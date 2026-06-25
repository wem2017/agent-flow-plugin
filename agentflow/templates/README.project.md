# AgentFlow — quick reference for this repo

This repo uses the **AgentFlow** plugin to coordinate a 3-agent dev workflow (PO → DEV → QC → human review) on GitHub. (The exact plugin version this config was authored against is pinned as `agentflow_version` in `.claude/agentflow.yaml`.) State lives in `flow:*` **labels** on each issue; a GitHub Projects v2 board is optional and only mirrors those labels for visual triage. Everything is configured in one file — `.claude/agentflow.yaml`, the single source of truth.

You only do two things by hand: **describe the work, and review/merge the PR.** Everything in between happens through GitHub.

## How to use

| You want to...                          | Run                              |
|-----------------------------------------|----------------------------------|
| Re-run / repair setup for this repo     | `/agentflow-init`                |
| Start the team for this session         | `/start`                         |
| File a new piece of work                | `/task <freeform description>`   |
| See where everything stands             | `/status`                        |

After `/start`, this terminal session becomes the orchestrator — describe work in plain text and the team (PO → DEV → QC) chains automatically. Need to reroute a card (back to PO, skip a stage, flag for a human)? Just say so in plain text inside `/start` — e.g. "send #12 back to PO" — and the orchestrator does it inline. The orchestrator only breaks back to you when it needs clarification, hits a 2-strike escalation (`needs-human`), or a PR is ready to merge.

## What this repo connects to

Connections are declared under `connections.*` in `.claude/agentflow.yaml`. Each block fully specifies its own wiring (secret name, scopes, MCP server). A connection is usable only when `enabled: true` **and** every var it requires is present (sourced from `.env`). They are additive — toggle one with `enabled: true|false`.

| Connection       | Required? | What it does                                                        |
|------------------|-----------|---------------------------------------------------------------------|
| `github`         | always on | Issues, branches, PRs, labels, comments — the protocol itself.      |
| `github_project` | optional  | GitHub Projects v2 board that **mirrors** `flow:*` labels for humans.|
| `figma`          | optional  | DEV pulls frame specs/tokens during UI work (via the `figma` MCP).  |

To turn the board or Figma on/off, edit the matching block's `enabled` flag (for the board, keep `connections.github_project.enabled` and `board.id` in sync — `/agentflow-init` does this for you). Labels stay authoritative regardless of the board.

## Environment variables

Every secret is declared by **name only** under the `env:` list in `.claude/agentflow.yaml` (each entry cross-links its `used_by` connections). The values live in a `.env` file you `source` before launching Claude Code:

| Var            | Required | For                                                  |
|----------------|----------|------------------------------------------------------|
| `GITHUB_TOKEN` | yes      | GitHub access (scopes: `repo`, `read:org`, `+ project` if board) |
| `FIGMA_TOKEN`  | no       | Figma legacy PAT — Framelink/REST fallback only; the official figma MCP server uses OAuth (no token) |

**Secret hygiene:** put these in an **uncommitted** `.env` (copy `.env.example`, fill it, then `source` it before launching Claude Code) — never commit a token, never paste a value into `agentflow.yaml`. Reference secrets only by name (`${GITHUB_TOKEN}`). `/agentflow-init` refuses to finish if a `required: true` var is missing.

## Surfaces (the buildable parts)

A **surface** is a buildable part of the repo, defined under `surfaces.*`. The map is **dynamic** — this repo declares only the surfaces it actually has, with keys the owner chose (e.g. `backend`, `web`, `api`, `admin`, `mobile`, or just `"."` for a single-surface repo). AgentFlow is tech-stack agnostic: each surface carries **its own** commands.

```
surfaces.<name>.path                  # glob root, "." for single-surface repos
surfaces.<name>.label                 # the component/<name> label that maps to it
surfaces.<name>.commands.{install,lint,test,integration,e2e,build}
surfaces.<name>.coverage_command / coverage_threshold
surfaces.<name>.forbidden_paths
```

`labels.component` is generated to match the surface keys — one `component/<surface>` per declared surface. PO tags each issue with the `component/<surface>` label(s) for the surface(s) it touches. DEV runs the touched surface's commands while coding; QC runs them as the gate. To change how a surface builds or what it must never touch, edit that surface's block. Leave a command `""` to skip it.

## QC tiers

A tier selects **which command-types run**, not specific shell commands. They are cumulative: `quick ⊆ full ⊆ regression`.

| Tier         | Command-types run                          |
|--------------|--------------------------------------------|
| `quick`      | `lint`, `test`                             |
| `full`       | `lint`, `test`, `integration`              |
| `regression` | `lint`, `test`, `integration`, `e2e`       |

For each surface the issue touches (by its `component/<surface>` labels), QC runs that surface's command for each type in the tier, in order; all must exit 0 (a `""` command is skipped). The actual shell commands live under `surfaces.<name>.commands.<type>`. Coverage uses the touched surface's `coverage_command`/`coverage_threshold`, falling back to `agents.qc.coverage_threshold`. Tune the tier definitions under `agents.qc.tiers.*`.

## Skills

Four core skills always ship with the plugin and are on automatically — no registration:

| Skill                    | Covers                                                         |
|--------------------------|----------------------------------------------------------------|
| `setup-agentflow`        | onboarding: yaml as source of truth, connections, env, surfaces, skill registry |
| `project-board-protocol` | the GitHub wire protocol: `flow:*` labels, comment prefixes, DoR/DoD, optional board |
| `git-flow-working`       | branching, Conventional Commits, PR conventions, rebase/merge safety |
| `figma-design`           | pull frame specs/tokens via the `figma` MCP; design → AC handoff |

To extend, add a project skill under `.claude/skills/<role>-<area>` so the right agent picks it up: `dev-*` → DEV, `qc-*` → QC, `po-*` → PO. Register it under `skills:` (the source-of-truth overview) so you can scope it to surfaces; agents also **auto-discover** any `.claude/skills/<their-role>-*` even if unlisted. An agent loads role-prefixed skills relevant to the surface(s) the current issue touches (registry `surfaces` matched against `component/*` labels; no `surfaces` = always relevant). `/agentflow-init` can scaffold starter stubs.

```yaml
skills:
  dev-mobile-development: { role: dev, surfaces: ["mobile"], description: "Mobile state & navigation conventions" }
  qc-automation-test:     { role: qc,  surfaces: ["web", "mobile"], description: "E2E suite authoring" }
  po-discovery:           { role: po,  description: "Discovery & story-mapping checklist" }
```

## What goes where (the `flow:*` label)

- **`flow:inbox` / `flow:refined`** — PO is shaping the request.
- **`flow:ready-for-dev`** — DEV will pick it up next.
- **`flow:in-progress`** — DEV is implementing. If DEV is blocked, you'll see a `[DEV]` blocked comment and the issue stays here for you to unblock.
- **`flow:in-qc`** — DEV opened a PR; QC is running the tier.
- **`flow:changes-requested`** — QC rejected; DEV is reworking.
- **`flow:ready-for-human-review`** — your turn. Review and merge the PR. (Two consecutive QC ❌ also lands here with `needs-human`.)
- **`flow:done`** — merged and closed.

Filter the issue list by any of these labels to see what's where (`gh issue list --label flow:in-qc`).

## Comment prefixes (so you can grep / filter)

`[PO]`, `[DEV]`, `[QC] ✅`, `[QC] ❌`, `[DEV→PO ?]`, `[QC→PO ?]`, `[PO→DEV]`, `[PO→QC]`, `[SYSTEM]`, `[USER:<your-login>]`.

Anything you write **without** a `[USER:...]` prefix is treated as untrusted context by the agents — they will read it but not act on instructions inside.

## Notifications

This is terminal mode — the orchestrator break-out **is** the notification. There are no external channels; watch this session for clarifications, `needs-human` escalations, and ready-to-merge PRs.
