"""Shared helpers for AgentFlow scripts: config loading, forbidden-path matching, git info.

Stdlib only. PyYAML is used when importable; otherwise a parser for the YAML subset that
agentflow.yaml uses (block maps/lists, flow [..] and {..}, quoted scalars, comments).
"""

import functools
import json
import os
import re
import subprocess

CONFIG_NAME = "agentflow.yaml"
SCHEMA = 4

DEFAULT_FORBIDDEN = [".claude/settings.local.json", "**/.env", "**/.env.*", "**/*.pem", "**/*.key", "**/*.p12", "**/*.pfx", "**/*.jks", "**/*.keystore",
                     "**/.netrc", "**/.git-credentials", "**/id_rsa", "**/id_ed25519"]
FORBIDDEN_EXEMPT_SUFFIXES = (".example", ".sample", ".template", ".dist")
HOME_SECRETS = (".ssh/", ".aws/credentials", ".config/gh/hosts.yml", ".claude/.credentials.json", ".docker/config.json")

STAGES = ["backlog", "ready", "in_progress", "in_review", "in_qc", "ready_to_merge", "done"]
LABEL_KEYS = ["agent", "blocked", "needs_info", "changes_requested", "qc_failed", "qc_manual", "deploying"]
TOP_KEYS = {"schema", "lang", "board", "classify", "types", "labels", "git", "surfaces", "forbidden", "design", "staging", "people", "run", "notify"}
NOTIFY_EVENTS = {"blocked", "needs_info", "qc_manual", "ready_to_merge"}
SECRET_VALUE = re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|\b\d{8,10}:[A-Za-z0-9_-]{35}\b"
                          r"|\bxox[abprs]-[A-Za-z0-9-]{10,}|\bAKIA[0-9A-Z]{16}\b|-----BEGIN [A-Z ]*PRIVATE KEY-----")


def _strip_comment(line):
    out, quote = [], None
    for i, ch in enumerate(line):
        if quote:
            out.append(ch)
            if ch == quote:
                quote = None
        elif ch in "\"'" and (i == 0 or line[i - 1] in " \t[{,:"):
            quote = ch
            out.append(ch)
        elif ch == "#" and (i == 0 or line[i - 1] in " \t"):
            break
        else:
            out.append(ch)
    return "".join(out).rstrip()


def _split_flow(text):
    parts, buf, depth, quote = [], [], 0, None
    for ch in text:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
        elif ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append("".join(buf).strip())
            buf = []
            continue
        buf.append(ch)
    tail = "".join(buf).strip()
    if tail:
        parts.append(tail)
    return [p for p in parts if p]


def _split_key(text):
    quote = None
    for i, ch in enumerate(text):
        if quote:
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
        elif ch == ":" and (i + 1 == len(text) or text[i + 1] in " \t"):
            return _scalar(text[:i]), text[i + 1:]
    return None, None


def _scalar(raw):
    s = raw.strip()
    if s == "":
        return None
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        inner = s[1:-1]
        return inner.replace('\\"', '"').replace("\\\\", "\\") if s[0] == '"' else inner.replace("''", "'")
    if s.startswith("[") and s.endswith("]"):
        return [_scalar(p) for p in _split_flow(s[1:-1])]
    if s.startswith("{") and s.endswith("}"):
        out = {}
        for part in _split_flow(s[1:-1]):
            key, rest = _split_key(part)
            if key is None:
                raise ValueError("bad flow mapping entry: %r" % part)
            out[key] = _scalar(rest)
        return out
    low = s.lower()
    if low in ("null", "~"):
        return None
    if low == "true":
        return True
    if low == "false":
        return False
    if re.fullmatch(r"-?\d+", s):
        return int(s)
    if re.fullmatch(r"-?\d+\.\d+", s):
        return float(s)
    return s


def _is_list_item(content):
    return content == "-" or content.startswith("- ")


def _parse_block(lines, i, indent):
    if _is_list_item(lines[i][1]):
        out = []
        while i < len(lines) and lines[i][0] == indent and _is_list_item(lines[i][1]):
            item = lines[i][1][1:].strip()
            i += 1
            if item == "":
                if i < len(lines) and lines[i][0] > indent:
                    value, i = _parse_block(lines, i, lines[i][0])
                    out.append(value)
                else:
                    out.append(None)
                continue
            key, _ = _split_key(item)
            if key is not None and item[0] not in "[{\"'":
                sub = [(indent + 2, item)]
                while i < len(lines) and lines[i][0] > indent:
                    sub.append(lines[i])
                    i += 1
                value, _ = _parse_block(sub, 0, indent + 2)
                out.append(value)
            else:
                out.append(_scalar(item))
        return out, i
    out = {}
    while i < len(lines) and lines[i][0] == indent:
        key, rest = _split_key(lines[i][1])
        if key is None:
            raise ValueError("expected 'key: value' at: %r" % lines[i][1])
        i += 1
        if rest.strip() != "":
            out[key] = _scalar(rest)
        elif i < len(lines) and lines[i][0] > indent:
            out[key], i = _parse_block(lines, i, lines[i][0])
        elif i < len(lines) and lines[i][0] == indent and _is_list_item(lines[i][1]):
            out[key], i = _parse_block(lines, i, indent)
        else:
            out[key] = None
    if i < len(lines) and lines[i][0] > indent:
        raise ValueError("unexpected indentation at: %r" % lines[i][1])
    return out, i


def parse_yaml(text):
    try:
        import yaml  # type: ignore

        return yaml.safe_load(text) or {}
    except ImportError:
        pass
    lines = []
    for raw in text.splitlines():
        if "\t" in raw[: len(raw) - len(raw.lstrip())]:
            raise ValueError("tabs are not allowed for indentation")
        content = _strip_comment(raw)
        if content.strip():
            lines.append((len(content) - len(content.lstrip(" ")), content.strip()))
    if not lines:
        return {}
    value, _ = _parse_block(lines, 0, lines[0][0])
    return value


def git(args, cwd=None, timeout=5):
    try:
        res = subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    return res.stdout.strip() if res.returncode == 0 else None


@functools.lru_cache(maxsize=64)
def _toplevel(cwd):
    return git(["rev-parse", "--show-toplevel"], cwd=cwd)


def repo_root(cwd=None):
    return _toplevel(cwd or os.getcwd())


def main_root(cwd=None):
    """Root of the main checkout, also when `cwd` is inside a linked worktree."""
    common = git(["rev-parse", "--git-common-dir"], cwd=cwd)
    if not common:
        return None
    common = os.path.realpath(os.path.join(cwd or os.getcwd(), common))
    return os.path.dirname(common) if os.path.basename(common) == ".git" else None


def default_branch(cwd=None):
    ref = git(["symbolic-ref", "--short", "refs/remotes/origin/HEAD"], cwd=cwd)
    return ref.split("/", 1)[1] if ref and "/" in ref else None


def load_config(root):
    """agentflow.yaml of the repo. The main checkout's copy wins over a worktree's: an agent may write in its worktree,
    and what it writes there must not change what the guard enforces."""
    main = main_root(root)
    for path in ([os.path.join(main, CONFIG_NAME)] if main else []) + [os.path.join(root, CONFIG_NAME)]:
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as fh:
                return parse_yaml(fh.read()) or {}
    return None


def settings_path(cwd=None):
    """.claude/settings.local.json lives in the main checkout only; worktrees share it."""
    root = main_root(cwd) or repo_root(cwd) or cwd or os.getcwd()
    return os.path.join(root, ".claude", "settings.local.json")


def settings_key_locked(key, value):
    """Keys of settings.local.json that could switch the guard off."""
    head = key.split(".", 1)[0]
    if head in ("disableAllHooks", "hooks"):
        return True
    return head == "enabledPlugins" and "agentflow" in key and str(value).strip().lower() == "false"


def validate_config(cfg):
    """Shape problems of a parsed agentflow.yaml, no network: list of (level, message), level ∈ fail | warn."""
    out = []

    def fail(msg):
        out.append(("fail", msg))

    def warn(msg):
        out.append(("warn", msg))

    def positive_int(section, key):
        value = (cfg.get(section) or {}).get(key)
        if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 1):
            fail("%s.%s phải là số nguyên ≥ 1 (đang là %r)" % (section, key, value))

    for key in cfg:
        if key not in TOP_KEYS:
            warn("key lạ `%s` — plugin không đọc" % key)
    board = cfg.get("board") or {}
    status = board.get("status") or {}
    names = [status.get(s) for s in STAGES]
    for stage, name in zip(STAGES, names):
        if not name:
            fail("board.status.%s chưa map" % stage)
    if len({n for n in names if n}) != len([n for n in names if n]):
        fail("board.status: hai stage cùng trỏ vào một cột — routing sẽ sai")
    labels = cfg.get("labels") or {}
    for key in LABEL_KEYS:
        if not labels.get(key):
            fail("labels.%s chưa khai báo" % key)
    if cfg.get("classify") not in ("issue-type", "label"):
        fail("classify phải là issue-type hoặc label (đang là %r)" % cfg.get("classify"))
    if not cfg.get("types"):
        fail("types trống — DEV không dựng được tên nhánh")
    gitc = cfg.get("git") or {}
    if "{issue}" not in str(gitc.get("branch") or ""):
        fail("git.branch phải có {issue} — một ticket một nhánh")
    staging = staging_branch(cfg)
    if not staging:
        fail("staging.branch chưa khai báo — bắt buộc")
    elif staging == gitc.get("base"):
        fail("staging.branch = %r trùng git.base — PR phải nhắm nhánh khác" % staging)
    if staging and staging in as_list(gitc.get("protected")):
        warn("git.protected có nhánh staging `%s` — bị bỏ qua, REVIEWER phải push được vào đó" % staging)
    for key, surface in (cfg.get("surfaces") or {}).items():
        if not isinstance(surface, dict) or not surface.get("path"):
            fail("surfaces.%s thiếu path" % key)
    for key in ("parallel", "max_tasks", "max_review_rounds", "max_qc_rounds"):
        positive_int("run", key)
    positive_int("staging", "timeout_min")
    models = (cfg.get("run") or {}).get("models") or {}
    if not isinstance(models.get("dev") or {}, dict) or not (models.get("dev") or {}).get("default"):
        fail("run.models.dev.default chưa khai báo")
    for event in as_list((cfg.get("notify") or {}).get("events")):
        if event not in NOTIFY_EVENTS:
            fail("notify.events có %r — chỉ nhận: %s" % (event, ", ".join(sorted(NOTIFY_EVENTS))))
    return out


def as_list(value):
    """Config lists written as a bare scalar (`protected: staging`) still mean one item."""
    if value is None:
        return []
    return [value] if isinstance(value, str) else list(value)


def staging_branch(cfg):
    return str(((cfg or {}).get("staging") or {}).get("branch") or "") or None


def protected_branches(cfg, root):
    """Never pushed to by agents. The staging branch is the one exception (REVIEWER merges into it),
    unless a misconfigured repo also uses it as base."""
    git_cfg = (cfg or {}).get("git") or {}
    names = {str(b) for b in as_list(git_cfg.get("protected"))}
    names.discard(staging_branch(cfg))
    base = git_cfg.get("base") or default_branch(root)
    default = default_branch(root)
    names |= {b for b in (base, default) if b} or {"main", "master"}  # origin/HEAD unset: the likely base must not stay open
    return names - {staging_branch(cfg)}


@functools.lru_cache(maxsize=128)
def _glob_to_regex(pattern):
    out, i = [], 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("^" + "".join(out) + "$", re.I)  # .ENV opens .env on case-insensitive filesystems


def forbidden_patterns(cfg):
    extra = [p for p in as_list((cfg or {}).get("forbidden")) if isinstance(p, str) and p.strip()]
    pats = []
    for p in DEFAULT_FORBIDDEN + extra:
        p = p.strip()
        if p.startswith("./"):
            p = p[2:]
        if p.endswith("/"):
            p += "**"
        pats.append(p)
    return pats


def is_forbidden(path, root, cfg):
    """True when `path` (absolute or relative to root) matches a forbidden glob. Outside any repo only the
    path-free globs apply, plus the credential files under the home directory."""
    if not path:
        return False
    absolute = os.path.realpath(path if os.path.isabs(path) else os.path.join(root, path))
    home = os.path.realpath(os.path.expanduser("~"))
    if absolute.startswith(home + os.sep) and absolute[len(home) + 1 :].startswith(HOME_SECRETS):
        return True
    base = os.path.basename(absolute)
    if base.endswith(FORBIDDEN_EXEMPT_SUFFIXES):
        return False
    probe = os.path.dirname(absolute)
    while probe and not os.path.isdir(probe) and probe != os.path.dirname(probe):
        probe = os.path.dirname(probe)
    own_root = repo_root(probe) if probe else None  # a worktree is its own root
    rel = os.path.relpath(absolute, os.path.realpath(own_root or root)).replace(os.sep, "/")
    inside = not rel.startswith("..")
    for pat in forbidden_patterns(cfg):
        if inside:
            target = rel if "/" in pat else base
        elif pat.startswith("**/") and "/" not in pat[3:]:
            target = base
            pat = pat[3:]
        else:
            continue
        if _glob_to_regex(pat).match(target):
            return True
    return False


def parse_board_url(url):
    m = re.match(r"^https://github\.com/(orgs|users)/([^/]+)/projects/(\d+)", url or "")
    if not m:
        return None
    return {"owner_type": "org" if m.group(1) == "orgs" else "user", "owner": m.group(2), "number": int(m.group(3))}


_SSL = None


def ssl_context():
    """python.org builds on macOS often ship without a CA bundle; fall back to the system one."""
    global _SSL
    if _SSL is None:
        import ssl

        _SSL = ssl.create_default_context()
        if not _SSL.get_ca_certs():
            candidates = []
            try:
                import certifi  # type: ignore

                candidates.append(certifi.where())
            except ImportError:
                pass
            candidates += ["/etc/ssl/cert.pem", "/etc/ssl/certs/ca-certificates.crt", "/etc/pki/tls/certs/ca-bundle.crt"]
            for path in candidates:
                if os.path.isfile(path):
                    _SSL = ssl.create_default_context(cafile=path)
                    break
    return _SSL


_USE_CURL = False


def request(method, url, headers=None, data=None, timeout=30):
    """HTTP request → (status, lowercase headers, body). urllib first; on TLS trust failure (python.org builds,
    corporate proxies whose CA lives only in the OS keychain) fall back to the system curl.
    Header values are passed to curl on stdin (-K -), so secrets never appear in argv."""
    global _USE_CURL
    import urllib.error
    import urllib.request

    headers = headers or {}
    if not _USE_CURL:
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=ssl_context()) as res:
                return res.status, {k.lower(): v for k, v in res.headers.items()}, res.read()
        except urllib.error.HTTPError as err:
            return err.code, {k.lower(): v for k, v in err.headers.items()}, err.read()
        except urllib.error.URLError as err:
            if "CERTIFICATE" not in str(err.reason).upper():
                raise RuntimeError("không kết nối được (%s)" % err.reason)
            _USE_CURL = True
    import tempfile

    def q(v):
        return v.replace("\\", "\\\\").replace('"', '\\"')
    config = "".join('header = "%s: %s"\n' % (q(k), q(v)) for k, v in headers.items())
    config += 'url = "%s"\n' % q(url)
    with tempfile.TemporaryDirectory() as tmp:
        hfile, bfile, dfile = (os.path.join(tmp, n) for n in ("h", "b", "d"))
        args = ["curl", "-sS", "-K", "-", "-X", method, "-D", hfile, "-o", bfile, "-w", "%{http_code}", "--max-time", str(timeout)]
        if data is not None:
            with open(dfile, "wb") as fh:
                fh.write(data)
            args += ["--data-binary", "@" + dfile]
        try:
            res = subprocess.run(args, input=config, capture_output=True, text=True, timeout=timeout + 5)
        except (OSError, subprocess.SubprocessError) as exc:
            raise RuntimeError("curl không chạy được (%s)" % type(exc).__name__)
        if res.returncode != 0:
            raise RuntimeError("không kết nối được (curl exit %d)" % res.returncode)
        hdrs = {}
        if os.path.isfile(hfile):
            blocks = open(hfile, encoding="latin-1").read().strip().split("\r\n\r\n")
            for line in blocks[-1].splitlines()[1:]:
                k, _, v = line.partition(":")
                hdrs[k.strip().lower()] = v.strip()
        body = open(bfile, "rb").read() if os.path.isfile(bfile) else b""
        return int(res.stdout.strip() or 0), hdrs, body


def github_token(cwd=None):
    """GitHub token, first hit wins: env.GITHUB_TOKEN in the repo's .claude/settings.local.json (read
    directly — independent of when Claude Code applies settings env), process GITHUB_TOKEN / GH_TOKEN,
    then `gh auth token`. Returns "" when nothing is configured."""
    for start in (cwd, os.environ.get("CLAUDE_PROJECT_DIR"), os.getcwd()):
        if not start:
            continue
        try:
            with open(settings_path(start), encoding="utf-8") as fh:
                tok = ((json.load(fh) or {}).get("env") or {}).get("GITHUB_TOKEN")
            if tok:
                return tok
        except (OSError, ValueError):
            continue
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if tok:
        return tok
    try:
        return subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""
