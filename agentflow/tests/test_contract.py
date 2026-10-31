#!/usr/bin/env python3
"""Contract between prompts, config and code. Prompts are the program here: a wrong section number, a renamed label or a
missing subcommand fails at run time in front of a user, unless it fails here first."""

import ast
import glob
import json
import os
import re
import stat
import sys
import unittest

ROOT = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import afconfig  # noqa: E402

# Runtime prompts cost tokens on every run. Limits are characters, since one line can hold hundreds of them.
# Do not raise a limit to fit a change: remove something first (CONTRIBUTING.md §Quy ước).
BUDGETS = {
    "agents/dev.md": 7200, "agents/reviewer.md": 7000, "agents/qc.md": 7400,
    "references/protocol.md": 11600, "references/dispatch.md": 9000, "references/design.md": 2800,
    "skills/init/SKILL.md": 10400, "skills/learn/SKILL.md": 5800, "skills/do/SKILL.md": 2400, "skills/doctor/SKILL.md": 2200,
    "skills/run/SKILL.md": 2600, "skills/status/SKILL.md": 3000, "skills/task/SKILL.md": 3900, "skills/init/references/board-setup.md": 5200,
}
PER_SPAWN_LIMIT = 19000  # agent prompt + protocol, read on every spawn
DESCRIPTION_LIMIT = 700


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


def frontmatter(rel):
    text = read(rel)
    assert text.startswith("---\n"), rel
    return afconfig.parse_yaml(text.split("---\n", 2)[1])


def prompts():
    out = []
    for pattern in ("agents/*.md", "references/*.md", "skills/*/SKILL.md", "skills/*/references/*.md"):
        out += glob.glob(os.path.join(ROOT, pattern))
    return sorted(os.path.relpath(p, ROOT) for p in out)


def all_docs():
    return prompts() + ["README.md", "CONTRIBUTING.md", "DESIGN-NOTES.md", "PRIVACY.md", "templates/board-readme.md"]


def code_files():
    return [p for p in glob.glob(os.path.join(ROOT, "bin", "*")) + glob.glob(os.path.join(ROOT, "scripts", "*.py")) if os.path.isfile(p)]


def headings(rel):
    return set(re.findall(r"^## (\d+[a-z]?)\.", read(rel), re.M))


TEMPLATE = afconfig.parse_yaml(read("agentflow.yaml"))
AGENTS = ["dev", "reviewer", "qc"]
SKILLS = ["do", "doctor", "init", "learn", "run", "status", "task"]


class Budget(unittest.TestCase):
    def test_every_prompt_has_a_budget(self):
        self.assertEqual(set(prompts()), set(BUDGETS))

    def test_within_budget(self):
        for rel, limit in BUDGETS.items():
            with self.subTest(rel):
                self.assertLessEqual(len(read(rel)), limit)

    def test_per_spawn_cost(self):
        protocol = len(read("references/protocol.md"))
        for agent in AGENTS:
            with self.subTest(agent):
                self.assertLessEqual(len(read("agents/%s.md" % agent)) + protocol, PER_SPAWN_LIMIT)

    def test_skill_files_under_the_platform_limit(self):
        for rel in prompts():
            self.assertLess(read(rel).count("\n"), 500, rel)


class Frontmatter(unittest.TestCase):
    def test_agents(self):
        for name in AGENTS:
            rel = "agents/%s.md" % name
            meta = frontmatter(rel)
            with self.subTest(name):
                self.assertEqual(meta["name"], name)
                self.assertLessEqual(len(meta["description"]), DESCRIPTION_LIMIT)
                self.assertIn(meta["model"], ("opus", "sonnet", "haiku", "fable", "inherit"))
                self.assertIsInstance(meta["maxTurns"], int)
                for ignored in ("hooks", "mcpServers", "permissionMode"):  # plugin agents ignore these: they would give false comfort
                    self.assertNotIn(ignored, meta)

    def test_agents_can_reach_what_their_prompt_uses(self):
        for name in AGENTS:
            tools = [t.strip() for t in frontmatter("agents/%s.md" % name)["tools"].split(",")]
            with self.subTest(name):
                self.assertIn("ToolSearch", tools)  # MCP tools are deferred
                self.assertIn("mcp__plugin_agentflow_github__*", tools)
                self.assertIn("Bash", tools)
                self.assertNotIn("Agent", tools)

    def test_least_privilege(self):
        tools = {n: frontmatter("agents/%s.md" % n)["tools"] for n in AGENTS}
        self.assertNotRegex(tools["qc"], r"\b(Edit|Write)\b")
        self.assertNotRegex(tools["reviewer"], r"\bWrite\b")
        self.assertRegex(tools["reviewer"], r"\bEdit\b")  # conflicts on staging
        self.assertIn("mcp__claude-in-chrome__*", tools["qc"])
        self.assertNotIn("mcp__claude-in-chrome__*", tools["dev"])

    def test_mcp_prefix_matches_the_manifest(self):
        servers = json.loads(read(".mcp.json"))["mcpServers"]
        for name in AGENTS:
            for server in re.findall(r"mcp__plugin_agentflow_(\w+?)__", read("agents/%s.md" % name)):
                self.assertIn(server, servers)

    def test_skills(self):
        self.assertEqual(sorted(os.listdir(os.path.join(ROOT, "skills"))), SKILLS)
        for name in SKILLS:
            meta = frontmatter("skills/%s/SKILL.md" % name)
            with self.subTest(name):
                self.assertEqual(meta["name"], name)
                self.assertIs(meta["disable-model-invocation"], True)
                self.assertLessEqual(len(meta["description"]), DESCRIPTION_LIMIT)

    def test_read_only_skills_preapprove_only_read_commands(self):
        for name in ("status", "doctor"):
            allowed = frontmatter("skills/%s/SKILL.md" % name)["allowed-tools"]
            self.assertNotRegex(allowed, r"status-apply|create|labels|ensure-field|set-secret|Write|Edit")


class Manifest(unittest.TestCase):
    def test_plugin_json(self):
        meta = json.loads(read(".claude-plugin/plugin.json"))
        self.assertRegex(meta["version"], r"^\d+\.\d+\.\d+$")
        self.assertIs(meta["defaultEnabled"], False)
        self.assertTrue(os.path.isfile(os.path.join(ROOT, meta["privacyPolicyUrl"].rsplit("/agentflow/", 1)[1])))
        self.assertTrue(os.path.isfile(os.path.join(ROOT, "LICENSE")))

    def test_marketplace_points_here(self):
        market = json.loads(read("../.claude-plugin/marketplace.json"))
        self.assertEqual([(p["name"], p["source"]) for p in market["plugins"]], [("agentflow", "./agentflow")])

    def test_hooks(self):
        hooks = json.loads(read("hooks/hooks.json"))["hooks"]
        pre = hooks["PreToolUse"][0]
        command = pre["hooks"][0]
        self.assertEqual(command["onFailure"], "block")  # a broken guard must not mean no guard
        self.assertIn("-I", command["command"])
        for tool in ("Bash", "Monitor", "Edit", "Write", "NotebookEdit", "Read", "Grep"):
            self.assertRegex(tool, "^(%s)$" % pre["matcher"])
        self.assertRegex("mcp__plugin_agentflow_github__merge_pull_request", "^(%s)$" % pre["matcher"])
        self.assertRegex("agentflow:dev", hooks["SubagentStop"][0]["matcher"])

    def test_every_script_a_hook_or_mcp_config_runs_exists(self):
        for rel in ("hooks/hooks.json", ".mcp.json"):
            for path in re.findall(r"\$\{CLAUDE_PLUGIN_ROOT\}/([\w./-]+)", read(rel)):
                self.assertTrue(os.path.isfile(os.path.join(ROOT, path)), path)

    def test_bin_is_executable_python_3_9(self):
        for path in code_files():
            with open(path, encoding="utf-8") as fh:
                source = fh.read()
            ast.parse(source, filename=path, feature_version=(3, 9))
            if "/bin/" in path:
                self.assertTrue(os.stat(path).st_mode & stat.S_IXUSR, path)
                self.assertTrue(source.startswith("#!/usr/bin/env python3"), path)

    def test_stdlib_only(self):
        allowed = set(sys.stdlib_module_names) if hasattr(sys, "stdlib_module_names") else None
        for path in code_files():
            with open(path, encoding="utf-8") as fh:
                tree = ast.parse(fh.read())
            for node in tree.body:  # top-level only: yaml and certifi are optional, imported inside functions
                names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module] if isinstance(node, ast.ImportFrom) else []
                for name in names:
                    root = name.split(".")[0]
                    if allowed is not None and root not in ("afconfig", "shellparse"):
                        self.assertIn(root, allowed, path)


class References(unittest.TestCase):
    def test_plugin_root_paths_exist(self):
        for rel in prompts():
            for path in re.findall(r"\$\{CLAUDE_PLUGIN_ROOT\}/([\w./-]+[\w/])", read(rel)):
                with self.subTest("%s → %s" % (rel, path)):
                    self.assertTrue(os.path.exists(os.path.join(ROOT, path)))

    def test_cross_file_sections_exist(self):
        targets = {"protocol": "references/protocol.md", "dispatch": "references/dispatch.md"}
        for rel in all_docs():
            for doc, section in re.findall(r"\b(protocol|dispatch)(?:\.md)? §(\d+[a-z]?)", read(rel)):
                with self.subTest("%s → %s §%s" % (rel, doc, section)):
                    self.assertIn(section, headings(targets[doc]))

    def test_own_sections_exist(self):
        for rel in ["agents/%s.md" % a for a in AGENTS] + ["references/protocol.md", "references/dispatch.md"]:
            text = re.sub(r"\b(protocol|dispatch)(\.md)? §\d+[a-z]?(–§?\d+)?", "", read(rel))
            text = re.sub(r"§[A-ZĐ][\wÀ-ỹ-]*", "", text)
            have = headings(rel)
            for section in re.findall(r"§(\d+[a-z]?)", text):
                with self.subTest("%s §%s" % (rel, section)):
                    self.assertIn(section, have)

    def test_learn_gate_section_exists(self):
        self.assertIn("## Non-goals", read("DESIGN-NOTES.md"))
        self.assertIn("§Non-goals", read("skills/learn/SKILL.md"))

    def test_board_subcommands_exist(self):
        source = read("bin/agentflow-board")
        have = set(re.findall(r'add_parser\("([\w-]+)"\)', source)) | set(re.findall(r'"([\w-]+)":\s*cmd_', source))
        for rel in all_docs():
            for sub in re.findall(r"agentflow-board ([a-z][a-z-]+)", read(rel)):
                with self.subTest("%s: %s" % (rel, sub)):
                    self.assertIn(sub, have)

    def test_board_flags_exist(self):
        source = read("bin/agentflow-board")
        for rel in prompts():
            for line in read(rel).splitlines():
                if "agentflow-board " not in line:
                    continue
                for flag in re.findall(r"(?<![\w-])(--[a-z][a-z-]+)", line.split("agentflow-board ", 1)[1]):
                    if flag == "--help":
                        continue
                    with self.subTest("%s: %s" % (rel, flag)):
                        self.assertIn('"%s"' % flag, source)

    def test_tool_subcommands_exist(self):
        settings, journal = read("bin/agentflow-settings"), read("bin/agentflow-journal")
        for rel in all_docs():
            text = read(rel)
            for sub in re.findall(r"agentflow-settings ([a-z-]+)", text):
                self.assertIn('"%s"' % sub, settings, rel)
            for sub in re.findall(r"agentflow-journal ([a-z]+)", text):
                self.assertIn('"%s"' % sub, journal, rel)

    def test_config_keys_exist(self):
        sections = ("git", "staging", "run", "notify", "design", "labels", "people", "board")
        for rel in prompts():
            text = re.sub(r"`[^`]*\.(md|py|json|yaml|yml)\b[^`]*`", "", read(rel))
            for section, key in re.findall(r"(?<![\w./-])(%s)\.([a-z_]+)(?![\w-]*\.(?:md|py|json|com))\b" % "|".join(sections), text):
                if key in ("md", "py", "json", "yaml"):
                    continue
                with self.subTest("%s: %s.%s" % (rel, section, key)):
                    self.assertIn(key, TEMPLATE[section] or {})

    def test_board_status_and_field_keys_exist(self):
        for rel in prompts():
            text = read(rel)
            for stage in re.findall(r"board\.status\.([a-z_]+)", text):
                self.assertIn(stage, afconfig.STAGES, rel)
            for key in re.findall(r"\bfields\.([a-z]+)", text):
                self.assertIn(key, TEMPLATE["board"]["fields"], rel)


class StateMachine(unittest.TestCase):
    """Rules whose loss leaves a ticket stuck or unverified. Each was a real defect or sits next to one: E2E covers the happy
    path and rework, this keeps the branches that are too costly to run from being edited away."""

    RULES = [
        ("references/dispatch.md", r"\*feedback\*:.*gỡ `qc_manual`", "feedback phải gỡ qc_manual, không thì ticket quay về chờ người"),
        ("references/dispatch.md", r"\*qc-failed\*:.*không spawn DEV", "escalate thì không spawn"),
        ("references/dispatch.md", r"`contains: false`.*\*redeploy\*.*`in_review`", "staging bị reset thì deploy lại, không kẹt blocked"),
        ("references/dispatch.md", r"PR đã đóng mà không merge.*`blocked`", "PR đóng không merge phải có lối ra"),
        ("references/dispatch.md", r"is:issue repo:<owner>/<repo>", "hàng đợi lọc đúng repo"),
        ("references/dispatch.md", r"Không có `RESULT`.*`blocked`", "agent chết giữa chừng"),
        ("references/protocol.md", r"\*\*Trước bước 1\*\*", "so Status trước khi ghi"),
        ("references/protocol.md", r"Status write — cuối cùng, commit point", "Status ghi cuối cùng"),
        ("references/dispatch.md", r"\*pipeline-ok\*: gỡ `deploying`", "pipeline xong phải gỡ deploying"),
        ("references/dispatch.md", r"\*done\*: Status → `done`", "PR đã merge thì ticket tới done"),
        ("references/dispatch.md", r"\*qc-manual-pass\*:.*`update_pull_request draft=false`", "QC người pass thì undraft"),
        ("references/dispatch.md", r"\*feedback\*:.*`update_pull_request draft=true`", "feedback đưa PR về draft"),
        ("references/dispatch.md", r"\*pipeline-timeout\*.*gắn `blocked`", "pipeline quá giờ phải báo người"),
        ("references/protocol.md", r"`review_round > run.max_review_rounds`.*\*\*escalate\*\*", "hết lượt review thì escalate"),
        ("agents/reviewer.md", r"Status → `in_qc`", "reviewer deploy xong chuyển In QC"),
        ("agents/reviewer.md", r"gắn `deploying`", "reviewer gắn deploying"),
        ("agents/qc.md", r"\[AF:QC\] stale", "QC phát hiện staging chưa có head PR"),
        ("references/protocol.md", r"round đã tính, không tăng lần nữa", "chạy lại sau crash không tăng round"),
        ("references/protocol.md", r"`author_association`.*untrusted", "không tin comment của người ngoài"),
        ("references/protocol.md", r"perPage=100", "phân trang comment"),
        ("agents/reviewer.md", r"\|\| \{ echo MERGE_CONFLICT", "conflict dừng khối deploy"),
        ("agents/reviewer.md", r"gỡ `changes_requested`", "reviewer ✅ gỡ label rework"),
        ("agents/reviewer.md", r"Verdict mới nhất là ✅ `@<head sha>`.*§5", "deploy lại không review lại"),
        ("agents/qc.md", r"\*\*`update_pull_request draft=false`\*\*", "QC ✅ undraft"),
        ("agents/qc.md", r"gỡ `qc_failed`, `qc_manual`", "QC ✅ dọn label"),
        ("agents/qc.md", r"stage: ready`.*gắn `qc_failed`", "QC ❌ về ready"),
        ("agents/dev.md", r"\*\*`draft=true`\*\*", "PR luôn draft"),
        ("agents/dev.md", r"WT bẩn", "resume sau crash"),
        ("skills/do/SKILL.md", r"áp bảng dispatch §3", "/do đi qua cùng bảng hành động"),
    ]

    def test_rules_still_stated(self):
        for rel, pattern, why in self.RULES:
            with self.subTest(why):
                self.assertRegex(read(rel), pattern)

    def test_every_label_has_a_remover(self):
        text = "".join(read(p) for p in prompts())
        for key in ("changes_requested", "qc_failed", "qc_manual", "deploying"):
            with self.subTest(key):
                self.assertRegex(text, r"gỡ[^.\n]{0,60}`%s`" % key)


class RealGitHubMcp(unittest.TestCase):
    """tests/e2e/github_tools.json is what the real server answered to tools/list. Re-record it when the server changes."""

    def setUp(self):
        self.tools = json.loads(read("tests/e2e/github_tools.json"))
        self.text = "\n".join(read(p) for p in prompts())

    def test_methods_the_prompts_call_exist(self):
        for tool, method in re.findall(r"\b(\w+) method=(\w+)", self.text):
            if tool in self.tools:
                with self.subTest("%s method=%s" % (tool, method)):
                    self.assertIn(method, self.tools[tool]["properties"]["method"]["enum"])

    def test_parameters_the_prompts_rely_on_exist(self):
        props = lambda tool: self.tools[tool]["properties"]
        self.assertIn("updated_field", props("projects_write"))
        self.assertIn("draft", props("update_pull_request"))
        self.assertIn("draft", props("create_pull_request"))
        self.assertIn("event", props("pull_request_review_write"))
        self.assertIn("field_names", props("projects_list"))
        self.assertIn("field_names", props("projects_get"))
        self.assertIn("perPage", props("issue_read"))
        self.assertNotIn("per_page", self.text)
        for key in ("failed_only", "return_content", "tail_lines"):
            self.assertIn(key, props("get_job_logs"))

    def test_guard_knows_the_dangerous_tool_names(self):
        guard = read("scripts/guard.py")
        for name in ("merge_pull_request", "actions_run_trigger"):
            self.assertIn(name, self.tools)
            self.assertIn(name, guard)


class Evals(unittest.TestCase):
    CASES = ["dev-dor-missing-ac", "guard-force-push", "guard-secret-read", "reviewer-escalates", "reviewer-rejects"]

    def graders(self):
        for path in glob.glob(os.path.join(ROOT, "evals", "*", "graders", "*.md")):
            yield os.path.relpath(path, ROOT), frontmatter(os.path.relpath(path, ROOT))

    def test_cases_have_everything(self):
        names = sorted(d for d in os.listdir(os.path.join(ROOT, "evals")) if os.path.isfile(os.path.join(ROOT, "evals", d, "case.yaml")))
        self.assertEqual(names, self.CASES)
        for name in names:
            meta = afconfig.parse_yaml(read("evals/%s/case.yaml" % name))
            self.assertEqual(meta["name"], name)
            self.assertTrue(os.stat(os.path.join(ROOT, "evals", name, "fixture.sh")).st_mode & stat.S_IXUSR)
            self.assertTrue(os.path.isfile(os.path.join(ROOT, "evals", name, "prompt.md")))
            self.assertIn(name, read("evals/README.md"))

    def test_trace_regex_is_anchored_to_a_tool_call(self):
        """Unanchored, a trace regex also matches the prompts the agent read: `[AF:REVIEW] deployed` is in reviewer.md."""
        for rel, meta in self.graders():
            if meta.get("type") == "regex" and meta.get("target") == "trace" and "[AF:" in meta["pattern"]:
                with self.subTest(rel):
                    self.assertTrue(meta["pattern"].startswith('"name":"mcp__plugin_agentflow_github__'))

    def test_llm_grader_can_see_the_verdict(self):
        for rel, meta in self.graders():
            if meta.get("type") == "llm":
                self.assertEqual(meta.get("focus"), "trace", rel)

    def test_mocks_name_tools_the_prompts_use(self):
        text = "".join(read(p) for p in prompts())
        for path in glob.glob(os.path.join(ROOT, "evals", "**", "mocks", "github", "*.md"), recursive=True):
            name = os.path.basename(path)[:-3]
            with self.subTest(name):
                self.assertIn(name, text)

    def test_runner_never_publishes_and_keeps_the_real_manifest(self):
        runner = read("evals/run.sh")
        self.assertIn("--no-publish", runner)
        self.assertIn("$TMP/agentflow/.claude-plugin/plugin.json", runner)
        self.assertIs(json.loads(read(".claude-plugin/plugin.json"))["defaultEnabled"], False)


class SharedFacts(unittest.TestCase):
    def test_schema(self):
        self.assertEqual(TEMPLATE["schema"], afconfig.SCHEMA)
        self.assertIn("(schema %d)" % afconfig.SCHEMA, read("references/protocol.md"))
        self.assertIn("`schema` phải là `%d`" % afconfig.SCHEMA, read("references/protocol.md"))
        self.assertIn("schema %d" % afconfig.SCHEMA, read("skills/init/SKILL.md"))

    def test_stages_everywhere(self):
        self.assertEqual(list(TEMPLATE["board"]["status"]), afconfig.STAGES)
        protocol_stages = re.findall(r"^\| `([a-z_]+)` \|", read("references/protocol.md").split("## 2.")[1].split("## 3.")[0], re.M)
        self.assertEqual(protocol_stages, afconfig.STAGES)
        board = read("bin/agentflow-board")
        for table in ("STATUS_COLORS", "STATUS_DESC"):
            body = board.split(table + " = {", 1)[1].split("}", 1)[0]
            self.assertEqual(re.findall(r'"([a-z_]+)":', body), afconfig.STAGES, table)
        setup = read("skills/init/references/board-setup.md")
        self.assertEqual(re.findall(r"^\| `([a-z_]+)` \| [A-Z]", setup.split("## Link board")[1].split("Thiếu stage")[0], re.M), afconfig.STAGES)

    def test_labels_everywhere(self):
        self.assertEqual(list(TEMPLATE["labels"]), afconfig.LABEL_KEYS)
        setup = read("skills/init/references/board-setup.md").split("## Label")[1].split("Repo đã có")[0]
        rows = re.findall(r"^\| `([a-z_]+)` \| ([\w-]+) \|", setup, re.M)
        self.assertEqual(rows, list(TEMPLATE["labels"].items()))
        for rel in prompts():
            for key in re.findall(r"labels\.([a-z_]+)", read(rel)):
                self.assertIn(key, afconfig.LABEL_KEYS, rel)

    def test_prompts_use_label_keys_not_literal_names(self):
        for name in ("agents/dev.md", "agents/reviewer.md", "agents/qc.md", "references/dispatch.md"):
            self.assertNotRegex(read(name), r"gắn `(needs-info|changes-requested|qc-failed|qc-manual)`", name)

    def test_comment_heads_are_documented(self):
        table = read("references/protocol.md").split("## 5.")[1].split("## 6.")[0]
        known = set(re.findall(r"\[AF:(\w+)\] ([^\s`@#<]+)", table))
        sys_events = re.search(r"`\[AF:SYS\] <event>` \| ([^\n]+)", table).group(1)
        known |= {("SYS", e) for e in re.findall(r"`([a-z-]+)`", sys_events)}
        for rel in ["agents/%s.md" % a for a in AGENTS] + ["references/dispatch.md"] + ["skills/%s/SKILL.md" % s for s in SKILLS] + ["templates/board-readme.md", "bin/agentflow-board"]:
            for role, events in re.findall(r"\[AF:(\w+)\] ([^\s`@#<\"…]+)", read(rel)):
                for event in events.split("|"):
                    with self.subTest("%s: [AF:%s] %s" % (rel, role, event)):
                        self.assertIn((role, event), known)

    def test_every_role_prefix_used_by_its_agent(self):
        self.assertIn("[AF:DEV]", read("agents/dev.md"))
        self.assertIn("[AF:REVIEW]", read("agents/reviewer.md"))
        self.assertIn("[AF:QC]", read("agents/qc.md"))

    def test_result_values(self):
        check = read("scripts/result-check.py")
        values = re.search(r"\(ok\|([\w|]+)\)", check).group(0).strip("()").split("|")
        protocol = re.search(r"RESULT: <stage hiện tại> · <([\w|]+)>", read("references/protocol.md")).group(1).split("|")
        self.assertEqual(values, protocol)
        for value in re.findall(r"RESULT: [\w<>`]+ · ([a-z_]+)", "".join(read("agents/%s.md" % a) for a in AGENTS)):
            self.assertIn(value, protocol)

    def test_journal_kinds(self):
        kinds = re.search(r'KINDS = \(([^)]*)\)', read("bin/agentflow-journal")).group(1)
        code = set(re.findall(r'"(\w+)"', kinds))
        documented = set(re.findall(r"`(\w+)`", read("references/protocol.md").split("`kind`:")[1].split("\n")[0]))
        self.assertEqual(code - {"other"}, documented)
        for rel in prompts():
            for kind in re.findall(r"journal `(?:kind=)?(\w+)`", read(rel)):
                self.assertIn(kind, code, rel)

    def test_notify_events(self):
        self.assertEqual(set(TEMPLATE["notify"]["events"]), afconfig.NOTIFY_EVENTS)
        for rel in prompts():
            for event in re.findall(r"agentflow-notify (\w+) ", read(rel)):
                self.assertIn(event, afconfig.NOTIFY_EVENTS, rel)

    def test_default_forbidden_documented(self):
        for doc in ("references/protocol.md", "agentflow.yaml"):
            text = read(doc)
            for pattern in afconfig.DEFAULT_FORBIDDEN:
                name = pattern.replace("**/", "")
                if name == ".env":
                    continue
                needle = ".env" if name == ".env.*" else name
                self.assertIn(needle, text, "%s thiếu %s" % (doc, pattern))

    def test_agent_mode_and_input_line_up_with_dispatch(self):
        dispatch = read("references/dispatch.md")
        self.assertIn("MODE=new", dispatch)
        for mode in ("new", "rework", "resume"):
            self.assertIn("`%s`" % mode, read("agents/dev.md"))
        for agent in AGENTS:
            self.assertIn("agentflow:<dev|reviewer|qc>", dispatch)
            self.assertIn("RESULT", read("agents/%s.md" % agent))
            self.assertIn("references/protocol.md", read("agents/%s.md" % agent))

    def test_docs_list_every_command_and_agent(self):
        readme = read("README.md")
        for name in SKILLS:
            self.assertIn("/agentflow:%s" % name, readme)
        for name in AGENTS:
            self.assertIn("%s.md" % name, readme)

    def test_no_stale_claims(self):
        notes = read("DESIGN-NOTES.md")
        self.assertNotIn("isolation: worktree` truyền lúc spawn", notes)
        self.assertNotIn("hook không phân biệt role", notes)
        self.assertNotIn("CHANGELOG", "".join(read(p) for p in all_docs()))


if __name__ == "__main__":
    unittest.main()
