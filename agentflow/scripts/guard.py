#!/usr/bin/env python3
"""AgentFlow PreToolUse guard. Exit 2 blocks the tool call; stderr is shown to Claude.

Hard rules (DESIGN-NOTES.md §Non-goals): no PR merge, no PR approve, no workflow dispatch, no force-push,
no push to protected branches (the staging branch is not one; force-push stays blocked there too), no direct
file write to staging via MCP, no edit/read/print of forbidden (secret) paths. Active only inside a repo that
has agentflow.yaml at its root. Best-effort text matching — not a security boundary.
"""

import json
import os
import re
import shlex
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import afconfig  # noqa: E402

SECRET_VAR = re.compile(r"\$\{?([A-Z0-9_]*(TOKEN|SECRET|PASSWORD|PASSWD|API_KEY|PRIVATE_KEY)[A-Z0-9_]*)\}?")
PRINTERS = {"cat", "head", "tail", "less", "more", "bat", "strings", "xxd", "od", "hexdump", "base64", "grep",
            "rg", "awk", "sed", "nl", "tac", "cut", "sort", "uniq", "diff", "cp", "scp", "rsync"}
COPIERS = {"cp", "scp", "rsync"}
GIT_GLOBAL_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}


def block(reason):
    sys.stderr.write("AgentFlow guard: " + reason + "\n")
    sys.exit(2)


def split_commands(command):
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    try:
        tokens = list(lexer)
    except ValueError:
        tokens = command.split()
    cmds, cur = [], []
    for tok in tokens:
        if tok and all(ch in ";&|()\n" for ch in tok):
            if cur:
                cmds.append(cur)
            cur = []
        else:
            cur.append(tok)
    if cur:
        cmds.append(cur)
    return cmds


def strip_prefix(argv):
    i = 0
    while i < len(argv) and (re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", argv[i]) or argv[i] in ("command", "exec", "sudo", "nohup", "time")):
        i += 1
    return argv[i:]


def git_parts(argv):
    """Return (git_cwd_arg, subcommand, args) for a git invocation, else None."""
    if not argv or os.path.basename(argv[0]) != "git":
        return None
    i, cwd = 1, None
    while i < len(argv) and argv[i].startswith("-"):
        opt = argv[i]
        name = opt.split("=", 1)[0]
        if name in GIT_GLOBAL_WITH_VALUE and "=" not in opt:
            if name == "-C" and i + 1 < len(argv):
                cwd = argv[i + 1]
            i += 2
        else:
            i += 1
    if i >= len(argv):
        return None
    return cwd, argv[i], argv[i + 1:]


def check_push(args, workdir, protected):
    positional = []
    for a in args:
        if a.startswith("--"):
            name = a.split("=", 1)[0]
            if name in ("--force", "--force-with-lease", "--force-if-includes", "--mirror"):
                block("force-push / mirror bị cấm (`%s`). Sync bằng `git pull --rebase` hoặc `git merge` rồi push thường." % a)
            if name in ("--all", "--delete") and protected:
                block("`git push %s` có thể chạm nhánh protected %s." % (a, sorted(protected)))
        elif a.startswith("-") and len(a) > 1:
            if "f" in a[1:]:
                block("force-push bị cấm (`%s`)." % a)
            if "d" in a[1:] and protected:
                block("xoá nhánh trên remote bị cấm khi repo có nhánh protected.")
        else:
            positional.append(a)
    refspecs = positional[1:]
    current = afconfig.git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=workdir)
    targets = []
    if not refspecs:
        targets.append(current)
    for spec in refspecs:
        if spec.startswith("+"):
            block("refspec có `+` là force-push (`%s`)." % spec)
        src, _, dst = spec.partition(":")
        dst = dst or src
        if dst in ("HEAD", "@"):
            dst = current
        targets.append(re.sub(r"^refs/heads/", "", dst or ""))
    for t in targets:
        if t and t in protected:
            block("push thẳng vào nhánh protected `%s` bị cấm — mở PR từ nhánh làm việc." % t)


def check_bash(command, root, cfg, protected):
    here = root
    for argv in split_commands(command):
        argv = strip_prefix(argv)
        if not argv:
            continue
        exe = os.path.basename(argv[0])
        if exe in ("cd", "pushd") and len(argv) > 1:
            here = os.path.normpath(os.path.join(here, os.path.expanduser(argv[1])))
            continue
        if exe in ("echo", "printf", "print"):
            hit = next((m.group(1) for a in argv[1:] for m in [SECRET_VAR.search(a)] if m), None)
            if hit:
                block("không in giá trị secret `$%s` ra output." % hit)
        if exe in ("env", "printenv") and (len(argv) == 1 or SECRET_VAR.search("$" + argv[-1])):
            block("`%s` in ra secret trong env — test sự tồn tại bằng `[ -n \"${VAR:-}\" ]`." % exe)
        if exe == "gh":
            joined = " ".join(argv[1:3])
            if joined == "pr merge" or (len(argv) > 2 and argv[1] == "pr" and argv[2] == "merge"):
                block("agent không bao giờ merge PR — người approve + merge ở cột ready_to_merge.")
            if len(argv) > 2 and argv[1] == "pr" and argv[2] == "review" and "--approve" in argv:
                block("agent không approve PR — dùng review dạng comment.")
            if argv[1:3] in (["workflow", "run"], ["run", "rerun"]) or (argv[1:2] == ["api"] and any(re.search(r"/actions/(workflows/[^/]+/dispatches|runs/\d+/rerun)", a) for a in argv)):
                block("agent không chạy/dispatch workflow — ở nhiều repo chạy workflow là deploy; báo người nếu cần.")
            if argv[1:2] == ["api"] and any(re.search(r"/pulls/\d+/merge\b", a) for a in argv):
                block("agent không bao giờ merge PR qua API.")
        parts = git_parts(argv)
        if parts:
            gcwd, sub, args = parts
            workdir = os.path.join(here, gcwd) if gcwd and not os.path.isabs(gcwd) else (gcwd or here)
            if sub == "push":
                check_push(args, workdir, protected)
        if exe in PRINTERS:
            operands = [a for a in argv[1:] if not a.startswith("-")]
            if exe in COPIERS:
                operands = operands[:-1]
            for path in operands:
                if afconfig.is_forbidden(path, here, cfg):
                    block("`%s` là path forbidden (secret) — không đọc/in/sao chép nội dung." % path)
        if exe == "curl":
            for a in argv[1:]:
                if a.startswith("@") and afconfig.is_forbidden(a[1:], here, cfg):
                    block("không gửi file secret `%s` qua curl." % a[1:])


def check_mcp(tool, ti, protected):
    low = tool.lower()
    if "actions_run_trigger" in low:
        block("agent không chạy/dispatch workflow — ở nhiều repo chạy workflow là deploy; báo người nếu cần.")
    if "merge_pull_request" in low:
        block("agent không bao giờ merge PR — người approve + merge ở cột ready_to_merge.")
    if "pull_request_review" in low and str(ti.get("event", "")).upper() == "APPROVE":
        block("agent không approve PR — post review với event=COMMENT.")
    if any(k in low for k in ("create_or_update_file", "push_files", "delete_file")):
        branch = ti.get("branch")
        if branch and branch in protected:
            block("ghi file thẳng lên nhánh protected `%s` qua MCP bị cấm." % branch)


def main():
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return
    tool = data.get("tool_name") or ""
    ti = data.get("tool_input") or {}
    cwd = data.get("cwd") or os.getcwd()
    root = afconfig.repo_root(cwd)
    if not root:
        return
    try:
        cfg = afconfig.load_config(root)
    except (ValueError, OSError):
        cfg = {}
    if cfg is None:
        return
    protected = afconfig.protected_branches(cfg, root)

    if tool == "Bash":
        check_bash(ti.get("command") or "", root, cfg, protected)
    elif tool in ("Edit", "Write", "MultiEdit", "NotebookEdit", "Read"):
        path = ti.get("file_path") or ti.get("notebook_path") or ""
        if afconfig.is_forbidden(path, root, cfg):
            block("`%s` là path forbidden (secret) — agent không đọc/sửa. Cần đổi giá trị → báo người." % path)
    elif tool.startswith("mcp__"):
        check_mcp(tool, ti, protected | set(filter(None, [afconfig.staging_branch(cfg)])))


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:  # never brick the session on a guard bug
        sys.stderr.write("AgentFlow guard internal error (allowed): %s\n" % exc)
        sys.exit(0)
