#!/usr/bin/env python3
"""Regression cases for scripts/guard.py. Run: python3 -I tests/test_guard.py (exit 1 on failure)."""

import json
import os
import subprocess
import sys
import tempfile

GUARD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts", "guard.py")
CONFIG = "schema: 4\ngit:\n  base: master\n  protected: [staging, production]\nstaging:\n  branch: staging\nforbidden: [\"secret/**\"]\n"

BASH = [
    ("BLOCK", "git push --force origin feat/1-x"), ("BLOCK", "git push --force-with-lease"),
    ("BLOCK", "git push -fu origin feat/1-x"), ("BLOCK", "git push origin +feat/1-x"),
    ("ALLOW", "git push origin HEAD:staging"), ("ALLOW", "git -C .claude/worktrees/af-7 push origin HEAD:staging"),
    ("BLOCK", "git push --force origin HEAD:staging"), ("BLOCK", "git push origin +HEAD:staging"),
    ("BLOCK", "git push origin --delete staging"), ("BLOCK", "git push origin HEAD:master"),
    ("BLOCK", "git push origin production"),
    ("BLOCK", "git push"), ("BLOCK", "cd x && git -C . push origin production"),
    ("ALLOW", "git push -u origin feat/1-x"), ("ALLOW", "cd .claude/worktrees/af-7 && git push"),
    ("ALLOW", "git -C .claude/worktrees/af-7 push -u origin feat/7-x"),
    ("BLOCK", "gh pr merge 12 --squash"), ("BLOCK", "gh api -X PUT repos/o/r/pulls/12/merge"),
    ("BLOCK", "gh pr review 12 --approve"), ("BLOCK", "gh workflow run web-release.yml"),
    ("BLOCK", "gh run rerun 123"), ("ALLOW", "gh run list --branch feat/1-x"),
    ("BLOCK", "cat secret/staging/app.env"), ("BLOCK", "cd .claude/worktrees/af-7 && cat secret/app.env"),
    ("BLOCK", "grep KEY .env | head"), ("BLOCK", "cat .claude/settings.local.json"),
    ("ALLOW", "cat .env.example"), ("ALLOW", "cp .env.example .env"),
    ("BLOCK", "echo $GITHUB_TOKEN"), ("BLOCK", "printf %s ${TELEGRAM_BOT_TOKEN}"), ("BLOCK", "env"),
    ("BLOCK", "printenv GITHUB_TOKEN"), ("ALLOW", "printenv PATH"),
    ("ALLOW", 'curl -H "Authorization: Bearer $GITHUB_TOKEN" https://api.github.com/user && echo done'),
    ("ALLOW", 'pnpm lint && git commit -m "fix: a | b; c"'), ("ALLOW", "agentflow-settings show"),
]
FILES = [
    ("BLOCK", "Edit", "secret/staging/app.env"), ("BLOCK", "Read", "server.pem"),
    ("BLOCK", "Read", ".claude/settings.local.json"), ("BLOCK", "Edit", ".claude/worktrees/af-7/secret/app.env"),
    ("ALLOW", "Edit", ".claude/worktrees/af-7/src/new/dir/a.ts"), ("ALLOW", "Edit", "src/app.ts"),
]
MCP = [
    ("BLOCK", "mcp__plugin_agentflow_github__merge_pull_request", {"pullNumber": 3}),
    ("BLOCK", "mcp__plugin_agentflow_github__pull_request_review_write", {"event": "APPROVE"}),
    ("ALLOW", "mcp__plugin_agentflow_github__pull_request_review_write", {"event": "COMMENT"}),
    ("BLOCK", "mcp__plugin_agentflow_github__actions_run_trigger", {"method": "run_workflow"}),
    ("ALLOW", "mcp__plugin_agentflow_github__actions_list", {"method": "list_workflow_runs"}),
    ("BLOCK", "mcp__plugin_agentflow_github__push_files", {"branch": "staging"}),
    ("BLOCK", "mcp__plugin_agentflow_github__create_or_update_file", {"branch": "master"}),
    ("ALLOW", "mcp__plugin_agentflow_github__update_pull_request", {"draft": False}),
]


def run(tool, tool_input, cwd):
    payload = json.dumps({"tool_name": tool, "tool_input": tool_input, "cwd": cwd})
    return subprocess.run([sys.executable, "-I", GUARD], input=payload, capture_output=True, text=True).returncode


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def main():
    failures = 0
    with tempfile.TemporaryDirectory() as tmp:
        repo = os.path.realpath(tmp)
        git(repo, "init", "-q", "-b", "master")
        with open(os.path.join(repo, "agentflow.yaml"), "w") as fh:
            fh.write(CONFIG)
        git(repo, "add", "-A")
        git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init")
        git(repo, "worktree", "add", "-q", ".claude/worktrees/af-7", "-b", "feat/7-x")

        cases = [(w, "Bash", {"command": c}) for w, c in BASH]
        cases += [(w, t, {"file_path": os.path.join(repo, p)}) for w, t, p in FILES]
        cases += MCP
        for want, tool, ti in cases:
            rc = run(tool, ti, repo)
            if rc != (2 if want == "BLOCK" else 0):
                failures += 1
                print("FAIL want %s rc=%s %s %s" % (want, rc, tool, json.dumps(ti, ensure_ascii=False)))
        git(repo, "switch", "-q", "-c", "feat/2-y")
        if run("Bash", {"command": "git push"}, repo) != 0:
            failures += 1
            print("FAIL plain push from feature branch should be allowed")
        if run("Bash", {"command": "git push --force"}, tempfile.gettempdir()) != 0:
            failures += 1
            print("FAIL guard must be inactive outside an agentflow repo")
        total = len(cases) + 2
    print("guard: %d/%d pass" % (total - failures, total))
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
