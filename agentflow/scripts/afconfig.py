"""Shared helpers for AgentFlow scripts: config loading, forbidden-path matching, git info.

Stdlib only. PyYAML is used when importable; otherwise a parser for the YAML subset that
agentflow.yaml uses (block maps/lists, flow [..] and {..}, quoted scalars, comments).
"""

import os
import re
import subprocess

CONFIG_NAME = "agentflow.yaml"
SCHEMA = 4

DEFAULT_FORBIDDEN = [".claude/settings.local.json", "**/.env", "**/.env.*", "**/*.pem", "**/*.key", "**/*.p12", "**/*.jks", "**/*.keystore"]
FORBIDDEN_EXEMPT_SUFFIXES = (".example", ".sample", ".template", ".dist")

STAGES = ["backlog", "ready", "in_progress", "in_review", "in_qc", "ready_to_merge", "done"]


def _strip_comment(line):
    out, quote = [], None
    for i, ch in enumerate(line):
        if quote:
            out.append(ch)
            if ch == quote:
                quote = None
        elif ch in "\"'":
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


def repo_root(cwd=None):
    return git(["rev-parse", "--show-toplevel"], cwd=cwd)


def default_branch(cwd=None):
    ref = git(["symbolic-ref", "--short", "refs/remotes/origin/HEAD"], cwd=cwd)
    return ref.split("/", 1)[1] if ref and "/" in ref else None


def load_config(root):
    path = os.path.join(root, CONFIG_NAME)
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return parse_yaml(fh.read()) or {}


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
    if base:
        names.add(base)
    return names


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
    return re.compile("^" + "".join(out) + "$")


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
    """True when `path` (absolute or relative to root) matches a forbidden glob."""
    if not path:
        return False
    absolute = os.path.realpath(path if os.path.isabs(path) else os.path.join(root, path))
    probe = os.path.dirname(absolute)
    while probe and not os.path.isdir(probe) and probe != os.path.dirname(probe):
        probe = os.path.dirname(probe)
    own_root = repo_root(probe) if probe else None  # a worktree is its own root
    rel = os.path.relpath(absolute, os.path.realpath(own_root or root))
    if rel.startswith(".."):
        return False
    rel = rel.replace(os.sep, "/")
    base = rel.rsplit("/", 1)[-1]
    if base.endswith(FORBIDDEN_EXEMPT_SUFFIXES):
        return False
    for pat in forbidden_patterns(cfg):
        target = rel if "/" in pat else base
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
    import json

    for start in (cwd, os.environ.get("CLAUDE_PROJECT_DIR"), os.getcwd()):
        if not start:
            continue
        root = repo_root(start) or start
        try:
            with open(os.path.join(root, ".claude", "settings.local.json"), encoding="utf-8") as fh:
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
