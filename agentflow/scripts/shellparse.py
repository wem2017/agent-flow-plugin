"""Small POSIX-shell reader for guard.py (stdlib only). Not an interpreter: it only finds every simple command a
script would run, including the nested ones shlex cannot see — `$(..)`, backticks, `<(..)`, subshells, groups,
if/for/while bodies — plus redirections, here-docs and pipelines.

commands(text) → flat list of Cmd. Quotes are removed from words; `$VAR` and `$(..)` stay as written, so the caller
can expand known variables and treat what is left as unknown. A `$` that the shell would not expand (single quotes,
backslash, $'..') comes back as LITERAL_DOLLAR. Subshell boundaries come back as Cmd with `mark` "push" / "pop", since a
`cd` inside one does not outlive it.
"""

import re

MAX_DEPTH = 16
RESERVED = {"if", "then", "elif", "else", "fi", "while", "until", "do", "done", "esac", "{", "}", "!", "coproc"}
LITERAL_DOLLAR = "\ue000"
ANSI_C = {"n": "\n", "t": "\t", "r": "\r", "a": "\a", "b": "\b", "e": "\x1b", "E": "\x1b", "f": "\f", "v": "\v", "\\": "\\", "'": "'", '"': '"', "?": "?"}
REDIRECTS = ("<<<", "<<-", "&>>", "<<", ">>", "<>", "<&", ">&", ">|", "&>", "<", ">")


class Cmd:
    __slots__ = ("words", "quoted", "redirs", "bodies", "herestrings", "prev", "next", "mark")

    def __init__(self, mark=None):
        self.mark = mark
        self.words = []  # assignments first, then argv
        self.quoted = []  # per word: had a quote in it, so an expansion inside does not split
        self.redirs = []  # (op, target)
        self.bodies = []  # here-doc text
        self.herestrings = []
        self.prev = None  # the command piping into this one
        self.next = None  # the command this one pipes into


class _Reader:
    def __init__(self, text, depth=0):
        if depth > MAX_DEPTH:
            raise ValueError("shell nesting too deep")
        self.s, self.depth, self.out, self.arith = text, depth, [], {}

    def _nested(self, i, stop):
        """Parse a nested command list starting at i with this same reader, so here-docs inside it stay in sync."""
        self.depth += 1
        if self.depth > MAX_DEPTH:
            raise ValueError("shell nesting too deep")
        self.out.append(Cmd("push"))
        end = self.parse(i, stop)
        self.out.append(Cmd("pop"))
        self.depth -= 1
        return end

    def _backtick(self, i):
        s, j, inner = self.s, i + 1, []
        while j < len(s) and s[j] != "`":
            if s[j] == "\\" and j + 1 < len(s):
                j += 1
            inner.append(s[j])
            j += 1
        self.out += [Cmd("push")] + _Reader("".join(inner), self.depth + 1).run() + [Cmd("pop")]
        return j + 1

    def _param(self, i):
        """`${..}` kept raw; a substitution inside it still counts, and a `}` inside that does not close it."""
        s, j = self.s, i + 2
        while j < len(s) and s[j] != "}":
            if s[j] == "\\":
                j += 2
            elif s[j] == "'":
                k = s.find("'", j + 1)
                j = len(s) if k < 0 else k + 1
            elif s[j] == '"':
                _, j = self._double_quoted(j + 1)
            elif s[j] in "$`":
                j = self._expansion(j) or j + 1
            else:
                j += 1
        return j + 1

    def _arithmetic(self, i, closer):
        """s[i] is the first character inside `$((`, `((` or `$[`. Index after the closer, or None if it is not one:
        `<<` in there is a shift, not a here-doc."""
        if (i, closer) in self.arith:  # a failed attempt is retried by every enclosing one: without this, exponential time
            return self.arith[(i, closer)]
        self.arith[(i, closer)] = end = self._scan_arithmetic(i, closer)
        return end

    def _scan_arithmetic(self, i, closer):
        s, j, depth = self.s, i, 0
        while j < len(s):
            ch = s[j]
            if ch in "$`":
                j = self._expansion(j) or j + 1
                continue
            if closer == "]":
                if ch == "]":
                    return j + 1
            elif ch == "(":
                depth += 1
            elif ch == ")":
                if depth == 0:
                    return j + 2 if s.startswith("))", j) else None
                depth -= 1
            j += 1
        return None

    def _expansion(self, i):
        """s[i] is `$` or a backtick. Return the index after it if it opens a substitution, else None."""
        s = self.s
        if s[i] == "`":
            return self._backtick(i)
        if s.startswith("$((", i):
            end = self._arithmetic(i + 3, ")")
            if end is not None:
                return end
        if s.startswith("$[", i):
            end = self._arithmetic(i + 2, "]")
            if end is not None:
                return end
        if s.startswith("$(", i):
            return self._nested(i + 2, ")")
        if s.startswith("${", i):
            return self._param(i)
        return None

    def _ansi_c(self, i):
        """s[i] is the first character inside $'..'. Return (decoded text, index after the closing quote)."""
        s, j, out = self.s, i, []
        while j < len(s) and s[j] != "'":
            if s[j] != "\\" or j + 1 >= len(s):
                out.append(s[j])
                j += 1
                continue
            esc = s[j + 1]
            m = re.compile(r"x[0-9a-fA-F]{1,2}|u[0-9a-fA-F]{1,4}|U[0-9a-fA-F]{1,8}|[0-7]{1,3}").match(s, j + 1)
            if m:
                body = m.group(0)
                out.append(chr(int(body, 8) if body[0] in "01234567" else int(body[1:], 16)))
                j = m.end()
            else:
                out.append(ANSI_C.get(esc, "\\" + esc))
                j += 2
        return "".join(out).replace("$", LITERAL_DOLLAR), j + 1

    def _double_quoted(self, i):
        s, j, out = self.s, i, []
        while j < len(s) and s[j] != '"':
            ch = s[j]
            if ch == "\\" and j + 1 < len(s):
                if s[j + 1] in '"\\$`':
                    out.append(LITERAL_DOLLAR if s[j + 1] == "$" else s[j + 1])
                elif s[j + 1] != "\n":
                    out.append(ch + s[j + 1])
                j += 2
            elif ch in "$`":
                end = self._expansion(j)
                if end is None:
                    out.append(ch)
                    j += 1
                else:
                    out.append(s[j:end])
                    j = end
            else:
                out.append(ch)
                j += 1
        return "".join(out), j + 1

    def _heredoc(self, i, pending):
        """s[i] is the first character after the newline. Fill the bodies of the pending here-docs."""
        s = self.s
        for delim, quoted, strip, cmd in pending:
            lines = []
            while i < len(s):
                end = s.find("\n", i)
                end = len(s) if end < 0 else end
                line = s[i:end]
                i = end + 1
                if (line.lstrip("\t") if strip else line) == delim:
                    break
                lines.append(line)
            body = "\n".join(lines)
            cmd.bodies.append(body)
            if not quoted:
                cmd.herestrings.append(body)  # expands like a here-string
            if not quoted and ("$(" in body or "`" in body):
                self.out += _Reader('"' + body.replace('"', '\\"') + '"', self.depth + 1).run()
        return i

    def parse(self, i, stop=None):
        s = self.s
        cmd, pending = Cmd(), []
        word, quoted, op, prev, skip_name, case_depth = None, False, None, None, False, 0

        def end_word():
            nonlocal word, quoted, op, skip_name, case_depth
            if word is None:
                return
            text = "".join(word)
            if not quoted and not op and not cmd.words:
                if text == "case":
                    case_depth += 1
                elif text == "esac":
                    case_depth = max(0, case_depth - 1)
            if op in ("<<", "<<-"):
                pending.append((text, quoted, op == "<<-", cmd))
            elif op == "<<<":
                cmd.herestrings.append(text)
            elif op:
                cmd.redirs.append((op, text))
            elif skip_name:
                skip_name = False
            elif not quoted and not cmd.words and text == "function":
                skip_name = True
            elif quoted or cmd.words or text not in RESERVED:
                cmd.words.append(text)
                cmd.quoted.append(quoted)
            word, quoted, op = None, False, None

        def end_cmd(piped=False):
            nonlocal cmd, prev
            end_word()
            has_content = cmd.words or cmd.redirs or cmd.herestrings or any(p[3] is cmd for p in pending)
            if has_content:
                cmd.prev = prev
                if prev is not None:
                    prev.next = cmd
                self.out.append(cmd)
            prev = cmd if piped and has_content else None
            cmd = Cmd()

        while i < len(s):
            ch = s[i]
            if ch == ")" and word is not None and "".join(word) == "esac":
                end_word()
            if stop and ch == stop and not case_depth:  # inside `case`, `)` ends a pattern, not the substitution
                end_cmd()
                return i + 1
            if ch == "\n":
                end_cmd()
                i += 1
                if pending:
                    i = self._heredoc(i, pending)
                    pending = []
            elif ch in " \t":
                end_word()
                i += 1
            elif ch == "#" and word is None:
                while i < len(s) and s[i] != "\n":
                    i += 1
            elif ch == "'":
                j = s.find("'", i + 1)
                j = len(s) if j < 0 else j
                word = (word or []) + [s[i + 1 : j].replace("$", LITERAL_DOLLAR)]
                quoted, i = True, j + 1
            elif ch == '"':
                text, i = self._double_quoted(i + 1)
                word = (word or []) + [text]
                quoted = True
            elif ch == "\\":
                if i + 1 < len(s) and s[i + 1] != "\n":
                    word = (word or []) + [LITERAL_DOLLAR if s[i + 1] == "$" else s[i + 1]]
                    quoted = True
                i += 2
            elif s.startswith("$'", i):
                text, i = self._ansi_c(i + 2)
                word = (word or []) + [text]
                quoted = True
            elif s.startswith('$"', i):
                i += 1
            elif ch in "$`":
                end = self._expansion(i)
                end = i + 1 if end is None else end
                word = (word or []) + [s[i:end]]
                i = end
            elif s.startswith(("<(", ">("), i):
                end = self._nested(i + 2, ")")
                word = (word or []) + [s[i:end]]
                i = end
            elif ch in "<>" or s.startswith("&>", i):
                if word is not None and "".join(word).isdigit():
                    word, quoted = None, False  # the fd number of `2>file`
                end_word()
                op = next(o for o in REDIRECTS if s.startswith(o, i))
                i += len(op)
            elif ch == "|":
                end_cmd(piped=not s.startswith("||", i))
                i += 2 if s.startswith(("||", "|&"), i) else 1
            elif ch in ";&":
                end_cmd()
                i += 2 if s.startswith((";;", ";&", "&&"), i) else 1
            elif ch == "(":
                end = self._arithmetic(i + 2, ")") if s.startswith("((", i) and word is None and not cmd.words else None
                if end is not None:
                    i = end
                    continue
                end_cmd()
                i = self._nested(i + 1, ")")
            elif ch == ")":
                end_cmd()  # a `case` pattern
                i += 1
            else:
                word = (word or []) + [ch]
                i += 1
        end_cmd()
        return i

    def run(self):
        self.parse(0)
        return self.out


def commands(text):
    return _Reader(text).run()
