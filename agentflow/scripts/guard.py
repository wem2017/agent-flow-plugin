#!/usr/bin/env python3
"""AgentFlow PreToolUse guard. Exit 2 blocks the tool call; stderr is shown to Claude.

Hard rules (DESIGN-NOTES.md §Non-goals): no PR merge, no PR approve, no workflow dispatch, no force-push or remote
branch delete, no push to protected branches (the staging branch is not one; force-push stays blocked there too), no
direct file write to staging via MCP, no edit/read/print of forbidden (secret) paths, no secret value in a tool call.
Role rules apply inside an agentflow subagent, read from `agent_type` of the hook payload: QC changes nothing in git,
REVIEWER pushes only to staging and writes only in its staging worktree, DEV never touches staging or undrafts a PR.

Active only for paths inside a repo that has agentflow.yaml at its root. Commands are parsed, wrappers and nested
scripts unwrapped; what cannot be read statically (a script written and run later, `make deploy`, decoded payloads)
stays out of reach — best effort, not a security boundary.
"""

import fnmatch
import glob
import json
import os
import re
import shlex
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import afconfig  # noqa: E402
import shellparse  # noqa: E402

LITERAL = shellparse.LITERAL_DOLLAR
SECRET_WORD = r"TOKEN|SECRET|PASSWORD|PASSWD|API_KEY|PRIVATE_KEY"
# `${X:+set}` only says whether X is set.
SECRET_VAR = re.compile(r"\$\{?([A-Z0-9_]*(?:%s)[A-Z0-9_]*)(?![A-Z0-9_])(?!:?\+)" % SECRET_WORD)
ASSIGN = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)(\+?)=(.*)$", re.S)
VAR_DEFAULT = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*):?[-=]([^}]*)\}")
VAR_REF = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)")
BRACES = re.compile(r"\{([^{}\s\"':$]*,[^{}\s\"':$]*)\}")
PROC_ENV = re.compile(r"^/proc/[^/]+/environ$")
# These substitutions name the current branch, whatever it is: safe to read as HEAD.
CURRENT_BRANCH = re.compile(r"\$\(git (branch --show-current|rev-parse --abbrev-ref HEAD|symbolic-ref --short HEAD)\)")
DYNAMIC = re.compile(r"[$`]")
DYNAMIC_RISK = re.compile(r"\b(push|merge|approve|rerun|workflow|credential)\b|--force")

# Commands that run another command: name → (options taking a value, positionals before the command).
WRAPPERS = {
    "command": ((), 0), "builtin": ((), 0), "nohup": ((), 0), "time": (("-f", "-o"), 0), "caffeinate": (("-t", "-w"), 0),
    "setsid": ((), 0), "unbuffer": ((), 0), "chronic": ((), 0), "exec": (("-a",), 0),
    "timeout": (("-k", "--kill-after", "-s", "--signal"), 1), "gtimeout": (("-k", "--kill-after", "-s", "--signal"), 1),
    "nice": (("-n", "--adjustment"), 0), "ionice": (("-c", "-n", "-p"), 0), "stdbuf": (("-i", "-o", "-e"), 0),
    "env": (("-u", "--unset", "-C", "--chdir"), 0), "flock": (("-w", "-E"), 1), "watch": (("-n", "--interval"), 0),
    "sudo": (("-u", "-g", "-h", "-p", "-C", "-r", "-t", "-T", "-U", "-D"), 0), "doas": (("-u", "-C"), 0),
    "xargs": (("-I", "-n", "-P", "-L", "-s", "-E", "-d", "-a", "-J", "-R", "-S"), 0), "parallel": (("-j", "-S"), 0),
}
SHELLS = {"bash", "sh", "zsh", "dash", "ksh", "ash", "fish"}
SHELL_VALUE_FLAGS = {"-o", "-O", "--rcfile", "--init-file"}
INTERPRETERS = re.compile(r"^(python[0-9.]*|pypy[0-9.]*|node|nodejs|deno|bun|ruby|perl|php|lua|osascript)$")
PLUGIN_SECRET = re.compile(r"\$\{?(GITHUB_TOKEN|GH_TOKEN|TELEGRAM_BOT_TOKEN|FIGMA_TOKEN)\b")
PLUGIN_SECRET_HOSTS = re.compile(r"^(https?://)?([\w.-]+\.)?(github\.com|githubusercontent\.com|githubcopilot\.com|telegram\.org|figma\.com)([/:?]|$)")
CODE_FLAG = re.compile(r"^(-[a-zA-Z]*[ceEpr]|--eval|--print|--command)$")
# Commands that may name a secret path without showing its content: metadata, and runners that hand the file to a process.
PATH_SAFE = {"ls", "stat", "test", "[", "[[", "touch", "rm", "mkdir", "chmod", "chown", "echo", "printf", "print", "source",
             ".", "for", "case", "select", "cd", "pushd", "popd", "export", "unset", "which", "type", "du", "realpath",
             "dirname", "basename", "true", "false", "find", "fd", "agentflow-settings", "agentflow-board", "agentflow-journal",
             "agentflow-notify", "flutter", "dart", "dotenv", "dotenvx", "env-cmd", "docker", "docker-compose", "podman",
             "pnpm", "npm", "yarn", "npx", "make", "just", "task", "tree", "eslint", "prettier"}
PATTERN_FIRST = {"grep", "egrep", "fgrep", "rg", "ag", "ack", "jq", "yq", "sed", "gsed", "awk", "gawk"}
PATTERN_FLAGS = ("-e", "--regexp", "-f", "--file")
COPIERS = {"cp", "scp", "rsync", "install"}
SKIP_VALUE_FLAGS = {"--env-file", "--exclude", "--ignore"}
FILE_FLAG = re.compile(r"file|input|data|upload|body|from|source|src|path")
# Commands that change the files they name; the role rules look at these too.
MUTATORS = {"rm", "rmdir", "touch", "mkdir", "chmod", "chown", "truncate", "tee"}

GIT_GLOBAL_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--super-prefix", "--attr-source", "--config-env"}
GIT_READERS = {"show", "log", "diff", "blame", "annotate", "cat-file", "grep", "archive", "whatchanged", "add"}
GIT_CHANGERS = {"commit", "push", "merge", "rebase", "cherry-pick", "revert", "reset", "tag", "am", "apply", "update-ref", "clean",
                "rm", "mv", "restore", "stash", "filter-branch", "fast-import"}
GIT_BUILTIN = GIT_READERS | GIT_CHANGERS | {
    "status", "fetch", "pull", "switch", "checkout", "branch", "worktree", "rev-parse", "rev-list", "ls-files", "ls-remote",
    "ls-tree", "remote", "config", "init", "clone", "symbolic-ref", "merge-base", "check-ignore", "describe", "shortlog",
    "show-ref", "for-each-ref", "name-rev", "credential", "version", "help"}
GIT_VALUE_FLAGS = {"-S", "-G", "--grep", "--author", "--committer", "-L", "--format", "--pretty", "--since", "--until", "-n", "-e"}
PUSH_VALUE_FLAGS = {"-o", "--push-option", "--repo", "--receive-pack", "--exec"}
PUSH_DESTRUCTIVE = ("--force", "--force-with-lease", "--force-if-includes", "--mirror", "--delete", "--prune")
PUSH_EVERYTHING = ("--all", "--branches")
GH_FILE_FLAGS = {"--body-file", "-F", "--input"}
GIT_CONFIG_ENV = re.compile(r"^GIT_CONFIG(_COUNT|_PARAMETERS|_KEY_\d+|_VALUE_\d+|_GLOBAL|_SYSTEM|_NOSYSTEM)?$")
# Runners whose subcommand runs an arbitrary program: name → the subcommands that do ("" = the runner itself).
EXEC_RUNNERS = {"npx": ("",), "pnpx": ("",), "bunx": ("",), "pnpm": ("exec", "dlx"), "npm": ("exec",), "yarn": ("exec", "dlx"), "bun": ("x",),
                "uv": ("run",), "uvx": ("",), "poetry": ("run",), "pipenv": ("run",), "pipx": ("run",), "bundle": ("exec",), "mise": ("exec", "x"), "rtx": ("exec", "x")}
# A file a glob over names would hit if it hits secrets.
SECRET_PROBES = (".env", ".env.local", "server.pem", "server.key", "id_rsa", "id_ed25519")
EXEC_ENV = {"GIT_PAGER", "PAGER", "GIT_EDITOR", "EDITOR", "VISUAL", "GIT_SSH_COMMAND", "GIT_SEQUENCE_EDITOR", "GIT_EXTERNAL_DIFF"}
EXEC_CONFIG = re.compile(r"(pager(\.|$)|editor$|sshcommand$|external$|\.program$|helper$|hookspath$|fsmonitor$|askpass$)")
GIT_REMOTE_WRITERS = {"send-pack", "http-push"}
PATTERN_VALUE_FLAGS = {"-t", "-T", "-g", "--type", "--type-not", "--glob", "--iglob", "--include", "--exclude", "--exclude-dir", "-A", "-B", "-C", "-m", "--max-count", "--context"}
CODE_ATTACHED = re.compile(r"^-[a-zA-Z]*[ce](.+)$|^--(?:eval|print|command)=(.+)$", re.S)
GH_API_VALUE_FLAGS = {"-X", "--method", "-H", "--header", "-f", "--raw-field", "-F", "--field", "-q", "--jq", "-t", "--template",
                      "--input", "--hostname", "--cache", "-p", "--preview"}

MSG_MERGE = "agent không bao giờ merge PR — người approve + merge ở cột ready_to_merge."
MSG_APPROVE = "agent không approve PR — post review với event=COMMENT."
MSG_DISPATCH = "agent không chạy/dispatch workflow — ở nhiều repo chạy workflow là deploy; báo người nếu cần."
MSG_REF = "agent không sửa/xoá ref, branch protection hay ruleset trên remote qua API."
MSG_TOKEN = "không in token — test sự tồn tại bằng `[ -n \"${VAR:-}\" ]`."
MSG_FORCE = "force-push / mirror / xoá nhánh trên remote bị cấm. Sync bằng `git merge` rồi push thường."
MSG_UNDRAFT = "chỉ QC (hoặc orchestrator sau khi QC người pass) mới undraft PR."
MSG_DRAFT = "PR luôn mở dạng draft: chưa qua QC thì chưa được merge."

API_WRITES = [  # REST endpoints that must not receive a write
    (re.compile(r"/pulls/[^/\s]+/merge\b"), MSG_MERGE), (re.compile(r"/merges\b"), MSG_MERGE), (re.compile(r"/auto-merge\b"), MSG_MERGE),
    (re.compile(r"/dispatches\b"), MSG_DISPATCH), (re.compile(r"/actions/(runs|jobs)/[^/\s]+/rerun"), MSG_DISPATCH),
    (re.compile(r"/git/refs\b"), MSG_REF), (re.compile(r"/branches/[^/\s]+/protection\b"), MSG_REF), (re.compile(r"/rulesets\b"), MSG_REF),
]
GRAPHQL_BANNED = [
    (re.compile(r"\b(mergePullRequest|enablePullRequestAutoMerge|mergeBranch)\b"), MSG_MERGE),
    (re.compile(r"\b(updateRefs?|deleteRef|updateBranchProtectionRule|deleteBranchProtectionRule)\b"), MSG_REF),
    (re.compile(r"\b(addPullRequestReview|submitPullRequestReview)\b[\s\S]*\bAPPROVE\b"), MSG_APPROVE),
]
APPROVE_EVENT = re.compile(r"event[\"':=\s]+APPROVE\b")
# Text rules for code handed to an interpreter (and the last resort when a command cannot be parsed).
CODE_BANNED = [
    (re.compile(r"\bgit\b[^\n]*\bpush\b[^\n]*(--force|--mirror|--prune|--delete|[\s\"',]-[a-zA-Z]*[fd]\b|[\s\"',]\+\S)"), MSG_FORCE),
    (re.compile(r"\bgh\b[^\n]*\bpr\b[^\n]*\bmerge\b"), MSG_MERGE),
    (re.compile(r"\bgh\b[^\n]*\bpr\b[^\n]*\breview\b[^\n]*(--approve|[\s\"',]-a\b)"), MSG_APPROVE),
    (re.compile(r"\bgh\b[^\n]*\b(workflow\b[^\n]*\brun|run\b[^\n]*\brerun)\b"), MSG_DISPATCH),
    (re.compile(r"\bgh\b[^\n]*\bauth\b[^\n]*\btoken\b"), MSG_TOKEN),
    (re.compile(r"(?<!\bin )os\.environ(?!\s*(\.get\b|\[))|process\.env(?![.\[])"), "không in toàn bộ env — có secret trong đó."),
    (re.compile(r"(print|console\.log|puts|echo|write)[^\n]*(environ|process\.env|ENV\b|ENVIRON|getenv)[^\n]*(%s)" % SECRET_WORD), MSG_TOKEN),
    (re.compile(r"^\s*process\.env\.\w*(%s)\w*\s*$" % SECRET_WORD), MSG_TOKEN),
]
CODE_STRING = re.compile(r"[\"'`]([^\"'`\n]{1,300})[\"'`]")
RISKY_TEXT = re.compile(r"\b(push|merge|approve|dispatch|rerun|workflow|credential|environ|token|gh)\b|--force|\.env\b|settings\.local", re.I)
MCP_COMMAND_TOOL = re.compile(r"terminal|shell|bash|exec|run_command", re.I)
MCP_PATH_KEYS = ("path", "file_path", "filePath", "pathInProject", "absolute_path")


def block(reason):
    sys.stderr.write("AgentFlow guard: " + reason + "\n")
    sys.exit(2)


def role_of(data):
    kind = str(data.get("agent_type") or "")
    return kind.split(":", 1)[1] if kind.startswith("agentflow:") else None


def parent_dir(path):
    probe = os.path.dirname(path)
    while probe and not os.path.isdir(probe) and probe != os.path.dirname(probe):
        probe = os.path.dirname(probe)
    return probe


def name_of(word):
    return os.path.basename(word).lower()  # GIT runs git on a case-insensitive filesystem


class Scope:
    """agentflow.yaml in force for one repo."""

    def __init__(self, root, cfg):
        self.root, self.cfg = root, cfg
        self.main = afconfig.main_root(root) or root
        self.protected = afconfig.protected_branches(cfg, root)
        self.staging = afconfig.staging_branch(cfg)


class Session:
    def __init__(self, cwd, role):
        self.cwd, self.here, self.here_known, self.role = cwd, cwd, True, role
        self.vars, self.hard_only, self.depth, self._scopes = {}, False, 0, {}
        self.stack, self.dirs, self.previous, self.branches = [], [], cwd, {}

    def scope(self, path=None):
        path = path or self.here
        root = afconfig.repo_root(path if os.path.isdir(path) else parent_dir(path))
        if not root:
            return None
        if root not in self._scopes:
            try:
                cfg = afconfig.load_config(root)
            except (ValueError, OSError):
                cfg = {}
            self._scopes[root] = None if cfg is None else Scope(root, cfg)
        return self._scopes[root]

    def abspath(self, path):
        return os.path.normpath(os.path.join(self.here, os.path.expanduser(path)))

    def secret_path(self, path):
        if not path or "\n" in path or "://" in path or len(path) > 1024:
            return False
        absolute = self.abspath(path)
        if PROC_ENV.match(absolute):
            return True
        scope = self.scope(parent_dir(absolute)) or self.scope(self.cwd)
        return bool(scope) and afconfig.is_forbidden(absolute, scope.root, scope.cfg)

    def write_denied(self, path):
        """Why this role may not change `path`, or None. Only subagents are limited; outside the repo nothing is."""
        if not self.role or DYNAMIC.search(path) or (not self.here_known and not path.startswith(("/", "~"))):
            return None  # `cd "$(mktemp -d)" && echo x > r.txt`: wherever that is, it cannot be judged
        absolute = self.abspath(path)
        resolved = os.path.realpath(absolute)
        plugin = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
        if re.search(r"/\.claude/(settings(\.local)?\.json|hooks/)", resolved) or resolved == plugin or resolved.startswith(plugin + os.sep):
            return "subagent không sửa settings/hook/plugin (`%s`)." % path
        scope = self.scope(parent_dir(absolute))
        if not scope or not (resolved == scope.main or resolved.startswith(scope.main + os.sep)):
            return None
        if os.path.basename(resolved) == afconfig.CONFIG_NAME:
            return "subagent không sửa/xoá `agentflow.yaml`."
        own = {"reviewer": r"/\.claude/worktrees/af-\d+-staging(/|$)", "qc": r"/\.claude/worktrees/af-\d+-qc(/|$)",
               "dev": r"/\.claude/worktrees/af-\d+(/|$)"}.get(self.role)
        if own and not re.search(own, resolved):
            return "%s không sửa file ngoài worktree của mình (`%s`)." % (self.role.upper(), path)
        return None

    def in_staging_worktree(self, path):
        return re.search(r"/\.claude/worktrees/af-\d+-staging(/|$)", self.abspath(path)) is not None


# ── push ──────────────────────────────────────────────────────────────────────

def long_flag_matches(name, full):
    """git takes any unambiguous prefix of a long option: `--del` is `--delete`."""
    return any(f == name or (len(name) >= 4 and f.startswith(name)) for f in full)


def push_targets(args, current, known):
    """Remote branches this push would write. Blocks what is destructive whatever the branch."""
    positional, i = [], 0
    while i < len(args):
        a = args[i]
        i += 1
        name = a.split("=", 1)[0]
        if a.startswith("--"):
            if long_flag_matches(name, PUSH_DESTRUCTIVE):
                block("`%s`: %s" % (a, MSG_FORCE))
            if long_flag_matches(name, PUSH_EVERYTHING):
                block("`git push %s` đẩy mọi nhánh, có thể chạm nhánh protected." % a)
            if name in PUSH_VALUE_FLAGS and "=" not in a:
                i += 1
        elif a.startswith("-") and len(a) > 1:
            if "f" in a[1:] or "d" in a[1:]:
                block("`%s`: %s" % (a, MSG_FORCE))
            if a in PUSH_VALUE_FLAGS:
                i += 1
        else:
            positional.append(a)
    if positional and DYNAMIC.search(positional[0]):
        block("remote `%s` không đọc được trước khi chạy — ghi thẳng tên." % positional[0])
    refspecs = positional[1:]
    if not refspecs:
        if not current or not known:
            block("không xác định được nhánh sẽ push — ghi refspec tường minh: `git push -u origin <branch>`.")
        return [current]
    targets = []
    for spec in refspecs:
        spec = CURRENT_BRANCH.sub("HEAD", spec)
        if spec.startswith("+"):
            block("refspec có `+` là force-push (`%s`)." % spec)
        if DYNAMIC.search(spec) or "*" in spec:
            block("refspec `%s` không đọc được trước khi chạy — ghi thẳng tên nhánh." % spec)
        src, sep, dst = spec.partition(":")
        if sep and not src:
            block("refspec `%s` xoá nhánh trên remote. %s" % (spec, MSG_FORCE))
        dst = dst or src
        if dst in ("HEAD", "@"):
            if not current:
                block("không xác định được nhánh sẽ push — ghi thẳng tên nhánh.")
            dst = current
        targets.append(re.sub(r"^(refs/)?heads/", "", dst))
    return targets


def check_push(args, workdir, known, session, scope):
    current = session.branches.get(workdir) or (afconfig.git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=workdir) if known else None)
    for t in push_targets(args, current, known):
        if t in scope.protected:
            block("push thẳng vào nhánh protected `%s` bị cấm — mở PR từ nhánh làm việc." % t)
        if session.role == "reviewer" and t != scope.staging:
            block("REVIEWER chỉ push vào `%s`, không đụng PR branch." % scope.staging)
        if session.role == "dev" and t == scope.staging:
            block("DEV không đụng nhánh staging — REVIEWER merge lên đó sau khi ✅.")


# ── git ───────────────────────────────────────────────────────────────────────

def git_parts(argv):
    """Return (-C values, --git-dir, subcommand, args, -c values) for a git invocation, else None."""
    i, cwds, gitdir, configs = 1, [], None, []
    while i < len(argv) and argv[i].startswith("-"):
        opt = argv[i]
        name, eq, value = opt.partition("=")
        if name in GIT_GLOBAL_WITH_VALUE and not eq:
            value = argv[i + 1] if i + 1 < len(argv) else ""
            i += 2
        else:
            i += 1
        if name == "-C":
            cwds.append(value)
        elif name == "--git-dir":
            gitdir = value
        elif name == "-c":
            configs.append(value)
    if i >= len(argv):
        return None
    return cwds, gitdir, argv[i], argv[i + 1 :], configs


def check_git_config_item(key, value, session, aliases):
    """`key` as git reads it, case-insensitively. Config can change what a later push does."""
    low = key.lower()
    if low.startswith("alias."):
        aliases[low[6:]] = value
        check_alias(value, [], session)
    elif EXEC_CONFIG.search(low) and value:  # git runs these through a shell
        check_bash(value[1:] if value.startswith("!") else value, session)
    elif re.match(r"remote\..*\.(push|mirror|pushurl)$", low) or low.startswith("push."):
        block("không đổi cấu hình push (`%s`) — ghi refspec tường minh." % key)


def check_alias(value, args, session):
    """A git alias runs whatever it says, with the arguments it was called with."""
    if not value:
        return
    text = value[1:] if value.startswith("!") else "git " + value
    check_bash(" ".join([text] + [shlex.quote(a) for a in args]), session)


def track_branch(sub, args, workdir, session):
    """`git switch master && git push` pushes master, though HEAD is elsewhere right now."""
    target = None
    for i, a in enumerate(args):
        if a in ("-c", "-C", "-b", "-B", "--create", "--force-create", "--orphan") and i + 1 < len(args):
            session.branches[workdir] = args[i + 1]
            return
        if a == "--":
            return
        if not a.startswith("-") and target is None:
            target = a
    if target and afconfig.git(["rev-parse", "--verify", "--quiet", "refs/heads/" + target], cwd=workdir):
        session.branches[workdir] = target


def git_read_paths(sub, args):
    """Words of this git command that name a file. Patterns and option values do not."""
    out, skip, after_dashes = [], False, False
    pattern_pending = sub == "grep" and "-e" not in args
    for a in args:
        if skip:
            skip = False
        elif after_dashes:
            out.append(a)
        elif a == "--":
            after_dashes = True
        elif a in GIT_VALUE_FLAGS:
            skip = True
        elif not a.startswith("-"):
            if pattern_pending:
                pattern_pending = False
            else:
                out.append(a)
    paths = []
    for a in out:
        if re.match(r"^:(!|\^|\([^)]*exclude[^)]*\))", a):
            continue  # names what to leave out
        a = re.sub(r"^:(\([^)]*\)|[/!^]+)", "", a)  # pathspec magic
        paths.append(a.split(":", 1)[1] if ":" in a and "://" not in a else a)
    return paths


def read_only_form(sub, args):
    words = [a for a in args if not a.startswith("-")]
    if sub == "tag":
        return not words or "-l" in args or "--list" in args
    if sub == "stash":
        return words[:1] in (["list"], ["show"])
    return False


def check_git(argv, session):
    parts = git_parts(argv)
    if not parts:
        return
    cwds, gitdir, sub, args, configs = parts
    if DYNAMIC.search(sub):
        block("lệnh con của git (`%s`) không đọc được trước khi chạy — ghi thẳng." % sub)
    if sub in GIT_REMOTE_WRITERS:
        block("`git %s` ghi thẳng lên remote, không qua kiểm tra của push. %s" % (sub, MSG_FORCE))
    workdir, known = session.here, session.here_known
    for c in cwds:
        known = known and not DYNAMIC.search(c)
        workdir = os.path.normpath(os.path.join(workdir, c))
    if gitdir and not DYNAMIC.search(gitdir):
        workdir = os.path.join(session.here, gitdir)
        workdir = os.path.dirname(workdir) if os.path.basename(workdir) == ".git" else workdir
    elif gitdir:
        known = False
    scope = session.scope(workdir if known else None) or session.scope(session.cwd)
    if not scope:
        return
    aliases = {}
    for item in configs:
        key, _, value = item.partition("=")
        check_git_config_item(key, value, session, aliases)
    if any(a.split("=", 1)[0] == "--config-env" for a in argv[1:]):
        block("không cấu hình git qua `--config-env` — guard không đọc được cấu hình đó.")
    if sub == "remote" and any(a.startswith("--mirror") for a in args):
        block("remote `--mirror` biến push thường thành mirror. %s" % MSG_FORCE)
    if sub == "rebase":  # these run a shell command per commit
        for i, a in enumerate(args):
            if a in ("-x", "--exec") and i + 1 < len(args):
                check_bash(args[i + 1], session)
            elif a.startswith("--exec="):
                check_bash(a.split("=", 1)[1], session)
    if (sub == "bisect" and args[:1] == ["run"]) or (sub == "submodule" and args[:1] == ["foreach"]):
        check_bash(" ".join(shlex.quote(a) for a in args[1:]), session)
    if sub == "config":
        if not {"--get", "--list", "-l", "--get-all", "--get-regexp", "get", "list"} & set(args):
            words = [a for a in args if not a.startswith("-")]  # `config set k v`, `config --file f k v`: find k by its dot
            for i, word in enumerate(words):
                if "." in word and "/" not in word:
                    check_git_config_item(word, words[i + 1] if i + 1 < len(words) else "", session, {})
        return
    if sub not in GIT_BUILTIN:
        value = aliases.get(sub.lower()) or afconfig.git(["config", "--get", "alias." + sub], cwd=workdir if known else None)
        if value:
            check_alias(value, args, session)
            return
        hidden = next((i for i, a in enumerate(args) if a in GIT_CHANGERS or a in GIT_READERS or a in GIT_REMOTE_WRITERS), None)  # a global option we do not know took a value
        if hidden is None:
            return
        sub, args = args[hidden], args[hidden + 1 :]
        if sub in GIT_REMOTE_WRITERS:
            block("`git %s` ghi thẳng lên remote, không qua kiểm tra của push. %s" % (sub, MSG_FORCE))
    if sub == "credential":
        block(MSG_TOKEN)
    if sub == "push":
        check_push(args, workdir, known, session, scope)
    if sub in ("switch", "checkout"):
        track_branch(sub, args, workdir, session)
    if session.hard_only:
        return
    if sub in GIT_READERS:
        for path in git_read_paths(sub, args):
            if session.secret_path(path):
                block("`%s` là path forbidden (secret) — không đọc qua git, không stage." % path)
    changes = sub in GIT_CHANGERS and not read_only_form(sub, args)
    if session.role == "qc" and (changes or sub in ("pull", "checkout", "switch")):
        block("QC không commit, không push, không đổi lịch sử git (`git %s`)." % sub)
    if session.role == "reviewer" and ((changes and sub != "push") or sub in ("pull", "checkout", "switch")):
        if not known or not session.in_staging_worktree(workdir):
            block("REVIEWER chỉ `git %s` trong worktree staging, ghi path tường minh: `git -C <repo>/.claude/worktrees/af-<n>-staging …`." % sub)
    if session.role == "dev" and ((changes and sub != "push") or sub in ("switch", "checkout")):
        if not known or not re.search(r"/\.claude/worktrees/af-\d+(/|$)", session.abspath(workdir)):
            block("DEV chỉ `git %s` trong worktree của mình, ghi path tường minh: `git -C <repo>/.claude/worktrees/af-<n> …`." % sub)
    if session.role == "dev" and scope.staging and sub in ("merge", "pull", "rebase", "cherry-pick", "switch", "checkout", "worktree"):
        pattern = r"(refs/heads/|refs/remotes/\w+/|origin/)?%s" % re.escape(scope.staging)
        skip = False
        for a in args:
            if a == "--":
                break
            if not skip and re.fullmatch(pattern, re.split(r"[\^~@]", a)[0]):
                block("DEV không đụng nhánh staging — nó chứa code chưa đạt của ticket khác.")
            skip = a in ("-c", "-C", "-b", "-B", "--create", "--force-create", "-m")  # names a new branch, or a message


# ── gh, curl ──────────────────────────────────────────────────────────────────

def http_method(args, flags, body_flags, default="GET"):
    for i, a in enumerate(args):
        name, eq, value = a.partition("=")
        if name in flags:
            return (value if eq else (args[i + 1] if i + 1 < len(args) else default)).upper()
        for short in (f for f in flags if len(f) == 2):
            if a.startswith(short) and len(a) > 2 and not a.startswith("--"):  # -XPUT
                return a[2:].upper()
    if any(a.split("=", 1)[0] in body_flags for a in args):
        return "POST"
    return default


def check_api(endpoint, text, method, scope):
    """`endpoint` is the path or URL; `text` the whole call, for bodies. A comment that mentions a path is not that path."""
    if "graphql" in endpoint:
        for pattern, reason in GRAPHQL_BANNED:
            if pattern.search(text):
                block(reason)
        return
    if "/reviews" in endpoint and APPROVE_EVENT.search(text):
        block(MSG_APPROVE)
    if method == "GET":
        return
    for pattern, reason in API_WRITES:
        if pattern.search(endpoint):
            block(reason)
    if "/contents/" in endpoint:
        m = re.search(r"\bbranch[\"':=\s]+([\w./-]+)", text)
        if not m or m.group(1) in scope.protected or m.group(1) == scope.staging:
            block("ghi file qua API lên `%s` bị cấm." % (m.group(1) if m else "default branch"))


def gh_positionals(args, value_flags):
    out, i = [], 0
    while i < len(args):
        a = args[i]
        if a.startswith("-"):
            i += 2 if a in value_flags else 1
        else:
            out.append(a)
            i += 1
    return out


def gh_stdin_text(args, cmd, session):
    """`gh api --input -` takes the request from stdin, `--input f` from a file: the rules must see it."""
    text = ""
    for i, a in enumerate(args[:-1]):
        if a == "--input":
            if args[i + 1] == "-":
                text += "\n".join(cmd.bodies + cmd.herestrings) + "\n" + (upstream_text(cmd, session) or "")
            else:
                try:
                    with open(session.abspath(args[i + 1]), encoding="utf-8", errors="replace") as fh:
                        text += fh.read(256 * 1024)
                except OSError:
                    pass
    return text


def check_gh(args, session, scope, cmd):
    words, i = [], 0
    while i < len(args):  # `-R o/r` may stand anywhere, also before the subcommand
        if args[i] in ("-R", "--repo"):
            i += 2
        elif args[i].startswith("--repo="):
            i += 1
        else:
            words.append(args[i])
            i += 1
    args = words
    while args and args[0].startswith("-"):
        args = args[1:]
    head = args[:2]
    if head == ["pr", "merge"]:
        block(MSG_MERGE)
    if head == ["pr", "review"] and any(a == "--approve" or re.match(r"^-[cr]*a", a) for a in args):
        block(MSG_APPROVE)
    if head == ["pr", "ready"] and session.role in ("dev", "reviewer") and "--undo" not in args:
        block(MSG_UNDRAFT)
    if head == ["pr", "create"] and session.role == "dev" and "--draft" not in args and "-d" not in args:
        block(MSG_DRAFT)
    if head in (["workflow", "run"], ["run", "rerun"]):
        block(MSG_DISPATCH)
    if head == ["repo", "sync"]:
        block("`gh repo sync` có thể ghi đè nhánh trên remote. %s" % MSG_FORCE)
    if head[:1] == ["alias"] and head[1:] in (["set"], ["import"]):
        block("không tạo alias cho gh — guard không đọc được lệnh phía sau.")
    if head in (["auth", "token"], ["auth", "git-credential"]) or (head == ["auth", "status"] and ("--show-token" in args or "-t" in args)):
        block(MSG_TOKEN)
    if head[:1] == ["api"]:
        method = http_method(args[1:], ("-X", "--method"), ("-f", "-F", "--field", "--raw-field", "--input"))
        endpoint = " ".join(gh_positionals(args[1:], GH_API_VALUE_FLAGS))
        check_api(endpoint, " ".join(args[1:]) + " " + gh_stdin_text(args, cmd, session), method, scope)
    if session.hard_only:
        return
    paths = [args[i + 1].split("=", 1)[-1].lstrip("@") for i, a in enumerate(args[:-1]) if a in GH_FILE_FLAGS]
    if head in (["gist", "create"], ["gist", "edit"], ["release", "upload"]):
        paths += gh_positionals(args[2:], {"-d", "--desc", "--description", "-f", "--filename"})
    for path in paths:
        if session.secret_path(path):
            block("`%s` là path forbidden (secret) — không gửi lên GitHub." % path)


def check_http_client(exe, args, scope):
    if any(PLUGIN_SECRET.search(a) for a in args):  # the plugin's own tokens only go where they are valid
        hosts = [a for a in args if re.match(r"^https?://", a, re.I)] or [a for a in args if not a.startswith("-") and re.match(r"^[\w-]+(\.[\w-]+)+(/|$)", a)]
        bad = [h for h in hosts if not PLUGIN_SECRET_HOSTS.match(h.lower())]
        if bad or not hosts:
            block("token của plugin chỉ gửi tới GitHub/Telegram/Figma, không gửi tới `%s`." % (bad[0] if bad else "host không đọc được"))
    endpoints = [a for a in args if not a.startswith("-") and ("api.github.com" in a.lower() or "/graphql" in a.lower())]
    if not endpoints:
        return
    if exe == "wget":
        method = http_method(args, ("--method",), ("--post-data", "--post-file", "--body-data", "--body-file"))
    else:
        method = http_method(args, ("-X", "--request"), ("-d", "--data", "--data-raw", "--data-binary", "--json", "-F", "--form", "-T", "--upload-file"))
    for endpoint in endpoints:
        check_api(endpoint, " ".join(args), method, scope)


# ── secrets ───────────────────────────────────────────────────────────────────

def operand_paths(exe, args):
    """Words that may name a file this command opens."""
    out, skip_next, pattern_pending = [], False, exe in PATTERN_FIRST
    if pattern_pending and any(a in PATTERN_FLAGS or a.startswith(("--regexp=", "--file=")) for a in args):
        pattern_pending = False
    for a in args:
        if skip_next:
            skip_next = False
            continue
        if a in SKIP_VALUE_FLAGS or (a in ("-e", "--regexp") and exe in PATTERN_FIRST) or (a in PATTERN_VALUE_FLAGS and exe in PATTERN_FIRST) or (a == "-x" and exe == "zip"):
            skip_next = True
            continue
        if a.startswith("-"):
            name, eq, value = a.partition("=")
            if eq and FILE_FLAG.search(name) and name != "--env-file":
                out.append(value.lstrip("@"))
            continue
        if not a:
            continue  # sed -i ''
        if pattern_pending:
            pattern_pending = False
            continue
        out.append(a.split("=", 1)[1].lstrip("@") if "=" in a else a.lstrip("@"))
    return out


def check_paths(exe, args, session):
    if exe in PATH_SAFE:
        return
    if exe in ("sed", "gsed"):  # sed reads and writes files from its script: r .env
        for a in args:
            for path in re.findall(r"(?:^|[;{\s\d/])[rRwW]\s+([^\s;}]+)", a):
                if session.secret_path(path):
                    block("`%s` là path forbidden (secret) — không đọc/ghi qua script sed." % path)
    if exe in PATTERN_FIRST:
        for i, a in enumerate(args):
            name, eq, value = a.partition("=")
            value = value if eq else (args[i + 1] if i + 1 < len(args) else "")
            if name in ("-g", "--glob", "--iglob", "--include") and glob_hits_secret(value.lstrip("!")) and not value.startswith("!"):
                block("glob `%s` chọn đúng file secret — không đọc/in nội dung." % value)
    if exe in ("grep", "egrep", "fgrep") and any(re.match(r"^(-[a-zA-Z]*[rR]|--recursive|--dereference-recursive)", a) for a in args) and not any(a.startswith(("--exclude", "--include")) for a in args):
        # grep does not honour .gitignore: from the repo root it reads .env and the settings file with the tokens
        operands = operand_paths(exe, args)
        for target in operands or ["."]:
            root = session.abspath(target)
            if any(os.path.exists(os.path.join(root, f)) for f in (".env", os.path.join(".claude", "settings.local.json"))):
                block("`grep -r` trên `%s` đọc cả file secret — dùng `rg` hoặc Grep tool, hoặc thêm `--exclude`." % target)
    paths = operand_paths(exe, args)
    if exe in COPIERS:
        paths = paths[:-1]
    for path in paths:
        hits = [path]
        if any(ch in path for ch in "*?[") and "\n" not in path:
            hits = glob.glob(os.path.join(session.here, os.path.expanduser(path)), recursive=True)[:200]
        for hit in hits:
            if session.secret_path(hit):
                block("`%s` là path forbidden (secret) — không đọc/in/sao chép nội dung." % hit)


def check_mutators(exe, args, session):
    """What a role may not do with Edit/Write it may not do with `sed -i` or `tee` either."""
    if not session.role:
        return
    if exe in ("sed", "gsed", "perl", "ruby") and any(re.match(r"^-[a-zA-Z]*i", a) for a in args):
        targets = [a for a in args if a and not a.startswith("-")][1:]  # the first is the script; sed -i '' has an empty suffix
    elif exe in ("cp", "mv", "install", "ln"):
        targets = [a for a in args if not a.startswith("-")][-1:]
    elif exe == "dd":
        targets = [a[3:] for a in args if a.startswith("of=")]
    elif exe in MUTATORS:
        targets = [a for a in args if not a.startswith("-")]
    else:
        return
    for path in targets:
        reason = session.write_denied(path)
        if reason:
            block(reason)


def check_redirects(redirs, session):
    for op, target in redirs:
        if op in ("<&", ">&") and (target.isdigit() or target == "-"):
            continue
        if session.secret_path(target):
            block("`%s` là path forbidden (secret) — không đọc/ghi qua redirect." % target)
        if op != "<":
            reason = session.write_denied(target)
            if reason:
                block(reason)


def check_code(code, session):
    code = code.replace(LITERAL, "$")
    for pattern, reason in CODE_BANNED:
        if pattern.search(code):
            block(reason)
    scope = session.scope() or session.scope(session.cwd)
    if scope:
        names = "|".join(re.escape(b) for b in sorted(scope.protected))
        if names and re.search(r"\bgit\b[^\n]*\bpush\b[^\n]*[\s\"',:/](%s)\b" % names, code):
            block("push thẳng vào nhánh protected bị cấm.")
    if not session.hard_only:
        for m in CODE_STRING.finditer(code):
            if session.secret_path(m.group(1)):
                block("`%s` là path forbidden (secret) — không đọc nội dung." % m.group(1))


def check_print(exe, args, cmd, session):
    if exe in ("echo", "printf", "print"):
        hit = next((m.group(1) for a in args for m in [SECRET_VAR.search(a)] if m), None)
        consumer = [expand(w, session) for w in cmd.next.words] if cmd.next else []
        if hit and not any(w in ("--password-stdin", "--with-token", "set-secret") for w in consumer):
            block("không in giá trị secret `$%s` ra output." % hit)
    if exe == "printenv" and (not args or SECRET_VAR.search("$" + args[-1])):
        block("`printenv` in ra secret trong env — test sự tồn tại bằng `[ -n \"${VAR:-}\" ]`.")
    if (exe == "set" and not args) or (exe in ("export", "declare", "typeset") and not [a for a in args if not a.startswith("-")]) \
            or (exe in ("declare", "typeset") and "-p" in args and any(SECRET_VAR.search("$" + a) for a in args)) \
            or (exe == "compgen" and "-e" in args):
        block("`%s` in ra toàn bộ env (có secret)." % exe)


# ── one command ───────────────────────────────────────────────────────────────

def expand(word, session):
    if "$" not in word:
        return word

    def default(m):
        if SECRET_VAR.match("$" + m.group(1)):
            return m.group(0)
        return session.vars.get(m.group(1), m.group(2))

    def sub(m):
        name = m.group(1) or m.group(2)
        if name in session.vars:
            return session.vars[name]
        if name == "HOME":
            return os.path.expanduser("~")
        if name == "PWD" and session.here_known:
            return session.here
        return m.group(0)
    return VAR_REF.sub(sub, VAR_DEFAULT.sub(default, word))


def expand_braces(word, limit=64):
    m = BRACES.search(word)
    if not m:
        return [word]
    out = []
    for part in m.group(1).split(","):
        out += expand_braces(word[: m.start()] + part + word[m.end() :], limit)
        if len(out) >= limit:
            break
    return out[:limit]


def strip_wrapper(exe, args):
    flags, positionals = WRAPPERS[exe]
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--":
            i += 1
            break
        if a.startswith("-") and len(a) > 1:
            i += 2 if a in flags else 1
        elif exe in ("env", "sudo", "doas") and ASSIGN.match(a):
            i += 1
        else:
            break
    return args[i + positionals :]


def run_script_file(path, session):
    absolute = session.abspath(path)
    try:
        if os.path.getsize(absolute) > 256 * 1024:
            return
        with open(absolute, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return
    was, session.hard_only = session.hard_only, True
    check_bash(text, session)
    session.hard_only = was


def upstream_text(cmd, session):
    """What echo/printf/cat feed into this command through a pipe, as far as it can be read."""
    prev = cmd.prev
    if not prev or not prev.words:
        return None
    words = [expand(w, session) for w in prev.words]
    if name_of(words[0]) not in ("echo", "printf", "print", "cat"):
        return None
    return " ".join(w for w in words[1:] if not w.startswith("-")) + "\n" + "\n".join(prev.bodies + prev.herestrings)


def check_shell(args, cmd, session):
    i = 0
    while i < len(args):
        a = args[i]
        if a in SHELL_VALUE_FLAGS:
            i += 2
        elif a.startswith("-") and len(a) > 1:
            if not a.startswith("--") and "c" in a[1:]:
                if i + 1 < len(args):
                    check_bash(args[i + 1], session)
                return
            i += 1
        else:
            if a.startswith(("<(", "$(", "`")):  # `bash <(echo 'gh pr merge 1')`: its output is the script
                check_code(a, session)
            else:
                run_script_file(a, session)
            return
    for text in cmd.bodies + cmd.herestrings:
        check_bash(text, session)
    text = upstream_text(cmd, session)
    if text:
        check_bash(text, session)


def check_interpreter(args, cmd, session):
    for i, a in enumerate(args):
        if CODE_FLAG.match(a) and i + 1 < len(args):
            check_code(args[i + 1], session)
        m = CODE_ATTACHED.match(a)
        if m:
            check_code(m.group(1) or m.group(2), session)
    for text in cmd.bodies + cmd.herestrings:
        check_code(text, session)


def check_settings_tool(args, session):
    if len(args) >= 2 and args[0] in ("set", "set-secret"):
        if session.role:
            block("subagent không sửa settings local.")
        if args[0] == "set" and afconfig.settings_key_locked(args[1], args[2] if len(args) > 2 else ""):
            block("`%s` có thể tắt hook hoặc plugin — người sửa tay nếu thật sự cần." % args[1])


def glob_hits_secret(pattern):
    return pattern not in ("*", "**") and any(fnmatch.fnmatch(p, pattern.rsplit("/", 1)[-1]) for p in SECRET_PROBES)


def check_find(args, session):
    named = [args[i + 1] for i, a in enumerate(args[:-1]) if a in ("-name", "-iname", "-path")]
    return any(session.secret_path(n) or glob_hits_secret(n) for n in named)


def change_dir(exe, args, session):
    if exe == "popd":
        if session.dirs:
            session.here = session.dirs.pop()
        return
    target = next((a for a in args if not a.startswith("-") or a == "-"), None)
    if target is None:
        target = os.path.expanduser("~")
    if DYNAMIC.search(target):
        session.here_known = False
        return
    if exe == "pushd":
        session.dirs.append(session.here)
    if target == "-":
        session.here, session.previous = session.previous, session.here
    else:
        session.previous, session.here = session.here, session.abspath(target)


def run_argv(argv, cmd, session):
    if not argv:
        return
    if name_of(argv[0]) == "gh" and any(DYNAMIC.search(a) for a in argv[1:3]):
        block("lệnh con của gh không đọc được trước khi chạy — ghi thẳng.")
    if DYNAMIC.search(argv[0]):  # `$G push --force`: the command itself is unknown until it runs
        if any(DYNAMIC_RISK.search(a) for a in argv[1:]):
            block("tên lệnh `%s` không đọc được trước khi chạy — ghi thẳng tên lệnh." % argv[0])
        return
    exe = name_of(argv[0])
    args = argv[1:]
    if exe in WRAPPERS:
        if exe == "env" and ("-S" in args or "--split-string" in args):
            flag = "-S" if "-S" in args else "--split-string"
            pos = args.index(flag)
            if pos + 1 < len(args):
                check_bash(" ".join(args[pos + 1 :]), session)
            return
        inner = strip_wrapper(exe, args)
        if exe == "env" and not inner and session.scope():
            block("`env` in ra secret trong env — test sự tồn tại bằng `[ -n \"${VAR:-}\" ]`.")
        if exe in ("xargs", "parallel") and inner:
            text = upstream_text(cmd, session)
            if text:
                inner = inner + text.split()
            if cmd.prev and cmd.prev.words and name_of(cmd.prev.words[0]) == "find" and not session.hard_only and check_find(cmd.prev.words[1:], session):
                block("không đọc nội dung file forbidden (secret) qua `find | xargs`.")
        run_argv(inner, cmd, session)
        return
    if exe in SHELLS:
        check_shell(args, cmd, session)
        return
    if exe == "eval":
        check_bash(" ".join(args), session)
        return
    if exe == "trap" and args and not args[0].startswith("-"):
        check_bash(args[0], session)
        return
    if exe in EXEC_RUNNERS:
        first = next((i for i, a in enumerate(args) if not a.startswith("-")), None)  # the program's own flags stay
        if first is not None and "" in EXEC_RUNNERS[exe]:
            run_argv(args[first:], cmd, session)
        elif first is not None and args[first] in EXEC_RUNNERS[exe]:
            inner = args[first + 1 :]
            run_argv(inner[1:] if inner[:1] == ["--"] else inner, cmd, session)
    if exe in ("source", ".") and args:
        if args[0].startswith(("<(", "$(", "`")):
            check_code(args[0], session)
        else:
            run_script_file(args[0], session)
        return
    if exe == "for" and "in" in args:  # judge the loop by its most dangerous value
        pos = args.index("in")
        items = args[pos + 1 :]
        if pos == 1 and items:
            session.vars[args[0]] = next((v for v in items if session.secret_path(v)), items[0])
        return
    if INTERPRETERS.match(exe):
        check_interpreter(args, cmd, session)
    if exe in ("awk", "gawk") and args:
        check_code(next((a for a in args if not a.startswith("-")), ""), session)
    if exe in ("find", "fd"):
        for i, a in enumerate(args):
            if a in ("-exec", "-execdir", "-ok", "-okdir", "-x", "--exec", "-X", "--exec-batch"):
                inner = args[i + 1 :]
                for end in (";", "+"):
                    if end in inner:
                        inner = inner[: inner.index(end)]
                if not session.hard_only and check_find(args[:i], session):
                    block("không đọc nội dung file forbidden (secret) qua `find -exec`.")
                run_argv(inner, cmd, session)
                break
    if exe in ("cd", "pushd", "popd"):
        change_dir(exe, args, session)
        return
    if exe == "git":
        check_git(argv, session)
    scope = session.scope() or session.scope(session.cwd)
    if scope:
        if exe == "gh":
            check_gh(args, session, scope, cmd)
        elif exe in ("curl", "wget"):
            check_http_client(exe, args, scope)
        if not session.hard_only:
            check_print(exe, args, cmd, session)
    if exe == "agentflow-settings":
        check_settings_tool(args, session)
    if not session.hard_only and exe not in ("git", "gh"):
        check_paths(exe, args, session)
        check_mutators(exe, args, session)


def check_cmd(cmd, session):
    if cmd.mark == "push":
        session.stack.append((session.here, session.here_known, dict(session.vars), list(session.dirs), session.previous, dict(session.branches)))
        return
    if cmd.mark == "pop":
        if session.stack:
            session.here, session.here_known, session.vars, session.dirs, session.previous, session.branches = session.stack.pop()
        return
    words = []
    for raw, quoted in zip(cmd.words, cmd.quoted):
        value = expand(raw, session)
        # An unquoted variable holding several words becomes several arguments: X="push --force"; git $X
        parts = value.split() if value != raw and not quoted and not ASSIGN.match(raw) else [value]
        words += [w for part in parts or [""] for w in (expand_braces(part) if not quoted else [part])]
    i = 0
    while i < len(words) and ASSIGN.match(words[i]):
        i += 1
    argv = words[i:]
    for word in words[:i] if argv else []:  # GIT_PAGER='gh pr merge 1' git log
        m = ASSIGN.match(word)
        if m.group(1) in EXEC_ENV:
            check_bash(m.group(3), session)
    for word in words:
        m = ASSIGN.match(word)
        if m and GIT_CONFIG_ENV.match(m.group(1)) and session.scope():
            block("không cấu hình git qua biến môi trường (`%s`) — guard không đọc được cấu hình đó." % m.group(1))
    if not argv or (name_of(argv[0]) in ("export", "readonly", "declare", "typeset", "local") and len(argv) > 1 and "-p" not in argv):
        for word in words[i + 1 :] if argv else words:
            m = ASSIGN.match(word)
            if m:
                session.vars[m.group(1)] = (session.vars.get(m.group(1), "") if m.group(2) else "") + m.group(3)
    redirs = [(op, expand(t, session)) for op, t in cmd.redirs]
    if not session.hard_only:
        check_redirects(redirs, session)
        exe = name_of(argv[0]) if argv else ""
        if not exe.startswith("agentflow-") and exe != "curl" and not {"--password-stdin", "--with-token"} & set(argv):
            for text in cmd.herestrings:
                m = SECRET_VAR.search(expand(text, session))
                if m:
                    block("không đưa secret `$%s` qua here-string." % m.group(1))
    run_argv(argv, cmd, session)


def check_bash(command, session):
    session.depth += 1
    if session.depth > 8:
        block("lệnh lồng quá sâu, guard không đọc được — tách thành lệnh đơn giản.")
    command = command.replace(LITERAL, "$")
    if "disableAllHooks" in command and "settings" in command:
        block("không tắt hook qua settings.")
    try:
        commands = shellparse.commands(command)
    except (ValueError, RecursionError):
        block("lệnh lồng quá sâu, guard không đọc được — tách thành lệnh đơn giản.")
    for cmd in commands:
        check_cmd(cmd, session)
    session.depth -= 1


# ── other tools ───────────────────────────────────────────────────────────────

def strings_in(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for v in node.values():
            yield from strings_in(v)
    elif isinstance(node, list):
        for v in node:
            yield from strings_in(v)


def check_secret_value(ti):
    for text in strings_in(ti):
        if afconfig.SECRET_VALUE.search(text):
            block("tham số chứa giá trị giống secret thật (token/private key) — bỏ khỏi nội dung; secret nằm trong env.")


def check_mcp(tool, ti, session):
    low = tool.lower()
    if "actions_run_trigger" in low or "run_workflow" in low or "rerun_" in low:
        block(MSG_DISPATCH)
    if "merge_pull_request" in low or "auto_merge" in low:
        block(MSG_MERGE)
    if "delete_branch" in low or "delete_ref" in low or "update_ref" in low:
        block(MSG_REF)
    if "pull_request_review" in low and str(ti.get("event", "")).upper() == "APPROVE":
        block(MSG_APPROVE)
    for key in MCP_PATH_KEYS:  # another server's file tools reach the same secrets
        if isinstance(ti.get(key), str) and session.secret_path(ti[key]):
            block("`%s` là path forbidden (secret) — agent không đọc/sửa." % ti[key])
    if MCP_COMMAND_TOOL.search(low.rsplit("__", 1)[-1]):
        for key in ("command", "cmd"):
            if isinstance(ti.get(key), str):
                check_bash(ti[key], session)
    role = session.role
    if any(k in low for k in ("create_or_update_file", "push_files", "delete_file")):
        if role in ("qc", "reviewer"):
            block("%s không ghi file lên GitHub." % role.upper())
        branch = ti.get("branch")
        scope = session.scope(session.cwd)
        if scope and (not branch or branch in scope.protected or branch == scope.staging):
            block("ghi file thẳng lên nhánh protected `%s` qua MCP bị cấm." % (branch or "default branch"))
    if "update_pull_request" in low and "branch" not in low and ti.get("draft") is False and role in ("dev", "reviewer"):
        block(MSG_UNDRAFT)
    if "create_pull_request" in low and role in ("qc", "reviewer"):
        block("chỉ DEV mở PR.")
    if "create_pull_request" in low and role == "dev" and ti.get("draft") is not True:
        block(MSG_DRAFT)


def check_write(path, ti, session):
    if session.role == "qc":
        block("QC không sửa file.")
    reason = session.write_denied(path)
    if reason:
        block(reason)
    if re.search(r"/\.claude/settings(\.local)?\.json$", session.abspath(path)) and any("disableAllHooks" in t for t in strings_in(ti)):
        block("không tắt hook qua settings.")


def evaluate(data):
    tool = data.get("tool_name") or ""
    ti = data.get("tool_input") or {}
    cwd = data.get("cwd") or os.getcwd()
    session = Session(cwd, role_of(data))

    if tool in ("Bash", "Monitor"):
        check_bash(ti.get("command") or "", session)
        return
    if tool in ("Edit", "Write", "MultiEdit", "NotebookEdit", "Read", "Grep"):
        path = ti.get("file_path") or ti.get("notebook_path") or ti.get("path") or ""
        if session.secret_path(path) or (tool == "Grep" and ti.get("glob") and (session.secret_path(os.path.join(path or cwd, ti["glob"])) or (session.scope(cwd) and glob_hits_secret(ti["glob"])))):
            block("`%s` là path forbidden (secret) — agent không đọc/sửa. Cần đổi giá trị → báo người." % (path or ti.get("glob")))
        if tool in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
            if session.scope(parent_dir(session.abspath(path))) or session.scope(cwd):
                check_secret_value(ti)
                check_write(path, ti, session)
        return
    if tool.startswith("mcp__") and session.scope(cwd):
        check_secret_value(ti)
        check_mcp(tool, ti, session)


def main():
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return
    try:
        evaluate(data)
    except SystemExit:
        raise
    except Exception as exc:  # a guard bug must not brick the session, but must not wave a risky command through either
        command = str((data.get("tool_input") or {}).get("command") or "")
        if RISKY_TEXT.search(command):
            block("không đọc được lệnh này (%s) — tách thành lệnh đơn giản hơn." % type(exc).__name__)
        sys.stderr.write("AgentFlow guard internal error (allowed): %s\n" % exc)


if __name__ == "__main__":
    main()
