#!/usr/bin/env python3
"""scripts/afconfig.py: YAML subset, config validation, forbidden paths, worktree-aware lookups."""

import builtins
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import afconfig  # noqa: E402

TEMPLATE = os.path.join(ROOT, "agentflow.yaml")


def fallback_parse(text):
    """parse_yaml with PyYAML hidden, even where it is installed."""
    real_import = builtins.__import__

    def no_yaml(name, *args, **kwargs):
        if name == "yaml":
            raise ImportError(name)
        return real_import(name, *args, **kwargs)
    with mock.patch("builtins.__import__", no_yaml):
        return afconfig.parse_yaml(text)


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def filled_config():
    with open(TEMPLATE, encoding="utf-8") as fh:
        cfg = fallback_parse(fh.read())
    cfg["board"]["url"] = "https://github.com/orgs/o/projects/1"
    return cfg


class Yaml(unittest.TestCase):
    def test_template_parses_like_pyyaml(self):
        try:
            import yaml
        except ImportError:
            self.skipTest("PyYAML không có")
        with open(TEMPLATE, encoding="utf-8") as fh:
            text = fh.read()
        self.assertEqual(fallback_parse(text), yaml.safe_load(text))

    def test_scalars(self):
        cfg = fallback_parse('a: 1\nb: -2\nc: 1.5\nd: true\ne: False\nf: null\ng: ~\nh: "x # y"\ni: \'it\'\'s\'\nj: plain # note\nk:\n')
        self.assertEqual(cfg, {"a": 1, "b": -2, "c": 1.5, "d": True, "e": False, "f": None, "g": None, "h": "x # y", "i": "it's", "j": "plain", "k": None})

    def test_flow_collections(self):
        self.assertEqual(fallback_parse('a: [x, "y z", 3]\nb: {k: v, n: 1}\nc: []\nd: {default: opus}'),
                         {"a": ["x", "y z", 3], "b": {"k": "v", "n": 1}, "c": [], "d": {"default": "opus"}})

    def test_nested_blocks_and_lists(self):
        self.assertEqual(fallback_parse("a:\n  b:\n    c: 1\n  d:\n    - x\n    - y: 2\n      z: 3\ne:\n- q\n"),
                         {"a": {"b": {"c": 1}, "d": ["x", {"y": 2, "z": 3}]}, "e": ["q"]})

    def test_apostrophe_in_plain_text_does_not_swallow_the_comment(self):
        self.assertEqual(fallback_parse("notes: don't use # comment\n"), {"notes": "don't use"})

    def test_hash_inside_word_is_text(self):
        self.assertEqual(fallback_parse("a: x#y\n"), {"a": "x#y"})

    def test_bad_input(self):
        for text in ("\ta: 1\n", "a: 1\n    b: 2\n", "just text\n"):
            with self.subTest(text), self.assertRaises(ValueError):
                fallback_parse(text)
        self.assertEqual(fallback_parse("# only comments\n"), {})


class Validate(unittest.TestCase):
    def problems(self, cfg):
        return [m for level, m in afconfig.validate_config(cfg) if level == "fail"]

    def test_template_is_valid(self):
        self.assertEqual(self.problems(filled_config()), [])

    def test_each_problem_is_named(self):
        cases = [
            (lambda c: c["board"]["status"].pop("in_qc"), "board.status.in_qc"),
            (lambda c: c["board"]["status"].update(in_qc="In Review"), "cùng trỏ"),
            (lambda c: c["labels"].pop("deploying"), "labels.deploying"),
            (lambda c: c.update(classify="x"), "classify"),
            (lambda c: c.update(types={}), "types"),
            (lambda c: c["git"].update(branch="{type}/x"), "git.branch"),
            (lambda c: c["staging"].update(branch=""), "staging.branch"),
            (lambda c: c["git"].update(base="staging"), "trùng git.base"),
            (lambda c: c["run"].update(parallel=0), "run.parallel"),
            (lambda c: c["run"].update(max_tasks="5"), "run.max_tasks"),
            (lambda c: c["run"].update(models={"dev": {}}), "run.models.dev.default"),
            (lambda c: c["notify"].update(events=["x"]), "notify.events"),
            (lambda c: c.update(surfaces={"web": {}}), "surfaces.web"),
        ]
        for change, needle in cases:
            cfg = filled_config()
            change(cfg)
            with self.subTest(needle):
                self.assertTrue(any(needle in m for m in self.problems(cfg)), self.problems(cfg))

    def test_warnings(self):
        cfg = filled_config()
        cfg["oops"] = 1
        cfg["git"]["protected"] = ["staging"]
        warns = [m for level, m in afconfig.validate_config(cfg) if level == "warn"]
        self.assertTrue(any("oops" in m for m in warns))
        self.assertTrue(any("git.protected" in m for m in warns))


class Paths(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = os.path.realpath(self.tmp.name)
        git(self.repo, "init", "-q", "-b", "master")
        self.cfg = {"forbidden": ["secret/**", "conf/", "./private.txt", "*.secret"]}

    def forbidden(self, path):
        return afconfig.is_forbidden(path, self.repo, self.cfg)

    def test_globs(self):
        for path in ("secret/a/b.txt", "conf/x", "private.txt", "deep/dir/x.secret", ".env", "web/.env", ".env.local", "a/b/server.pem", "x.key", "c.p12", "c.pfx", "k.jks", "k.keystore", ".claude/settings.local.json", ".netrc", "a/.git-credentials", "id_rsa", "deep/id_ed25519"):
            with self.subTest(path):
                self.assertTrue(self.forbidden(path))

    def test_not_forbidden(self):
        for path in (".env.example", "web/.env.sample", ".env.template", "cert.pem.dist", "src/env.ts", "README.md", "secrets.md", "key.ts", "", ".claude/settings.json"):
            with self.subTest(path):
                self.assertFalse(self.forbidden(path))

    def test_case_insensitive(self):
        self.assertTrue(self.forbidden(".ENV"))

    def test_symlink_resolves(self):
        with open(os.path.join(self.repo, ".env"), "w") as fh:
            fh.write("x")
        os.symlink(".env", os.path.join(self.repo, "innocent.txt"))
        os.symlink(".env", os.path.join(self.repo, "safe.example"))
        self.assertTrue(self.forbidden("innocent.txt"))
        self.assertTrue(self.forbidden("safe.example"))

    def test_outside_the_repo_only_file_name_globs(self):
        with tempfile.TemporaryDirectory() as other:
            self.assertTrue(self.forbidden(os.path.join(other, ".env")))
            self.assertTrue(self.forbidden(os.path.join(other, "a.pem")))
            self.assertFalse(self.forbidden(os.path.join(other, "secret", "x.txt")))
            self.assertFalse(self.forbidden(os.path.join(other, "a.txt")))

    def test_home_credentials(self):
        with mock.patch.dict(os.environ, {"HOME": self.repo}):
            self.assertTrue(self.forbidden(os.path.join(self.repo, ".ssh", "config")))
            self.assertTrue(self.forbidden(os.path.join(self.repo, ".aws", "credentials")))
            self.assertTrue(self.forbidden(os.path.join(self.repo, ".config", "gh", "hosts.yml")))
            self.assertFalse(self.forbidden(os.path.join(self.repo, ".aws", "config")))


class Repo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = os.path.realpath(self.tmp.name)
        git(self.repo, "init", "-q", "-b", "master")
        git(self.repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "i", "--allow-empty")

    def test_worktree_lookups_reach_the_main_checkout(self):
        with open(os.path.join(self.repo, "agentflow.yaml"), "w") as fh:
            fh.write("schema: 4\n")
        git(self.repo, "worktree", "add", "-q", "wt", "-b", "f")
        wt = os.path.join(self.repo, "wt")
        self.assertEqual(afconfig.main_root(wt), self.repo)
        self.assertEqual(afconfig.main_root(self.repo), self.repo)
        self.assertEqual(afconfig.load_config(wt), {"schema": 4})
        with open(os.path.join(wt, "agentflow.yaml"), "w") as fh:
            fh.write("schema: 99\n")
        self.assertEqual(afconfig.load_config(wt), {"schema": 4})  # an agent writes in its worktree: the main copy wins
        self.assertEqual(afconfig.settings_path(wt), os.path.join(self.repo, ".claude", "settings.local.json"))

    def test_no_config(self):
        self.assertIsNone(afconfig.load_config(self.repo))
        self.assertIsNone(afconfig.main_root(tempfile.gettempdir()))

    def test_protected(self):
        cfg = {"git": {"base": "dev", "protected": ["production", "staging"]}, "staging": {"branch": "staging"}}
        self.assertEqual(afconfig.protected_branches(cfg, self.repo), {"dev", "production"})
        self.assertEqual(afconfig.protected_branches({"git": {"protected": "prod"}}, self.repo), {"prod", "main", "master"})  # origin/HEAD unset
        self.assertEqual(afconfig.protected_branches({"git": {"base": "master"}, "staging": {"branch": "master"}}, self.repo), set())

    def test_default_branch_stays_protected_when_base_differs(self):
        bare = os.path.join(self.repo, "o.git")
        git(self.repo, "init", "-q", "--bare", "-b", "master", bare)
        git(self.repo, "remote", "add", "origin", bare)
        git(self.repo, "push", "-q", "origin", "master")
        git(self.repo, "fetch", "-q", "origin")
        git(self.repo, "remote", "set-head", "origin", "master")
        self.assertEqual(afconfig.protected_branches({"git": {"base": "develop"}}, self.repo), {"develop", "master"})

    def test_token_order(self):
        os.makedirs(os.path.join(self.repo, ".claude"))
        with open(os.path.join(self.repo, ".claude", "settings.local.json"), "w") as fh:
            fh.write('{"env": {"GITHUB_TOKEN": "from-settings"}}')
        with mock.patch.dict(os.environ, {"GITHUB_TOKEN": "from-env"}):
            self.assertEqual(afconfig.github_token(self.repo), "from-settings")
        empty = os.path.realpath(tempfile.mkdtemp(dir=self.repo))
        with mock.patch.object(afconfig, "settings_path", return_value=os.path.join(empty, "none")), mock.patch.dict(os.environ, {"GITHUB_TOKEN": "from-env"}):
            self.assertEqual(afconfig.github_token(self.repo), "from-env")


class Misc(unittest.TestCase):
    def test_board_url(self):
        self.assertEqual(afconfig.parse_board_url("https://github.com/orgs/acme/projects/7/views/1"), {"owner_type": "org", "owner": "acme", "number": 7})
        self.assertEqual(afconfig.parse_board_url("https://github.com/users/me/projects/2"), {"owner_type": "user", "owner": "me", "number": 2})
        for bad in (None, "", "https://github.com/acme/repo", "http://github.com/orgs/a/projects/1"):
            self.assertIsNone(afconfig.parse_board_url(bad))

    def test_locked_settings(self):
        for key, value in (("disableAllHooks", "true"), ("hooks", "{}"), ("hooks.PreToolUse", "[]"), ("enabledPlugins.agentflow@m", "false")):
            self.assertTrue(afconfig.settings_key_locked(key, value), key)
        for key, value in (("enabledPlugins.agentflow@m", "true"), ("enabledPlugins.other@m", "false"), ("permissions.defaultMode", '"bypassPermissions"')):
            self.assertFalse(afconfig.settings_key_locked(key, value), key)

    def test_secret_value_regex(self):
        for text in ("gh" + "p_" + "a" * 36, "github_" + "pat_" + "a" * 60, "123456789:" + "A" * 35, "xox" + "b-123-abc-def", "AK" + "IA" + "A" * 16, "-----BEGIN RSA PRIVATE" + " KEY-----"):
            self.assertTrue(afconfig.SECRET_VALUE.search(text), text)
        for text in ("ghp_short", "commit 3f2a9c1", "GITHUB_TOKEN", "12:30", "-----BEGIN CERTIFICATE-----"):
            self.assertFalse(afconfig.SECRET_VALUE.search(text), text)


if __name__ == "__main__":
    unittest.main()
