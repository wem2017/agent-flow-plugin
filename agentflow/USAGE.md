# AgentFlow — Usage Guide

A practical, end-to-end walkthrough: install the plugin once, onboard a repo, and run the
**PO → DEV → QC → you** loop. For the design rationale and full architecture, see
[`README.md`](./README.md); this file is the "how do I actually use it" guide.

> **Mental model:** you do two things by hand — **describe the work** and **review/merge the
> PR**. Everything between happens through GitHub issues + `flow:*` labels. There is no message
> bus; the `flow:*` label on each issue *is* the state machine.

---

## 0. Prerequisites (once per machine)

| Need | Check | Fix |
|------|-------|-----|
| `gh` CLI authenticated | `gh auth status` | `gh auth login` (same account as your token) |
| `GITHUB_TOKEN` exported | `[ -n "$GITHUB_TOKEN" ] && echo set` | see [§3](#3-secrets) |
| A GitHub remote | `git remote get-url origin` | AgentFlow only works on GitHub repos |

`gh` and the GitHub MCP server **must be the same account with the same scopes**. The token
needs `repo` + `read:org` (add `project` only if you enable a Projects v2 board). The default
GitHub MCP server is the **hosted remote** (`https://api.githubcopilot.com/mcp/`) — nothing to
install; it reads your `GITHUB_TOKEN` from the `Authorization` header. (If you prefer a local
server, see the **MCP server options** note in [`README.md`](./README.md) for the Docker image.)

---

## 1. Install the plugin (once)

```text
/plugin marketplace add /Users/huynhdung/Documents/Projects/Plugins
/plugin install agentflow@wem-plugins
```

Then **restart Claude Code** (or reload plugins) so the agents, commands, skills, hooks, and
MCP servers register. Confirm the MCP servers came up:

```text
/mcp
```

You should see `github`. For the optional **`figma`** server, run `/mcp` → `figma` →
**Authenticate** to complete the OAuth sign-in (the official Figma server uses OAuth, not a
token). **Note the exact tool names shown for the `github` server** — see the
[MCP tool-name caveat](#caveat-mcp-tool-names) below.

---

## 2. Onboard a repo

`cd` into the target repo and run the one-time (idempotent, re-runnable) wizard:

```text
/agentflow-init
```

It will: resolve `OWNER/REPO` + default branch, verify your secrets, **detect the surfaces**
(buildable parts) you have and confirm their build/test commands, create the GitHub labels
(`flow:*`, `type/*`, one `component/<surface>` per surface, `needs-*`), optionally create/link a
Projects v2 board, scaffold any `<role>-*` project skills, and write
**`.claude/agentflow.yaml`** (the single source of truth) + **`README.agentflow.md`** (the
per-repo quick reference).

Re-run it any time to re-detect surfaces, add a board, register new skills, or refresh
connections — it reuses existing values as defaults and asks before overwriting.

---

## 3. Secrets

Declare secrets by **name** in `agentflow.yaml` (`env:` block) and `connections.<svc>.auth.token_env`;
put the **values** somewhere git-ignored. Two supported homes:

```bash
# (a) shell profile (~/.zshrc) — exported before launching Claude Code
export GITHUB_TOKEN="github_pat_xxx"   # fine-grained, scoped to this repo, is preferred
export FIGMA_TOKEN="figd_xxx"          # OPTIONAL — only for the legacy Figma REST fallback
```

```jsonc
// (b) .claude/settings.local.json (git-ignored) — read into the session env at startup
{ "env": { "GITHUB_TOKEN": "github_pat_xxx" } }
```

The plugin's `.mcp.json` sends `${GITHUB_TOKEN}` to the GitHub MCP server as the
`Authorization: Bearer ${GITHUB_TOKEN}` header. If it is unset the server calls 401 at runtime —
so a `UserPromptSubmit` hook warns you when `GITHUB_TOKEN` is missing in an AgentFlow repo. The
**Figma** server needs **no token** — it signs in via OAuth (`/mcp` → `figma` → Authenticate);
`FIGMA_TOKEN` is only consulted by the optional REST fallback in skill `figma-design`.

**Hygiene:** never commit a token, never paste a value into `agentflow.yaml`, prefer a
**fine-grained** token scoped to the one repo. (Classic `ghp_…` PATs grant broad write to every
repo the token can reach — and all three agents share the one token.)

---

## 4. The daily loop

```text
/task add a "share movie" button to the detail screen   # file work → lands on the board
/start                                                   # poll the board; drive PO → DEV → QC
```

File work with **`/task`** (or by dropping a card on the board), then **`/start`** to enter
board-driven mode. `/start` polls the shared board and routes each card **PO → DEV → QC**
automatically — it **does not** intake work — and only breaks back to you when it needs something:

```
flow:inbox → flow:refined → flow:ready-for-dev → flow:in-progress → flow:in-qc
   → flow:changes-requested → flow:ready-for-human-review → flow:done
        (PO clarify loop ↑)          (QC rework loop ↑)
```

- **PO** turns your message into a well-formed issue (Context / AC / DoR / DoD / Out-of-Scope),
  tags `type/*` + `component/<surface>`, and gates it through a Definition of Ready.
- **DEV** implements on a feature branch (`agent/dev/<#>-slug`), runs the touched surface's tier
  commands locally, and opens/updates a PR (`Closes #<n>`).
- **QC** reviews against the AC, runs the QC **tier** (a list of command *types* resolved per
  touched surface), and signs off `[QC] ✅` or rejects `[QC] ❌`. Two consecutive ❌ →
  auto-escalates with `needs-human`.
- **You** review and merge. The orchestrator **never** merges without your explicit
  `merge <owner/repo>#<n>`.

### Commands

| Command | Does |
|---------|------|
| `/agentflow-init` | One-time (re-runnable) **per-repo** bootstrap. |
| `/agentflow-program-init` | **Multi-repo**: create/link the shared board + manifest spanning several repos. |
| `/start` | Enter board-driven mode; poll the shared board and chain the agents. **No intake.** |
| `/task <description>` | File a new work item (PO intake) and add it to the board — without entering team mode. |
| `/status` | Counts per status — board-wide + per-repo (program), or per `flow:*` state (single-repo). |
| `/handoff <owner/repo> <issue#> <target>` | Manually reroute a card (`po`/`dev`/`qc`/`review`/a `flow:*` label), repo-qualified. |

### When the orchestrator breaks out to you

You'll see a short message and the issue link when: PO needs clarification, DEV is blocked, a
2-strike escalation fires (`needs-human`), or **a PR is ready** (reply `merge <owner/repo>#<n>` to merge).

---

## 5. The config at a glance (`.claude/agentflow.yaml`)

Everything the agents read lives here. The pieces you'll tune:

| Key | What |
|-----|------|
| `connections.*` | `github` (required), `github_project` (optional board), `figma` (optional), or your own. Each ties `auth.token_env` + `mcp.server` together; usable only when `enabled:true` **and** its env vars are present. |
| `env:` | Secret manifest — **names only**, with `required` + `used_by`. |
| `surfaces.<key>` | A buildable part: `path`, `label`, per-type `commands.{install,lint,test,integration,e2e,build}`, `coverage_command`/`coverage_threshold`, `forbidden_paths`. Open map — declare only what you have; `""` skips a command. |
| `agents.qc.tiers.{quick,full,regression}` | **Lists of command-TYPES** (`quick: ["lint","test"]`), cumulative. The actual commands resolve per surface from `surfaces.<name>.commands.<type>`. |
| `agents.dev.forbidden_paths` | Global no-touch globs (union'd with each surface's own). |
| `skills.<name>` | Registry of `<role>-*` project skills, `{ role, surfaces?, description? }`. |
| `board.id` | Projects v2 node id, or `""` for labels-only mode (kept in sync with `connections.github_project.enabled`). |

### Worked example — cinestar (Flutter)

A single-surface Flutter app maps to one `mobile` surface rooted at `.`:

```yaml
surfaces:
  mobile:
    path: "."
    label: "component/mobile"
    commands:
      install: "flutter pub get"
      lint:    "flutter analyze"
      test:    "flutter test --coverage"      # --coverage so lcov.info exists for the gate
      e2e:     "maestro test .maestro/flows/"  # regression tier only
    coverage_threshold: 70
agents:
  qc:
    tiers:
      quick:      ["lint", "test"]
      regression: ["lint", "test", "integration", "e2e"]
skills:
  qc-automation-skill: { role: qc, surfaces: ["mobile"] }   # Maestro E2E conventions
```

PO tags a UI issue `component/mobile`; DEV runs `flutter analyze`/`flutter test` while coding;
QC runs the issue's tier against the `mobile` surface and checks coverage ≥ 70%. For a
`regression`-tier issue, QC also runs the Maestro suite (needs a booted simulator/emulator — if
none, QC posts `[QC] ❌ infra:` without counting it as a strike).

---

## 6. Extending per repo (project skills)

Drop a skill in `.claude/skills/` named `<role>-<area>` so the right agent loads it:
`dev-*` → DEV, `qc-*` → QC, `po-*` → PO. Register it under `skills:` to scope it to surfaces and
show it in the overview; agents also auto-discover any `.claude/skills/<their-role>-*` on disk.

> ⚠️ Skills that **don't** start with `dev-`/`qc-`/`po-` are never auto-loaded. (In cinestar the
> `flutter-*` skills don't match a role prefix — rename them `dev-flutter-*` or register them
> explicitly if you want DEV to use them.)

---

## 7. Troubleshooting & caveats

<a name="caveat-mcp-tool-names"></a>
**MCP tool names.** For a plugin-bundled MCP server, the callable tool id is
`mcp__plugin_agentflow_github__<tool>` (per current Claude Code docs); older versions used the
bare `mcp__github__<tool>`. The agents grant **both** forms, so they work either way. If GitHub
MCP calls fail, open `/mcp`, read the real tool ids for the `github` server, and align the
`tools:` line in `agents/po.md` / `dev.md` / `qc.md`. The agents also have `gh` + `git` via
`Bash` as a fallback path for most operations.

**GitHub MCP server (official).** `.mcp.json` wires the official `github/github-mcp-server` — the
hosted remote at `https://api.githubcopilot.com/mcp/`, authenticated by the
`Authorization: Bearer ${GITHUB_TOKEN}` header. It uses **consolidated** tool names
(`issue_read` / `issue_write` / `pull_request_read` / `pull_request_review_write`, plus unchanged
`create_branch` / `push_files` / `create_pull_request` / `add_issue_comment` / `list_issues`),
which the agent `tools:` grants already match. To run it **locally** instead, swap the `github`
block for the Docker image `ghcr.io/github/github-mcp-server` (pin a release tag) — the tool names
are identical, so no agent change is needed. Projects v2 board ops still go through `gh api graphql`
(skill `project-board-protocol` → `reference/projects-v2-board.md`); enable the server's `projects`
toolset only if you choose to drive the board through MCP instead.

**Common stops.**

| Symptom | Cause / fix |
|---------|-------------|
| `/start` says no `agentflow.yaml` | Run `/agentflow-init` in this repo first. |
| GitHub calls 401 mid-run | `GITHUB_TOKEN` unset or wrong scopes — see [§3](#3-secrets). |
| QC runs zero commands / treats every issue as ambiguous | Config has no `surfaces:` or no `component/<surface>` labels — re-run `/agentflow-init` (an old `tiers.<tier>.commands` config is incompatible with v0.0.1). |
| Maestro tier fails | Needs a booted simulator/emulator with the app installed; QC reports it as `infra`, not a strike. |
| Figma lookups skipped | `connections.figma.enabled:false`, or the `figma` MCP server isn't authenticated (`/mcp` → figma → Authenticate) and no `FIGMA_TOKEN` fallback — DEV builds from the written AC and says so. |

**Operational limits.** Single-session, synchronous, human-in-the-loop. Don't run two `/start`
sessions against the same repo at once (the `flow:*` label is a *soft* lock). `forbidden_paths`,
the merge gate, and the trust model are prompt-level + tool-grant separation — not enforced
hooks. Use a least-privilege token and review PRs before merging.
