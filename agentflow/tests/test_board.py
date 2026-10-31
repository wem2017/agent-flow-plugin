#!/usr/bin/env python3
"""bin/agentflow-board against a fake GitHub: no network, no token."""

import contextlib
import datetime as dt
import importlib.machinery
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import afconfig  # noqa: E402


def load_board():
    sys.dont_write_bytecode = True  # bin/ must stay free of __pycache__
    path = os.path.join(ROOT, "bin", "agentflow-board")
    loader = importlib.machinery.SourceFileLoader("agentflow_board", path)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


board = load_board()
URL = "https://github.com/orgs/acme/projects/3"
OPTIONS = [{"id": "o%d" % i, "name": n, "color": "GRAY", "description": ""} for i, n in enumerate(
    ["Backlog", "Ready", "In Progress", "In Review", "In QC", "Ready to Merge", "Done"])]
SHA = "a" * 40


class FakeGitHub:
    """Routes (method, url substring) → (status, body); body may be a list, consumed call by call. Records calls."""

    def __init__(self):
        self.routes, self.calls = [], []

    def on(self, method, needle, body, status=200, headers=None):
        self.routes.append((method, needle, body, status, headers or {}))
        return self

    def __call__(self, method, url, headers=None, data=None, timeout=30):
        self.calls.append((method, url, data))
        text = url + (data.decode() if data else "")
        for m, needle, body, status, res_headers in self.routes:
            if m == method and needle in text:
                if isinstance(body, list) and body and isinstance(body[0], tuple):
                    status, payload = body.pop(0) if len(body) > 1 else body[0]
                else:
                    payload = body
                return status, res_headers, json.dumps(payload).encode()
        return 404, {}, b'{"message":"Not Found"}'


class BoardCase(unittest.TestCase):
    def setUp(self):
        self.gh = FakeGitHub()
        for patcher in (mock.patch.object(afconfig, "request", self.gh), mock.patch.object(board, "_TOKEN", "t"), mock.patch.object(board.time, "sleep")):
            patcher.start()
            self.addCleanup(patcher.stop)

    def run_cmd(self, *argv):
        out = io.StringIO()
        code = 0
        with mock.patch.object(sys, "argv", ["agentflow-board", *argv]), contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            try:
                board.main()
            except SystemExit as exc:
                code = exc.code or 0
        return code, out.getvalue()


class Checks(BoardCase):
    def setup_head(self, runs=(), statuses=(), compare="ahead"):
        self.gh.on("GET", "/commits/staging", {"sha": SHA})
        self.gh.on("GET", "/check-runs", {"check_runs": list(runs), "total_count": len(runs)})
        self.gh.on("GET", "/status", {"statuses": list(statuses), "total_count": len(statuses)})
        self.gh.on("GET", "/compare/", {"status": compare})

    def checks(self, *extra):
        code, out = self.run_cmd("checks", "o/r", "--branch", "staging", "--contains", "abc", *extra)
        return code, json.loads(out) if code == 0 else out

    def test_success(self):
        self.setup_head(runs=[{"name": "b", "status": "completed", "conclusion": "success"}, {"name": "s", "status": "completed", "conclusion": "skipped"}])
        self.assertEqual(self.checks()[1], {"state": "success", "sha": SHA, "contains": True, "failed": []})

    def test_failure_wins_over_pending(self):
        self.setup_head(runs=[{"name": "b", "status": "completed", "conclusion": "failure", "html_url": "u"}, {"name": "p", "status": "in_progress", "conclusion": None}])
        res = self.checks()[1]
        self.assertEqual((res["state"], res["failed"]), ("failure", [{"name": "b", "url": "u"}]))

    def test_commit_status_from_external_ci(self):
        self.setup_head(statuses=[{"context": "jenkins", "state": "error", "target_url": "j"}])
        self.assertEqual(self.checks()[1]["failed"], [{"name": "jenkins", "url": "j"}])

    def test_no_check_yet_is_pending(self):
        self.setup_head()
        self.assertEqual(self.checks()[1]["state"], "pending")

    def test_identical_head_contains(self):
        self.setup_head(compare="identical")
        self.assertTrue(self.checks()[1]["contains"])

    def test_green_right_after_the_push_is_still_pending(self):
        self.setup_head(runs=[{"name": "b", "status": "completed", "conclusion": "success"}])
        now = dt.datetime.now(dt.timezone.utc)
        fresh = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        settled = (now - dt.timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.assertEqual(self.checks("--since", fresh)[1]["state"], "pending")
        self.assertEqual(self.checks("--since", settled)[1]["state"], "success")

    def test_failure_is_not_delayed_by_since(self):
        self.setup_head(runs=[{"name": "b", "status": "completed", "conclusion": "failure", "html_url": "u"}])
        fresh = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.assertEqual(self.checks("--since", fresh)[1]["state"], "failure")

    def test_diverged_staging_does_not_contain(self):
        self.setup_head(compare="diverged")
        self.assertFalse(self.checks()[1]["contains"])

    def test_unreachable_sha_means_rewritten_not_crash(self):
        self.gh.on("GET", "/commits/staging", {"sha": SHA}).on("GET", "/check-runs", {"check_runs": []}).on("GET", "/status", {"statuses": []})
        code, res = self.checks()
        self.assertEqual(code, 0)
        self.assertFalse(res["contains"])

    def test_wait_polls_until_done(self):
        self.gh.on("GET", "/commits/staging", {"sha": SHA})
        self.gh.on("GET", "/check-runs", [(200, {"check_runs": [{"name": "b", "status": "in_progress", "conclusion": None}]}), (200, {"check_runs": [{"name": "b", "status": "completed", "conclusion": "success"}]})])
        self.gh.on("GET", "/status", {"statuses": []}).on("GET", "/compare/", {"status": "ahead"})
        self.assertEqual(self.checks("--wait", "5")[1]["state"], "success")
        board.time.sleep.assert_called_with(30)

    def test_transient_error_is_retried(self):
        self.gh.on("GET", "/commits/staging", [(502, {}), (200, {"sha": SHA})])
        self.gh.on("GET", "/check-runs", {"check_runs": []}).on("GET", "/status", {"statuses": []}).on("GET", "/compare/", {"status": "ahead"})
        self.assertEqual(self.checks()[0], 0)

    def test_permanent_error_is_reported(self):
        self.gh.on("GET", "/commits/staging", {"message": "Bad credentials"}, status=401)
        code, out = self.run_cmd("checks", "o/r", "--branch", "staging", "--contains", "abc")
        self.assertEqual(code, 2)
        self.assertIn("HTTP 401", out)


class StatusOptions(BoardCase):
    def test_plan_keeps_ids_on_rename_and_reorder(self):
        current = [{"id": "1", "name": "Todo", "color": "RED", "description": "x"}, {"id": "2", "name": "Done", "color": "GREEN", "description": "y"}]
        color, desc = (lambda i, n: "GRAY"), (lambda i, n: "new")
        result, extra = board.plan_options(current, ["Done", "Ready", "New"], ["Todo=Ready"], False, color, desc)
        self.assertEqual([(o.get("id"), o["name"]) for o in result], [("2", "Done"), ("1", "Ready"), (None, "New")])
        self.assertEqual(extra, [])
        self.assertEqual(result[0]["color"], "GREEN")

    def test_plan_keeps_unmapped_unless_drop(self):
        current = [{"id": "1", "name": "Odd", "color": "RED", "description": ""}]
        result, extra = board.plan_options(current, ["A"], [], False, lambda i, n: "GRAY", lambda i, n: "")
        self.assertEqual([o["name"] for o in result], ["A", "Odd"])
        self.assertEqual([o["name"] for o in extra], ["Odd"])
        result, _ = board.plan_options(current, ["A"], [], True, lambda i, n: "GRAY", lambda i, n: "")
        self.assertEqual([o["name"] for o in result], ["A"])

    def test_rename_of_missing_option_stops(self):
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            board.plan_options([], ["A"], ["Nope=A"], False, lambda i, n: "", lambda i, n: "")

    def project(self, options=OPTIONS, items=()):
        project = {"id": "P", "title": "T", "url": URL, "shortDescription": "", "closed": False, "items": {"totalCount": len(items)},
                   "repositories": {"nodes": [{"nameWithOwner": "acme/app"}]}, "views": {"nodes": []},
                   "fields": {"nodes": [{"__typename": "ProjectV2SingleSelectField", "id": "F", "name": "Status", "dataType": "SINGLE_SELECT", "options": options}]}}
        self.gh.on("POST", "shortDescription", {"data": {"organization": {"projectV2": project}}})
        self.gh.on("POST", "updateProjectV2Field", {"data": {"updateProjectV2Field": {"projectV2Field": {"options": []}}}})
        self.gh.on("POST", "pageInfo", {"data": {"organization": {"projectV2": {"items": {"pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": list(items)}}}}})

    def item(self, status, number=1):
        return {"id": "I%d" % number, "type": "ISSUE", "f0": {"name": status}, "content": {"number": number, "title": "t", "state": "OPEN", "closedAt": None, "repository": {"nameWithOwner": "a/b"}, "labels": {"nodes": []}, "assignees": {"nodes": []}}}

    def mutations(self):
        return [c for c in self.gh.calls if c[2] and b"updateProjectV2Field" in c[2]]

    def test_status_plan_writes_nothing(self):
        self.project()
        code, out = self.run_cmd("status-plan", URL, "--want", "Backlog,Ready,New")
        self.assertEqual(code, 0)
        self.assertIn("dry-run", out)
        self.assertEqual(self.mutations(), [])

    def test_status_apply_needs_yes(self):
        self.project()
        code, _ = self.run_cmd("status-apply", URL, "--want", "Backlog")
        self.assertEqual(code, 1)
        self.assertEqual(self.mutations(), [])

    def test_dropping_an_option_with_cards_needs_allow_drop(self):
        self.project(items=[self.item("Done")])
        code, out = self.run_cmd("status-apply", URL, "--want", "Backlog", "--drop-extra", "--yes")
        self.assertEqual(code, 1)
        self.assertIn("mất Status", out)
        self.assertEqual(self.mutations(), [])

    def test_apply_sends_existing_ids(self):
        self.project()
        code, _ = self.run_cmd("status-apply", URL, "--want", "Backlog,Ready,In Progress,In Review,In QC,Ready to Merge,Done", "--yes")
        self.assertEqual(code, 0)
        body = json.loads(self.mutations()[0][2])
        self.assertEqual([o.get("id") for o in body["variables"]["o"]], [o["id"] for o in OPTIONS])

    def test_shared_board_counts_only_this_repo(self):
        other = self.item("Ready", 2)
        other["content"]["repository"]["nameWithOwner"] = "x/other"
        self.project(items=[self.item("Ready", 1), other])
        code, out = self.run_cmd("inspect", URL, "--repo", "A/B")
        self.assertEqual((code, json.loads(out)["open_by_status"]["Ready"]), (0, 1))
        code, out = self.run_cmd("items", URL, "--repo", "a/b")
        self.assertEqual((code, out.count("\n")), (0, 1))

    def test_inspect_counts_by_status(self):
        self.project(items=[self.item("Ready", 1), self.item("Ready", 2), self.item("Done", 3)])
        code, out = self.run_cmd("inspect", URL)
        res = json.loads(out)
        self.assertEqual((code, res["open_by_status"]["Ready"], res["done_total"]), (0, 2, 1))


class Metrics(BoardCase):
    def row(self, number, comments, state="CLOSED", closed="2026-10-20T12:00:00Z", status="Done", labels=()):
        return {"st": {"name": status}, "content": {"number": number, "state": state, "closedAt": closed, "labels": {"nodes": [{"name": x} for x in labels]},
                                                    "comments": {"nodes": [{"createdAt": t, "body": b} for t, b in comments]}}}

    def test_flow_and_quality(self):
        rows = [
            self.row(1, [("2026-10-20T00:00:00Z", "[AF:DEV] start"), ("2026-10-20T02:00:00Z", "[AF:DEV] pr #9 @a"), ("2026-10-20T10:00:00Z", "[AF:QC] ✅ @a")]),
            self.row(2, [("2026-10-20T00:00:00Z", "[AF:DEV] start"), ("2026-10-20T01:00:00Z", "[AF:REVIEW] ❌ @a"), ("2026-10-20T02:00:00Z", "[AF:QC] ❌ @a"),
                         ("2026-10-20T03:00:00Z", "[AF:SYS] escalated"), ("2026-10-20T04:00:00Z", "[AF:DEV] ? cần hỏi"), ("2026-10-20T05:00:00Z", "[AF:SYS] qc-manual-pass")]),
            self.row(3, [("2026-10-01T00:00:00Z", "[AF:DEV] start")], state="OPEN", closed=None, status="Ready to Merge"),
            self.row(4, [("2026-10-20T00:00:00Z", "hello from a human")], state="OPEN", closed=None, status="Ready"),
        ]
        self.gh.on("POST", "pageInfo", {"data": {"organization": {"projectV2": {"items": {"pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": rows}}}}})
        now = dt.datetime(2026, 10, 25, tzinfo=dt.timezone.utc)
        with mock.patch.object(board.dt, "datetime", wraps=dt.datetime) as fake:
            fake.now.return_value = now
            code, out = self.run_cmd("metrics", URL, "--days", "30", "--stages", "ready_to_merge=Ready to Merge")
        self.assertEqual(code, 0, out)
        self.assertIn("tickets có [AF:] 3", out)
        self.assertIn("first-pass yield 50% (1/2)", out)
        self.assertIn("review ❌ 1 · QC ❌ 1 · escalated 1 · cần hỏi người 1", out)
        self.assertIn("#3 Ready to Merge", out)


CONFIG = """schema: 4
board:
  url: %s
  status: {backlog: Backlog, ready: Ready, in_progress: In Progress, in_review: In Review, in_qc: In QC, ready_to_merge: Ready to Merge, done: Done}
classify: label
types: {Bug: fix}
labels: {agent: agentflow, blocked: blocked, needs_info: needs-info, changes_requested: changes-requested, qc_failed: qc-failed, qc_manual: qc-manual, deploying: deploying}
git: {base: master, protected: [], branch: "{type}/{issue}-{slug}"}
staging: {branch: staging, url: "https://s.example"}
run: {models: {dev: {default: opus}}}
""" % URL


class Doctor(BoardCase):
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = os.path.realpath(self.tmp.name)
        subprocess.run(["git", "init", "-q", "-b", "master"], cwd=self.repo, check=True)
        with open(os.path.join(self.repo, ".gitignore"), "w") as fh:
            fh.write(".claude/settings.local.json\n")
        self.write_config(CONFIG)
        real_git = afconfig.git

        def fake_git(args, cwd=None, timeout=5):
            if args[:2] == ["remote", "get-url"]:
                return "git@github.com:acme/app.git"
            if args[0] == "ls-remote":
                return None if args[-1] in self.missing_branches else "x"
            return real_git(args, cwd=cwd, timeout=timeout)
        self.missing_branches = set()
        patcher = mock.patch.object(afconfig, "git", fake_git)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.good_github()

    def write_config(self, text):
        with open(os.path.join(self.repo, "agentflow.yaml"), "w") as fh:
            fh.write(text)

    def good_github(self, options=OPTIONS, labels=("agentflow", "blocked", "needs-info", "changes-requested", "qc-failed", "qc-manual", "deploying"), runs=1):
        project = {"id": "P", "title": "T", "url": URL, "shortDescription": "", "closed": False, "items": {"totalCount": 0},
                   "repositories": {"nodes": [{"nameWithOwner": "acme/app"}]}, "views": {"nodes": []},
                   "fields": {"nodes": [{"__typename": "ProjectV2SingleSelectField", "id": "F", "name": "Status", "dataType": "SINGLE_SELECT", "options": options}]}}
        self.gh.routes = []
        self.gh.on("GET", "/user", {"login": "me"}, headers={"x-oauth-scopes": "repo, project, read:org"})
        self.gh.on("POST", "shortDescription", {"data": {"organization": {"projectV2": project}}})
        self.gh.on("POST", "workflows", {"data": {"node": {"workflows": {"nodes": [{"name": "Item closed", "enabled": True}]}}}})
        self.gh.on("GET", "/labels", [{"name": x} for x in labels])
        self.gh.on("GET", "/rules/branches/staging", [])
        self.gh.on("GET", "/rules/branches/master", [{"type": "pull_request"}])
        self.gh.on("GET", "/commits/staging/check-runs", {"check_runs": []})
        self.gh.on("GET", "/commits/%s/check-runs" % SHA, {"check_runs": [{"name": "b", "status": "completed", "conclusion": "success"}] * runs, "total_count": runs})
        self.gh.on("GET", "/commits/%s/status" % SHA, {"statuses": [], "total_count": 0})
        self.gh.on("GET", "/commits/staging", {"sha": SHA})
        self.gh.on("GET", "/repos/acme/app", {"full_name": "acme/app", "owner": {"type": "Organization"}})

    def doctor(self):
        return self.run_cmd("doctor", "--root", self.repo)

    def test_healthy_repo(self):
        code, out = self.doctor()
        self.assertEqual(code, 0, out)
        self.assertIn("KẾT QUẢ: OK", out)
        self.assertIn("✓ pipeline staging", out)

    def test_board_option_mismatch(self):
        self.good_github(options=OPTIONS[:-1])
        code, out = self.doctor()
        self.assertEqual(code, 1)
        self.assertIn("board.status.done", out)

    def test_missing_label(self):
        self.good_github(labels=("agentflow",))
        code, out = self.doctor()
        self.assertEqual(code, 1)
        self.assertIn("labels thiếu: blocked", out)

    def test_missing_staging_branch(self):
        self.missing_branches = {"staging"}
        code, out = self.doctor()
        self.assertEqual(code, 1)
        self.assertIn("staging.branch 'staging' không có trên origin", out)

    def test_warns_when_no_pipeline_reports(self):
        self.good_github(runs=0)
        code, out = self.doctor()
        self.assertEqual(code, 0, out)
        self.assertIn("không có check nào", out)

    def test_warns_when_base_has_no_protection(self):
        self.gh.routes = [r for r in self.gh.routes if "/rules/branches/master" not in r[1]]
        self.gh.routes.insert(0, ("GET", "/rules/branches/master", [], 200, {}))
        self.gh.routes.insert(0, ("GET", "/repos/acme/app/branches/master", {"protected": False}, 200, {}))
        code, out = self.doctor()
        self.assertEqual(code, 0, out)
        self.assertIn("không có branch protection", out)

    def test_warns_on_duplicate_github_mcp(self):
        with open(os.path.join(self.repo, ".mcp.json"), "w") as fh:
            fh.write('{"mcpServers":{"gh":{"type":"http","url":"https://api.githubcopilot.com/mcp/"}}}')
        self.assertIn("loại trùng", self.doctor()[1])

    def test_schema_mismatch(self):
        self.write_config(CONFIG.replace("schema: 4", "schema: 3"))
        code, out = self.doctor()
        self.assertEqual(code, 1)
        self.assertIn("schema 3", out)

    def test_shape_problem_from_validate(self):
        self.write_config(CONFIG.replace("classify: label", "classify: nope"))
        code, out = self.doctor()
        self.assertEqual(code, 1)
        self.assertIn("classify", out)

    def test_no_config(self):
        os.remove(os.path.join(self.repo, "agentflow.yaml"))
        code, out = self.doctor()
        self.assertEqual(code, 1)
        self.assertIn("/agentflow:init", out)

    def test_tracked_settings_file_fails(self):
        os.makedirs(os.path.join(self.repo, ".claude"))
        with open(os.path.join(self.repo, ".claude", "settings.local.json"), "w") as fh:
            fh.write("{}")
        subprocess.run(["git", "add", "-f", ".claude/settings.local.json"], cwd=self.repo, check=True)
        code, out = self.doctor()
        self.assertEqual(code, 1)
        self.assertIn("TRACK", out)

    def test_token_never_printed(self):
        secret = "super-secret-value"
        with mock.patch.object(board, "_TOKEN", secret):
            _, out = self.doctor()
        self.assertNotIn(secret, out)


class Misc(BoardCase):
    def test_labels_create_or_update(self):
        self.gh.on("PATCH", "/labels/blocked", {}).on("POST", "/repos/o/r/labels", {})
        code, out = self.run_cmd("labels", "--repo", "o/r", "--label", "blocked|B60205|x", "--label", "new one|#123456|" + "y" * 200)
        self.assertEqual(code, 0, out)
        self.assertIn("= blocked", out)
        self.assertIn("+ new one", out)
        created = json.loads(self.gh.calls[-1][2])
        self.assertEqual((created["color"], len(created["description"])), ("123456", 100))

    def test_whoami_warns_on_broad_scope(self):
        self.gh.on("GET", "/user", {"login": "me"}, headers={"x-oauth-scopes": "repo, delete_repo"})
        _, out = self.run_cmd("whoami")
        self.assertIn("WARN", out)

    def test_bad_board_url(self):
        code, _ = self.run_cmd("inspect", "https://github.com/acme/app")
        self.assertEqual(code, 1)

    def test_help_lists_every_subcommand(self):
        with open(os.path.join(ROOT, "bin", "agentflow-board"), encoding="utf-8") as fh:
            source = fh.read()
        doc = source.split('"""')[1]
        for name in ("whoami", "inspect", "items", "status-plan", "status-apply", "ensure-field", "create", "repo", "labels", "issue-types", "metrics", "checks", "doctor"):
            self.assertIn(name, doc)


if __name__ == "__main__":
    unittest.main()
