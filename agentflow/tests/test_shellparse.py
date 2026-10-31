#!/usr/bin/env python3
"""scripts/shellparse.py: what a shell would run, whatever the nesting."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import shellparse  # noqa: E402


def argv(text):
    return [c.words for c in shellparse.commands(text) if not c.mark]


class ShellParse(unittest.TestCase):
    def test_lists_and_pipes(self):
        self.assertEqual(argv("a && b || c; d & e\nf"), [["a"], ["b"], ["c"], ["d"], ["e"], ["f"]])
        cmds = shellparse.commands("a | b |& c || d")
        self.assertIs(cmds[1].prev, cmds[0])
        self.assertIs(cmds[2].prev, cmds[1])
        self.assertIsNone(cmds[3].prev)

    def test_quotes(self):
        self.assertEqual(argv(r"""echo 'a;b' "c|d" e\;f g\ h"""), [["echo", "a;b", "c|d", "e;f", "g h"]])
        self.assertEqual(argv('git commit -m "fix: a | b; c"'), [["git", "commit", "-m", "fix: a | b; c"]])
        self.assertEqual(argv("echo a # comment ; rm b"), [["echo", "a"]])
        self.assertEqual(argv("echo a#b"), [["echo", "a#b"]])

    def test_substitutions_are_found(self):
        self.assertIn(["rm", "x"], argv("echo $(rm x)"))
        self.assertIn(["rm", "x"], argv('echo "$(rm x)"'))
        self.assertIn(["rm", "x"], argv("echo `rm x`"))
        self.assertIn(["rm", "x"], argv('echo "`rm x`"'))
        self.assertIn(["rm", "x"], argv("cat <(rm x)"))
        self.assertIn(["rm", "x"], argv('echo "${A:-$(rm x)}"'))
        self.assertIn(["rm", "x"], argv("echo $(echo $(rm x))"))

    def test_escaped_substitution_is_text(self):
        self.assertEqual(argv('echo "\\$(rm x)"'), [["echo", shellparse.LITERAL_DOLLAR + "(rm x)"]])

    def test_literal_dollar_is_marked(self):
        lit = shellparse.LITERAL_DOLLAR
        self.assertEqual(argv("""echo '$A' \\$B "$C" $'$D'"""), [["echo", lit + "A", lit + "B", "$C", lit + "D"]])

    def test_ansi_c_quoting_does_not_desync(self):
        self.assertIn(["rm", "x"], argv(r"echo $'\'' ; rm x; echo $'\''"))
        self.assertEqual(argv(r"$'g\x69t' push"), [["git", "push"]])
        self.assertEqual(argv(r"$'\147it' push"), [["git", "push"]])

    def test_case_inside_a_substitution(self):
        self.assertIn(["rm", "x"], argv('echo "$(case a in a) rm x;; esac)"'))
        self.assertEqual(argv('echo "$(case a in a) true;; esac)" after')[-1][-1], "after")

    def test_brace_inside_a_parameter_default(self):
        self.assertIn(["rm", "x"], argv("""echo "${X:-$(echo '}' ; rm x)}" """))

    def test_arithmetic_shift_is_not_a_here_doc(self):
        for text in ("echo $[1<<2]\nrm x", "echo $((1<<2))\nrm x", "(( 1<<2 ))\nrm x"):
            with self.subTest(text):
                self.assertIn(["rm", "x"], argv(text))

    def test_subshell_is_marked(self):
        self.assertEqual([c.mark or c.words for c in shellparse.commands("(cd x); y")], ["push", ["cd", "x"], "pop", ["y"]])
        self.assertEqual([c.mark for c in shellparse.commands("{ cd x; }")], [None])

    def test_time_is_a_wrapper_not_a_keyword(self):
        self.assertEqual(argv("time -p rm x"), [["time", "-p", "rm", "x"]])

    def test_next_links_a_pipe(self):
        cmds = shellparse.commands("a | b")
        self.assertIs(cmds[0].next, cmds[1])

    def test_control_flow_bodies(self):
        for text in ("if a; then rm x; fi", "for i in 1 2; do rm x; done", "while a; do rm x; done", "{ rm x; }", "(rm x)", "! rm x", "f() { rm x; }", "function f { rm x; }", "case a in a) rm x;; esac"):
            with self.subTest(text):
                self.assertIn(["rm", "x"], argv(text))

    def test_quoted_reserved_word_is_a_command(self):
        self.assertEqual(argv("'if' a"), [["if", "a"]])
        self.assertEqual(argv("echo if"), [["echo", "if"]])

    def test_redirects(self):
        cmd = shellparse.commands("cat<in 2>&1 >out >>app &>both")[0]
        self.assertEqual(cmd.words, ["cat"])
        self.assertEqual(cmd.redirs, [("<", "in"), (">&", "1"), (">", "out"), (">>", "app"), ("&>", "both")])
        self.assertEqual(shellparse.commands("cat <<< 'text'")[0].herestrings, ["text"])

    def test_here_doc(self):
        cmd = shellparse.commands("bash <<EOF\nrm x\nEOF\nnext")
        self.assertEqual(cmd[0].bodies, ["rm x"])
        self.assertEqual(cmd[1].words, ["next"])
        self.assertEqual(shellparse.commands("cat <<-'E'\n\ta\n\tE\n")[0].bodies, ["\ta"])

    def test_here_doc_in_substitution_keeps_quotes_apart(self):
        cmds = argv('git commit -m "$(cat <<\'EOF\'\nfix: don\'t ) stop\nEOF\n)" && echo done')
        self.assertEqual(cmds[0], ["cat"])
        self.assertEqual(cmds[1][:3], ["git", "commit", "-m"])
        self.assertEqual(cmds[-1], ["echo", "done"])

    def test_unquoted_here_doc_body_runs_substitutions(self):
        self.assertIn(["rm", "x"], argv("cat <<EOF\n$(rm x)\nEOF"))
        self.assertNotIn(["rm", "x"], argv("cat <<'EOF'\n$(rm x)\nEOF"))

    def test_assignments_stay_words(self):
        self.assertEqual(argv("A=1 B=2 cmd"), [["A=1", "B=2", "cmd"]])
        self.assertEqual(argv("A=1; echo $A"), [["A=1"], ["echo", "$A"]])

    def test_broken_input_does_not_raise(self):
        for text in ("echo 'open", 'echo "open', "echo $(open", "echo `open", "cat <<EOF\nno end", ")", "|", "&&", ""):
            with self.subTest(text):
                shellparse.commands(text)

    def test_nesting_limit(self):
        with self.assertRaises(ValueError):
            shellparse.commands("$(" * 40 + "x" + ")" * 40)
        with self.assertRaises(ValueError):
            shellparse.commands("( " * 40 + "x" + " )" * 40)


if __name__ == "__main__":
    unittest.main()
