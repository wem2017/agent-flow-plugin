#!/usr/bin/env python3
"""agentflow-settings, agentflow-journal, agentflow-notify, mcp-headers, result-check: run as the user runs them."""

import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
FAKE_PAT = "gh" + "p_" + "a1B2" * 9


def tool(name, *args, cwd=None, stdin=None, env=None):
    path = os.path.join(ROOT, "bin", name) if name.startswith("agentflow-") else os.path.join(ROOT, "scripts", name)
    full = {"PATH": "/usr/bin:/bin", "HOME": cwd or tempfile.gettempdir()}
    full.update(env or {})
    return subprocess.run([sys.executable, "-I", path, *args], cwd=cwd, input=stdin, capture_output=True, text=True, env=full)


class RepoCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = os.path.realpath(self.tmp.name)
        subprocess.run(["git", "init", "-q", "-b", "master"], cwd=self.repo, check=True)
        self.settings = os.path.join(self.repo, ".claude", "settings.local.json")

    def read_settings(self):
        with open(self.settings, encoding="utf-8") as fh:
            return json.load(fh)


class Settings(RepoCase):
    def test_secret_is_stored_private_and_never_shown(self):
        res = tool("agentflow-settings", "set-secret", "GITHUB_TOKEN", cwd=self.repo, stdin="s3cret-value\n")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertNotIn("s3cret-value", res.stdout + res.stderr)
        self.assertEqual(self.read_settings()["env"]["GITHUB_TOKEN"], "s3cret-value")
        self.assertEqual(stat.S_IMODE(os.stat(self.settings).st_mode), 0o600)
        shown = tool("agentflow-settings", "show", cwd=self.repo)
        self.assertNotIn("s3cret-value", shown.stdout)
        self.assertEqual(json.loads(shown.stdout)["env"]["GITHUB_TOKEN"], "<set>")

    def test_existing_world_readable_file_is_tightened(self):
        os.makedirs(os.path.dirname(self.settings))
        with open(self.settings, "w") as fh:
            fh.write("{}")
        os.chmod(self.settings, 0o644)
        tool("agentflow-settings", "set-secret", "X", cwd=self.repo, stdin="v\n")
        self.assertEqual(stat.S_IMODE(os.stat(self.settings).st_mode), 0o600)

    def test_stale_temp_file_cannot_widen_the_mode(self):
        os.makedirs(os.path.dirname(self.settings))
        with open(self.settings + ".tmp", "w") as fh:
            fh.write("")
        os.chmod(self.settings + ".tmp", 0o644)
        tool("agentflow-settings", "set-secret", "X", cwd=self.repo, stdin="v\n")
        self.assertEqual(stat.S_IMODE(os.stat(self.settings).st_mode), 0o600)

    def test_show_masks_secret_looking_keys_anywhere(self):
        os.makedirs(os.path.dirname(self.settings))
        with open(self.settings, "w") as fh:
            json.dump({"mcpServers": {"x": {"headers": {"Authorization": "Bearer abc"}}}, "apiKeyHelper": "keep", "env": {"A": ""}}, fh)
        shown = json.loads(tool("agentflow-settings", "show", cwd=self.repo).stdout)
        self.assertEqual(shown["mcpServers"]["x"]["headers"]["Authorization"], "<set>")
        self.assertEqual(shown["env"]["A"], "<empty>")

    def test_set_merges_and_parses_json(self):
        tool("agentflow-settings", "set", "permissions.defaultMode", '"bypassPermissions"', cwd=self.repo)
        tool("agentflow-settings", "set", "enabledPlugins.agentflow@m", "true", cwd=self.repo)
        tool("agentflow-settings", "set", "x.plain", "not json", cwd=self.repo)
        self.assertEqual(self.read_settings(), {"permissions": {"defaultMode": "bypassPermissions"}, "enabledPlugins": {"agentflow@m": True}, "x": {"plain": "not json"}})

    def test_refuses_env_and_locked_keys(self):
        for key, value in (("env.A", "1"), ("disableAllHooks", "true"), ("hooks.PreToolUse", "[]"), ("enabledPlugins.agentflow@m", "false")):
            with self.subTest(key):
                self.assertNotEqual(tool("agentflow-settings", "set", key, value, cwd=self.repo).returncode, 0)
        self.assertFalse(os.path.exists(self.settings))

    def test_has(self):
        self.assertEqual(tool("agentflow-settings", "has", "A", cwd=self.repo).returncode, 1)
        tool("agentflow-settings", "set-secret", "A", cwd=self.repo, stdin="v\n")
        self.assertEqual(tool("agentflow-settings", "has", "A", cwd=self.repo).returncode, 0)

    def test_empty_stdin_writes_nothing(self):
        self.assertNotEqual(tool("agentflow-settings", "set-secret", "A", cwd=self.repo, stdin="\n").returncode, 0)
        self.assertFalse(os.path.exists(self.settings))

    def test_broken_json_reports_without_content(self):
        os.makedirs(os.path.dirname(self.settings))
        with open(self.settings, "w") as fh:
            fh.write('{"env": {"T": "leaky-value"')
        res = tool("agentflow-settings", "show", cwd=self.repo)
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("JSON", res.stderr)
        self.assertNotIn("leaky-value", res.stdout + res.stderr)

    def test_worktree_shares_the_main_settings(self):
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "i", "--allow-empty"], cwd=self.repo, check=True)
        subprocess.run(["git", "worktree", "add", "-q", "wt", "-b", "f"], cwd=self.repo, check=True)
        tool("agentflow-settings", "set-secret", "A", cwd=os.path.join(self.repo, "wt"), stdin="v\n")
        self.assertEqual(self.read_settings()["env"]["A"], "v")


class Journal(RepoCase):
    def setUp(self):
        super().setUp()
        self.path = os.path.join(self.repo, "j", "journal.jsonl")
        self.env = {"AGENTFLOW_JOURNAL": self.path}

    def jr(self, *args):
        return tool("agentflow-journal", *args, cwd=self.repo, env=self.env)

    def rows(self):
        with open(self.path, encoding="utf-8") as fh:
            return [json.loads(x) for x in fh]

    def test_add_list_mark_stats(self):
        first = self.jr("add", "retry", "nên X", "--issue", "7", "--role", "dev", "--repo", "o/r").stdout.split()[1]
        second = self.jr("add", "slow", "nên Y").stdout.split()[1]
        self.assertIn("nên X", self.jr("list").stdout)
        self.assertEqual(self.rows()[0]["issue"], 7)
        self.assertIn("marked 1/1", self.jr("mark", first, "--as", "applied", "--ref", "v2").stdout)
        self.assertNotIn("nên X", self.jr("list").stdout)
        self.assertIn("nên X", self.jr("list", "--all").stdout)
        self.assertIn("slow", self.jr("stats").stdout)
        self.assertNotIn("retry", self.jr("stats").stdout)
        self.jr("mark", second, "--as", "dismissed")
        self.assertIn("không có entry mới", self.jr("stats").stdout)

    def test_unknown_kind_refused(self):
        self.assertNotEqual(self.jr("add", "nope", "x").returncode, 0)

    def test_token_is_scrubbed_before_it_reaches_disk(self):
        self.jr("add", "tool_error", "call lỗi với %s rồi" % FAKE_PAT)
        with open(self.path, encoding="utf-8") as fh:
            text = fh.read()
        self.assertNotIn(FAKE_PAT, text)
        self.assertIn("<secret>", text)

    def test_note_is_one_line_and_bounded(self):
        self.jr("add", "other", "a\nb  " + "c" * 1000)
        note = self.rows()[0]["note"]
        self.assertNotIn("\n", note)
        self.assertLessEqual(len(note), 400)

    def test_corrupt_line_is_skipped(self):
        self.jr("add", "other", "ok")
        with open(self.path, "a") as fh:
            fh.write("{broken\n")
        self.assertIn("ok", self.jr("list").stdout)

    def test_empty_journal(self):
        self.assertIn("trống", self.jr("list").stdout)


class Notify(RepoCase):
    def write_cfg(self, text):
        with open(os.path.join(self.repo, "agentflow.yaml"), "w") as fh:
            fh.write(text)

    def test_off_by_default(self):
        self.write_cfg("notify:\n  telegram: false\n")
        res = tool("agentflow-notify", "blocked", "x", cwd=self.repo)
        self.assertEqual((res.returncode, res.stdout.strip()), (0, "notify: off"))

    def test_event_not_listed(self):
        self.write_cfg("notify:\n  telegram: true\n  events: [blocked]\n")
        self.assertIn("không bật", tool("agentflow-notify", "qc_manual", "x", cwd=self.repo).stdout)

    def test_missing_credentials_does_not_fail(self):
        self.write_cfg("notify:\n  telegram: true\n  events: [blocked]\n")
        res = tool("agentflow-notify", "blocked", "x", cwd=self.repo)
        self.assertEqual(res.returncode, 0)
        self.assertIn("thiếu", res.stdout)

    def test_unreachable_network_does_not_fail_nor_leak(self):
        self.write_cfg("notify:\n  telegram: true\n  events: [blocked]\n")
        env = {"TELEGRAM_BOT_TOKEN": "123:bot-secret", "TELEGRAM_CHAT_ID": "1", "HTTPS_PROXY": "http://127.0.0.1:9", "https_proxy": "http://127.0.0.1:9"}
        res = tool("agentflow-notify", "blocked", "x", cwd=self.repo, env=env)
        self.assertEqual(res.returncode, 0)
        self.assertNotIn("bot-secret", res.stdout + res.stderr)

    def test_broken_config_and_outside_repo(self):
        self.write_cfg("\tbad: [\n")
        self.assertEqual(tool("agentflow-notify", "blocked", "x", cwd=self.repo).returncode, 0)
        self.assertEqual(tool("agentflow-notify", "blocked", "x", cwd=tempfile.gettempdir()).returncode, 0)

    def test_usage(self):
        self.assertEqual(tool("agentflow-notify", cwd=self.repo).returncode, 0)


class McpHeaders(RepoCase):
    def test_token_from_settings(self):
        os.makedirs(os.path.dirname(self.settings))
        with open(self.settings, "w") as fh:
            json.dump({"env": {"GITHUB_TOKEN": "abc"}}, fh)
        out = json.loads(tool("mcp-headers.py", cwd=self.repo).stdout)
        self.assertEqual(out["Authorization"], "Bearer abc")
        self.assertIn("projects", out["X-MCP-Toolsets"])

    def test_token_from_env(self):
        self.assertEqual(json.loads(tool("mcp-headers.py", cwd=self.repo, env={"GH_TOKEN": "xyz"}).stdout)["Authorization"], "Bearer xyz")

    def test_stdout_stays_json_without_token(self):
        out = json.loads(tool("mcp-headers.py", cwd=self.repo).stdout)
        self.assertNotIn("Authorization", out)

    def test_every_tool_family_the_prompts_use_is_enabled(self):
        toolsets = json.loads(tool("mcp-headers.py", cwd=self.repo).stdout)["X-MCP-Toolsets"].split(",")
        for name in ("context", "issues", "pull_requests", "projects", "actions"):
            self.assertIn(name, toolsets)


class ResultCheck(unittest.TestCase):
    def check(self, message, agent="agentflow:dev", active=False):
        payload = {"agent_type": agent, "last_assistant_message": message, "stop_hook_active": active}
        res = tool("result-check.py", stdin=json.dumps(payload))
        self.assertEqual(res.returncode, 0, res.stderr)
        return res.stdout.strip()

    def test_valid(self):
        for message in ("Xong.\n\nRESULT: in_review · ok\nPR: #5 @abc\nNOTE: x", "RESULT: ready · needs_info", "RESULT: in_qc · waiting_human", "RESULT: in_qc · blocked", "RESULT: in_progress · escalated", "RESULT: in_review · abort"):
            with self.subTest(message):
                self.assertEqual(self.check(message), "")

    def test_invalid_is_sent_back(self):
        for message in ("Tôi đã xong.", "", "RESULT: in_review", "RESULT: in_review · done", "RESULT: nowhere · ok", "result: ready · ok"):
            with self.subTest(message):
                self.assertEqual(json.loads(self.check(message))["decision"], "block")

    def test_blocks_only_once(self):
        self.assertEqual(self.check("không có", active=True), "")

    def test_other_agents_untouched(self):
        self.assertEqual(self.check("không có", agent="Explore"), "")
        self.assertEqual(self.check("không có", agent=""), "")

    def test_broken_stdin(self):
        self.assertEqual(tool("result-check.py", stdin="not json").returncode, 0)


if __name__ == "__main__":
    unittest.main()
