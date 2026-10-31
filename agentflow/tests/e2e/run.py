#!/usr/bin/env python3
"""End-to-end run of one ticket: `claude -p "/agentflow:do #42"` with real git, real hooks and real subagents, against a local
bare origin and a stateful fake GitHub. Asserts on what ended up in GitHub and in git, not on what the agents said.

  python3 agentflow/tests/e2e/run.py [--scenario new|rework|feedback|redeploy|manual-pass|pipeline-fail|pipeline-infra|pipeline-timeout|qc-stale] [--budget USD] [--model sonnet] [--keep]

new: a fresh ticket in Ready. rework: QC returned the ticket with a real bug on the PR branch, which is also on staging.
feedback: a human requested changes at Ready to Merge. redeploy: a human reset staging while the ticket waited for its build.
manual-pass: a human QC ticked the checklist and dragged the card. pipeline-fail: the staging build fails because of this PR.
pipeline-infra: it fails because of the infrastructure. pipeline-timeout: it never reports. qc-stale: the card reached QC while
staging does not hold the PR head.

Costs tokens, so unittest discovery does not pick it up. Nothing leaves the machine: GitHub MCP is replaced, the board tool
points at a local server, and GITHUB_TOKEN / GH_TOKEN are fake so a stray `gh` call fails.
"""

import argparse
import http.server
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.realpath(os.path.join(HERE, "..", ".."))
AGENTFLOW_YAML = """schema: 4
lang: vi
board:
  url: https://github.com/orgs/acme/projects/3
  status: {backlog: Backlog, ready: Ready, in_progress: In Progress, in_review: In Review, in_qc: In QC, ready_to_merge: Ready to Merge, done: Done}
  fields: {size: Size}
classify: label
types: {Feature: feat, Bug: fix}
labels: {agent: agentflow, blocked: blocked, needs_info: needs-info, changes_requested: changes-requested, qc_failed: qc-failed, qc_manual: qc-manual, deploying: deploying}
git: {base: master, protected: [], branch: "{type}/{issue}-{slug}", commit: "{type}: {subject}", link: Closes}
surfaces:
  core:
    path: "."
    check: "python3 -m py_compile calc.py"
    test: "python3 -m unittest"
    e2e: "python3 -m unittest"
forbidden: []
design: {figma: false, repo: []}
staging: {branch: staging, url: "", build: "", notes: "", timeout_min: 30}
people: {po: [acme-po], qc: [acme-qc], reviewers: [acme-rev]}
run: {parallel: 1, max_tasks: 1, max_review_rounds: 3, max_qc_rounds: 2, models: {dev: {default: %(model)s}, reviewer: %(model)s, qc: %(model)s}}
notify: {telegram: false, events: [blocked]}
"""
ISSUE_BODY = """### Vấn đề và mục tiêu
calc.py cần thêm phép chia.

### Tiêu chí nghiệm thu
- [ ] Khi gọi `div(6, 2)` từ calc.py thì trả về 3
- [ ] Khi gọi `div(1, 0)` thì báo lỗi `ValueError`

### Hướng dẫn cho QC
Test tự động được hết bằng e2e của surface `core`, không cần môi trường web.
"""


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def make_repo(base, model):
    bare = os.path.join(base, "origin.git")
    repo = os.path.join(base, "app")
    git(base, "init", "-q", "--bare", "-b", "master", bare)
    os.makedirs(repo)
    git(repo, "init", "-q", "-b", "master")
    git(repo, "config", "user.email", "e2e@example.com")
    git(repo, "config", "user.name", "e2e")
    git(repo, "remote", "add", "origin", "https://github.com/acme/app.git")
    git(repo, "config", "url.file://%s.insteadOf" % bare, "https://github.com/acme/app.git")
    with open(os.path.join(repo, ".gitignore"), "w") as fh:
        fh.write(".claude/settings.local.json\n.claude/worktrees/\n__pycache__/\n")
    with open(os.path.join(repo, "agentflow.yaml"), "w") as fh:
        fh.write(AGENTFLOW_YAML % {"model": model})
    with open(os.path.join(repo, "calc.py"), "w") as fh:
        fh.write("def add(a, b):\n    return a + b\n")
    with open(os.path.join(repo, "test_calc.py"), "w") as fh:
        fh.write("import unittest\n\nfrom calc import add\n\n\nclass AddTest(unittest.TestCase):\n    def test_add(self):\n        self.assertEqual(add(1, 2), 3)\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "chore: init")
    git(repo, "push", "-q", "origin", "master", "master:staging")
    git(repo, "fetch", "-q", "origin")
    git(repo, "remote", "set-head", "origin", "master")
    return repo, bare


def seed_rework(repo, state):
    """A PR whose div multiplies, already merged into staging, returned by QC."""
    git(repo, "switch", "-q", "-c", "feat/42-chia")
    with open(os.path.join(repo, "calc.py"), "a") as fh:
        fh.write("\n\ndef div(a, b):\n    return a * b\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "feat: thêm hàm chia")
    git(repo, "push", "-q", "-u", "origin", "feat/42-chia")
    head = git(repo, "rev-parse", "HEAD")
    git(repo, "switch", "-q", "master")
    git(repo, "branch", "-q", "staging", "origin/staging")
    git(repo, "switch", "-q", "staging")
    git(repo, "merge", "-q", "--no-ff", "--no-edit", "feat/42-chia")
    git(repo, "push", "-q", "origin", "staging")
    deploy = git(repo, "rev-parse", "HEAD")
    git(repo, "switch", "-q", "master")
    git(repo, "branch", "-qD", "staging", "feat/42-chia")
    short = head[:7]
    verdict = ("[AF:QC] ❌ @%s\n1. AC1 — chặn\n   Môi trường: staging @%s\n   Bước: `python3 -c 'from calc import div; print(div(6, 2))'`\n   Kỳ vọng: 3 · Thực tế: 12\n   Nghi vấn: calc.py, hàm div\n"
               "2. AC2 — chặn\n   Bước: `python3 -c 'from calc import div; div(1, 0)'`\n   Kỳ vọng: ValueError · Thực tế: trả về 0\nAC đã pass: không có." % (short, deploy[:7]))
    state["status"] = "Ready"
    state["issue"]["labels"] = ["Feature", "agentflow", "qc-failed"]
    state["issue"]["body"] += ("\n<!-- agentflow:state\nstage: ready\nreview_round: 0\nqc_round: 1\npr: 57\nbranch: feat/42-chia\nreview_sha: %s\ndeploy_sha: %s\nqc_sha: %s\nnext: DEV sửa mục 1..2 của QC @%s\n-->" % (short, deploy[:7], short, short))
    state["pr"] = {"number": 57, "state": "open", "draft": True, "title": "feat: thêm hàm chia", "body": "Closes #42\n\n- [ ] div(6, 2) = 3\n- [ ] div(1, 0) báo ValueError", "head": "feat/42-chia", "base": "master", "reviews": [], "comments": []}
    state["issue"]["comments"] = [{"id": i + 1, "body": b, "author_association": "OWNER", "user": {"login": "agentflow-bot"}}
                                  for i, b in enumerate(["[AF:DEV] pr #57 @" + short, "[AF:REVIEW] ✅ @" + short, "[AF:REVIEW] deployed @" + deploy[:7], verdict])]


GOOD_DIV = 'def div(a, b):\n    if b == 0:\n        raise ValueError("division by zero")\n    return a / b\n'
GOOD_TEST = ("import unittest\n\nfrom calc import add, div\n\n\nclass CalcTest(unittest.TestCase):\n    def test_add(self):\n        self.assertEqual(add(1, 2), 3)\n\n"
             "    def test_div(self):\n        self.assertEqual(div(6, 2), 3)\n\n    def test_zero(self):\n        with self.assertRaises(ValueError):\n            div(1, 0)\n")


def seed_done_pr(repo, state, on_staging):
    """A correct PR that has passed review. Returns (head, staging sha that holds it, or None)."""
    git(repo, "switch", "-q", "-c", "feat/42-chia")
    with open(os.path.join(repo, "calc.py"), "a") as fh:
        fh.write("\n\n" + GOOD_DIV)
    with open(os.path.join(repo, "test_calc.py"), "w") as fh:
        fh.write(GOOD_TEST)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "feat: thêm hàm chia")
    git(repo, "push", "-q", "-u", "origin", "feat/42-chia")
    head = git(repo, "rev-parse", "HEAD")
    deploy = None
    if on_staging:
        git(repo, "branch", "-q", "staging", "origin/staging")
        git(repo, "switch", "-q", "staging")
        git(repo, "merge", "-q", "--no-ff", "--no-edit", "feat/42-chia")
        git(repo, "push", "-q", "origin", "staging")
        deploy = git(repo, "rev-parse", "HEAD")
        git(repo, "switch", "-q", "master")
        git(repo, "branch", "-qD", "staging")
    git(repo, "switch", "-q", "master")
    git(repo, "branch", "-qD", "feat/42-chia")
    short = head[:7]
    state["pr"] = {"number": 57, "state": "open", "draft": False, "title": "feat: thêm hàm chia", "body": "Closes #42\n\n- [x] div(6, 2) = 3\n- [x] div(1, 0) báo ValueError", "head": "feat/42-chia", "base": "master", "reviews": [], "comments": []}
    heads = ["[AF:DEV] pr #57 @" + short, "[AF:REVIEW] ✅ @" + short]
    if deploy:
        heads.append("[AF:REVIEW] deployed @" + deploy[:7])
    state["issue"]["comments"] = [{"id": i + 1, "body": b, "author_association": "OWNER", "user": {"login": "agentflow-bot"}} for i, b in enumerate(heads)]
    return head, deploy


def seed_scenario(scenario, repo, state):
    if scenario == "rework":
        seed_rework(repo, state)
        return
    if scenario == "new":
        return
    if scenario == "pipeline-fail":  # the PR's bug breaks the build: nothing reaches QC testing yet
        seed_rework(repo, state)
        verdict = state["issue"]["comments"].pop()
        short = re.search(r"@(\w+)", verdict["body"]).group(1)
        deploy = re.search(r"deployed @(\w+)", state["issue"]["comments"][-1]["body"]).group(1)
        state["status"] = "In QC"
        state["issue"]["labels"] = ["Feature", "agentflow", "deploying"]
        state["issue"]["body"] = ISSUE_BODY + "\n<!-- agentflow:state\nstage: in_qc\nreview_round: 0\nqc_round: 0\npr: 57\nbranch: feat/42-chia\nreview_sha: %s\ndeploy_sha: %s\ndeploy_at: 2026-01-01T00:00:00Z\nnext: chờ pipeline staging\n-->" % (short, deploy)
        state["job_log"] = "FAIL: test_div (test_calc.DivTest)\nAssertionError: 12 != 3\n  File calc.py, in div: return a * b\n"
        return
    head, deploy = seed_done_pr(repo, state, on_staging=scenario not in ("redeploy", "qc-stale"))
    block = "\n<!-- agentflow:state\nstage: %s\nreview_round: 0\nqc_round: 0\npr: 57\nbranch: feat/42-chia\nreview_sha: " + head[:7] + "\n%snext: x\n-->"
    if scenario == "feedback":
        state["status"] = "Ready to Merge"
        state["issue"]["labels"] = ["Feature", "agentflow"]
        state["issue"]["body"] += block % ("ready_to_merge", "qc_sha: %s\ndeploy_sha: %s\ndeploy_at: 2026-01-01T00:00:00Z\n" % (head[:7], deploy[:7]))
        state["issue"]["comments"].append({"id": 9, "body": "[AF:QC] ✅ @" + head[:7], "author_association": "OWNER", "user": {"login": "agentflow-bot"}})
        state["pr"]["reviews"].append({"id": 1, "state": "CHANGES_REQUESTED", "event": "REQUEST_CHANGES", "author_association": "OWNER", "user": {"login": "acme-rev"},
                                       "body": "Đổi thông báo lỗi thành đúng chuỗi: khong chia duoc cho 0", "submitted_at": "2026-10-31T00:00:00Z"})
    elif scenario == "redeploy":
        # The human reset staging: deploy_sha exists but is not on staging any more.
        state["status"] = "In QC"
        state["pr"]["draft"] = True
        state["issue"]["labels"] = ["Feature", "agentflow", "deploying"]
        git(repo, "commit", "-q", "--allow-empty", "-m", "chore: bản staging cũ")
        old = git(repo, "rev-parse", "HEAD")
        git(repo, "push", "-q", "origin", "HEAD:refs/heads/old-deploy")
        git(repo, "reset", "-q", "--hard", "HEAD~1")
        state["issue"]["body"] += block % ("in_qc", "deploy_sha: %s\ndeploy_at: 2026-01-01T00:00:00Z\n" % old[:7])
        state["issue"]["comments"].append({"id": 9, "body": "[AF:REVIEW] deployed @" + old[:7], "author_association": "OWNER", "user": {"login": "agentflow-bot"}})
    elif scenario == "qc-stale":
        state["status"] = "In QC"
        state["pr"]["draft"] = True
        state["issue"]["labels"] = ["Feature", "agentflow"]
        state["issue"]["body"] += block % ("in_qc", "")
    elif scenario in ("pipeline-infra", "pipeline-timeout"):
        state["status"] = "In QC"
        state["pr"]["draft"] = True
        state["issue"]["labels"] = ["Feature", "agentflow", "deploying"]
        state["issue"]["body"] += block % ("in_qc", "deploy_sha: %s\ndeploy_at: 2026-01-01T00:00:00Z\n" % deploy[:7])
        if scenario == "pipeline-infra":
            state["job_log"] = "Error: No space left on device\nThe runner has received a shutdown signal. Không liên quan tới file nào trong repo.\n"
    elif scenario == "manual-pass":
        state["status"] = "Ready to Merge"
        state["pr"]["draft"] = True
        state["issue"]["labels"] = ["Feature", "agentflow", "qc-manual"]
        state["issue"]["body"] += block % ("in_qc", "qc_sha: %s\ndeploy_sha: %s\n" % (head[:7], deploy[:7]))
        state["issue"]["comments"].append({"id": 9, "body": "[AF:QC] 🧪 @%s\n- [x] Kiểm tra trên thiết bị thật" % head[:7], "author_association": "OWNER", "user": {"login": "agentflow-bot"}})


def make_plugin(base, state_path, bare):
    copy = os.path.join(base, "agentflow")
    shutil.copytree(PLUGIN, copy, ignore=shutil.ignore_patterns("__pycache__", "results"))
    manifest = os.path.join(copy, ".claude-plugin", "plugin.json")
    with open(manifest, encoding="utf-8") as fh:
        meta = json.load(fh)
    meta["defaultEnabled"] = True
    with open(manifest, "w", encoding="utf-8") as fh:
        json.dump(meta, fh, ensure_ascii=False, indent=2)
    with open(os.path.join(copy, ".mcp.json"), "w") as fh:
        json.dump({"mcpServers": {"github": {"command": sys.executable, "args": [os.path.join(HERE, "fake_github.py")], "env": {"AF_E2E_STATE": state_path, "AF_E2E_BARE": bare}}}}, fh)
    return copy


def serve_checks(bare, scenario, seeded_head):
    """What `agentflow-board checks` reads. The staging pipeline is green on whatever the head is, except in the pipeline-*
    scenarios, where the head as seeded stays failing or silent."""
    failing = {"status": "completed", "conclusion": "failure", "name": "build", "html_url": "http://local/1"}

    def runs_for(sha):
        if scenario == "pipeline-timeout":
            return []
        if scenario == "pipeline-infra" or (scenario == "pipeline-fail" and sha == seeded_head):
            return [failing]
        return [{"name": "build", "status": "completed", "conclusion": "success", "html_url": "http://local/1"}]

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            m = re.match(r"/repos/acme/app/(.*)", self.path.split("?")[0])
            rest = m.group(1) if m else ""
            body, code = {"message": "Not Found"}, 404
            try:
                if rest.endswith("/check-runs"):
                    runs = runs_for(rest.split("/")[1])
                    body, code = {"total_count": len(runs), "check_runs": runs}, 200
                elif rest.endswith("/status"):
                    body, code = {"total_count": 0, "statuses": []}, 200
                elif rest.startswith("commits/"):
                    body, code = {"sha": git(bare, "rev-parse", rest.split("/", 1)[1])}, 200
                elif rest.startswith("compare/"):
                    base, head = rest.split("/", 1)[1].split("...")
                    ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", base, head], cwd=bare, capture_output=True).returncode == 0
                    body, code = {"status": "ahead" if ancestor else "diverged"}, 200
            except subprocess.CalledProcessError:
                pass
            payload = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(payload)

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def assertions(state, repo, bare, master_before, scenario="new"):
    heads = [c["body"].lstrip().split("\n", 1)[0] for c in state["issue"]["comments"]]
    tools = [c["tool"] for c in state["calls"]]
    pr = state.get("pr") or {}
    head = git(bare, "rev-parse", "--verify", "-q", "refs/heads/" + pr["head"]) if pr.get("head") else None
    staging_has_head = bool(head) and subprocess.run(["git", "merge-base", "--is-ancestor", head, "staging"], cwd=bare, capture_output=True).returncode == 0
    has = lambda prefix: any(h.startswith(prefix) for h in heads)
    extra = []
    if scenario == "manual-pass":
        return [("đọc được QC người đã pass", has("[AF:SYS] qc-manual-pass"), heads),
                ("PR đã undraft", pr.get("draft") is False, pr.get("draft")),
                ("qc-manual đã gỡ", "qc-manual" not in state["issue"]["labels"], state["issue"]["labels"]),
                ("không spawn lại, không đổi cột", state["status"] == "Ready to Merge", state["status"]),
                ("state block ở ready_to_merge", "stage: ready_to_merge" in state["issue"]["body"], ""),
                ("không merge", "merge_pull_request" not in tools, "")]
    if scenario in ("pipeline-infra", "pipeline-timeout"):
        event = "[AF:QC] infra" if scenario == "pipeline-infra" else "[AF:SYS] pipeline-timeout"
        return [("báo đúng sự kiện", has(event), heads),
                ("gắn blocked, chờ người", "blocked" in state["issue"]["labels"], state["issue"]["labels"]),
                ("đứng nguyên cột", state["status"] == "In QC", state["status"]),
                ("không tính vào round", "qc_round: 0" in state["issue"]["body"], ""),
                ("không kết luận ❌ cho ticket", not has("[AF:QC] ❌"), heads),
                ("không undraft", pr.get("draft") is True, pr.get("draft")),
                ("không merge", "merge_pull_request" not in tools, "")]
    if scenario == "qc-stale":
        extra = [("QC không test khi staging thiếu head PR", has("[AF:QC] stale"), heads),
                 ("trả về review rồi deploy đúng", has("[AF:REVIEW] deployed"), heads)]
    if scenario == "pipeline-fail":
        extra = [("QC đọc log, trả về vì lỗi của ticket", has("[AF:QC] ❌"), heads),
                 ("DEV sửa rồi đi lại luồng", has("[AF:DEV] fixed"), heads),
                 ("hàm div đã đúng trên staging", "a / b" in git(bare, "show", "staging:calc.py") or "a // b" in git(bare, "show", "staging:calc.py"), "")]
    if scenario == "feedback":
        extra = [("nhận ra feedback", has("[AF:SYS] feedback"), heads),
                 ("DEV sửa theo feedback", "khong chia duoc cho 0" in git(bare, "show", "feat/42-chia:calc.py"), ""),
                 ("sửa xong vẫn qua lại QC", sum(h.startswith("[AF:QC] ✅") for h in heads) >= 2, heads)]
    if scenario == "redeploy":
        extra = [("nhận ra staging bị reset", has("[AF:SYS] redeploy"), heads),
                 ("deploy lại mà không kẹt blocked", "blocked" not in state["issue"]["labels"], state["issue"]["labels"]),
                 ("không review lại từ đầu", not any(c["tool"] == "pull_request_review_write" and "❌" in str(c["args"].get("body")) for c in state["calls"]), "")]
    if scenario == "rework":
        extra = [("DEV báo đã sửa", has("[AF:DEV] fixed"), heads),
                 ("review lại trước khi lên staging", sum(h.startswith("[AF:REVIEW] ✅") for h in heads) >= 2, heads),
                 ("hàm div đã đúng trên staging", "a / b" in git(bare, "show", "staging:calc.py") or "a // b" in git(bare, "show", "staging:calc.py"), ""),
                 ("round reset khi tới ready_to_merge", "qc_round: 0" in state["issue"]["body"], "")]
    return extra + [
        ("Status tới Ready to Merge", state["status"] == "Ready to Merge", state["status"]),
        ("đi đúng thứ tự cột", [s for s in state["status_history"] if s in ("In Progress", "In Review", "In QC", "Ready to Merge")][-3:] == ["In Review", "In QC", "Ready to Merge"], state["status_history"]),
        ("PR do DEV mở, đã undraft", pr.get("draft") is False, pr.get("draft")),
        ("PR nhắm master", pr.get("base") == "master", pr.get("base")),
        ("staging chứa head PR", staging_has_head, head),
        ("master không bị đụng", git(bare, "rev-parse", "master") == master_before, "master"),
        ("không merge, không dispatch", "merge_pull_request" not in tools and "actions_run_trigger" not in tools, ""),
        ("không APPROVE", not any(c["tool"] == "pull_request_review_write" and str(c["args"].get("event")).upper() == "APPROVE" for c in state["calls"]), ""),
        ("có comment của cả 3 role", has("[AF:DEV] pr") and has("[AF:REVIEW] ✅") and has("[AF:REVIEW] deployed") and has("[AF:QC] ✅"), heads),
        ("pipeline được kiểm", has("[AF:SYS] pipeline-ok"), heads),
        ("label sạch", set(state["issue"]["labels"]) == {"agentflow"} or set(state["issue"]["labels"]) == {"agentflow", "Feature"}, state["issue"]["labels"]),
        ("state block ở ready_to_merge", "stage: ready_to_merge" in state["issue"]["body"], ""),
        ("body của PO còn nguyên", "### Tiêu chí nghiệm thu" in state["issue"]["body"], ""),
        ("checkout chính sạch", git(repo, "status", "--porcelain") == "", git(repo, "status", "--porcelain")),
    ]


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--scenario", choices=["new", "rework", "feedback", "redeploy", "manual-pass", "pipeline-fail", "pipeline-infra", "pipeline-timeout", "qc-stale"], default="new")
    p.add_argument("--budget", default="8")
    p.add_argument("--model", default="sonnet")
    p.add_argument("--timeout", type=int, default=1500)
    p.add_argument("--keep", action="store_true")
    a = p.parse_args()
    base = os.path.realpath(tempfile.mkdtemp(prefix="af-e2e-"))
    state_path = os.path.join(base, "github.json")
    repo, bare = make_repo(base, a.model)
    master_before = git(bare, "rev-parse", "master")
    state = {"status": "Ready", "status_history": [], "calls": [], "pr": None,
             "issue": {"number": 42, "title": "Thêm hàm chia vào calc.py", "state": "open", "body": ISSUE_BODY, "labels": ["Feature"], "assignees": [], "comments": []}}
    seed_scenario(a.scenario, repo, state)
    with open(state_path, "w", encoding="utf-8") as fh:
        json.dump(state, fh, ensure_ascii=False)
    plugin = make_plugin(base, state_path, bare)
    server = serve_checks(bare, a.scenario, git(bare, "rev-parse", "staging"))
    env = dict(os.environ, GITHUB_TOKEN="fake-e2e", GH_TOKEN="fake-e2e", AGENTFLOW_JOURNAL=os.path.join(base, "journal.jsonl"),
               AGENTFLOW_GITHUB_API="http://127.0.0.1:%d" % server.server_address[1])
    log = os.path.join(base, "claude.jsonl")
    with open(log, "w") as out:
        try:
            res = subprocess.run(["claude", "-p", "/agentflow:do #42", "--plugin-dir", plugin, "--model", a.model, "--max-budget-usd", a.budget, "--dangerously-skip-permissions",
                                  "--output-format", "stream-json", "--verbose"], cwd=repo, env=env, stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT, timeout=a.timeout)
            exit_code = res.returncode
        except subprocess.TimeoutExpired:
            exit_code = "timeout"
    with open(state_path, encoding="utf-8") as fh:
        state = json.load(fh)
    checks = assertions(state, repo, bare, master_before, a.scenario)
    cost = None
    with open(log) as fh:
        for line in fh:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if row.get("type") == "result":
                cost = row.get("total_cost_usd")
    failed = 0
    for name, ok, detail in checks:
        failed += not ok
        print("%s %s%s" % ("✓" if ok else "✗", name, "" if ok else "  → %s" % (detail,)))
    print("claude exit %s · $%s · %d lời gọi MCP · comment: %s" % (exit_code, cost, len(state["calls"]), [c["body"].lstrip().split("\n", 1)[0][:40] for c in state["issue"]["comments"]]))
    print("kết quả: %s" % ("ĐẠT" if not failed else "%d/%d không đạt" % (failed, len(checks))))
    if a.keep or failed:
        print("giữ lại: %s" % base)
    else:
        shutil.rmtree(base, ignore_errors=True)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
