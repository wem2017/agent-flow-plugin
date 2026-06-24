---
description: Bootstrap AgentFlow in the current repo — resolve project + summary, wire connections (full auth/MCP spec), detect the surfaces that exist, create flow:*/type/*/component/* labels, optionally a board, optionally scaffold role-prefixed project skills, then write .claude/agentflow.yaml + README.agentflow.md.
argument-hint: (no args — runs an interactive setup wizard)
---

You are bootstrapping **AgentFlow** in the user's CURRENT repository. This is a one-time
setup, but it is **idempotent and re-runnable** — users re-run it to re-detect surfaces,
add a board later, register new skills, or refresh env/connections. Never destroy a
hand-edited `.claude/agentflow.yaml` without warning; if one exists, read it, treat its
values as the defaults for each step below, and confirm before overwriting.

The generated `.claude/agentflow.yaml` is **the single source of truth** for the project —
connections, secrets, surfaces, skills, labels and board all live there. Read the authoritative
schema at `templates/agentflow.yaml.template` before writing.

Work through the steps **in order**. If a precondition fails, tell the user exactly what to
fix and **stop** — do not press on with a half-configured repo. Never echo a secret value.

---

## 1. Preconditions

Run these and stop on the first failure with a precise fix:

```bash
git rev-parse --is-inside-work-tree     # must be a git repo
git remote get-url origin               # must resolve to a GitHub remote
gh auth status                          # must be authenticated
```

- Not a git repo → "Run `git init` and add a GitHub `origin` remote first."
- No `origin` → "Add a remote: `git remote add origin git@github.com:OWNER/REPO.git`."
- `gh` not authenticated → "Run `gh auth login` (same account as your token) and retry."

The `github` and `figma` MCP servers are **HTTP** servers (hosted GitHub remote; official Figma
server) — no Node/`npx` install is needed. The optional `figma` server signs in via OAuth
(`/mcp` → figma → Authenticate) after the plugin loads.

## 2. Resolve project

Derive `OWNER/REPO`, the default branch, and the owner from the remote and `gh`:

```bash
gh repo view --json nameWithOwner,defaultBranchRef,owner,description \
  -q '{repo: .nameWithOwner, branch: .defaultBranchRef.name, owner: .owner.login, type: .owner.type, desc: .description}'
```

- `OWNER/REPO` ← `nameWithOwner`; split on `/` for `OWNER` and `REPO`.
- `DEFAULT_BRANCH` ← `defaultBranchRef.name`.
- `PROJECT_OWNER` ← `owner.login`; `PROJECT_OWNER_TYPE` ← `Organization` → `org`, else `user`.
- `PROJECT_NAME` ← `REPO` unless the user gives a friendlier name.
- `PROJECT_SUMMARY` ← a short one-liner answering "what is this project?". Seed it from the
  repo `description` (or a glance at the README), then **ask the user to confirm or edit**.
  This goes to `project.summary` and is shown in `/status` and the READMEs.

## 3. Env check (presence only — NEVER a value)

The `env:` list in `templates/agentflow.yaml.template` declares every secret by NAME, with
`required` and `used_by`. Verify each is **present in the shell** — check presence, never the value:

```bash
[ -n "${GITHUB_TOKEN:-}" ] && echo "GITHUB_TOKEN: set" || echo "GITHUB_TOKEN: MISSING"
[ -n "${FIGMA_TOKEN:-}" ]  && echo "FIGMA_TOKEN: set"  || echo "FIGMA_TOKEN: absent"
```

- **`GITHUB_TOKEN` (required):** if unset → tell the user to
  `export GITHUB_TOKEN=...` (fine-grained PAT, scopes `repo` + `read:org`, plus `project` if
  they want a board) in the shell that launches Claude Code, then re-run. **Stop.**
- **`FIGMA_TOKEN` (optional):** if absent, note that the `figma` connection stays disabled
  (its MCP server is inert until set) and continue.

Never print, log, or interpolate a token value. Reference vars only as `${GITHUB_TOKEN}` /
`${FIGMA_TOKEN}`. See skill: **setup-agentflow** for how env names map to connections and MCP servers.

## 4. Connections wizard

Each connection is **fully specified in one place** — `auth` (token_env + scopes/cli|docs) and,
when the service has an MCP server, `mcp` (server key in `.mcp.json` + `requires_env`). A
connection is usable only when `enabled: true` AND every var in its auth/mcp requirements is
present. Confirm each:

- **github** — always `enabled: true`. `repo` ← `OWNER/REPO`.
  `auth: { token_env: GITHUB_TOKEN, scopes: ["repo","read:org"], cli: "gh auth login" }`,
  `mcp: { server: "github", requires_env: ["GITHUB_TOKEN"] }`.
- **github_project** — ask: *create a new board*, *link an existing board by id/number*, or
  *skip*. Sets `enabled` for Step 7. Needs the `project` scope on `GITHUB_TOKEN`.
  `auth.scopes: ["project","read:org"]`, `mcp: { server: "github", requires_env: ["GITHUB_TOKEN"] }`,
  plus `owner`/`owner_type` from Step 2.
- **figma** — only offer if `FIGMA_TOKEN` is set (Step 3). If enabling, seed
  `connections.figma.files` with any known file keys (e.g. `[{ name: "Design System", key: "AbC123xyz" }]`),
  else `[]`. `auth: { token_env: FIGMA_TOKEN, docs: "..." }`,
  `mcp: { server: "figma", requires_env: ["FIGMA_TOKEN"] }`. If `FIGMA_TOKEN` absent → `enabled: false`, skip the prompt.

**Validate** each enabled connection: confirm every var in its `auth.token_env` + `mcp.requires_env`
is present (presence only, from Step 3). If an enabled connection is missing a required var, warn
and either disable it or stop. Tell the user they can copy a connection block in the yaml to add
more services later (see skill: **setup-agentflow**).

## 5. Dynamic surface detection

AgentFlow is **tech-stack agnostic** and surfaces are an **OPEN MAP** — declare ONLY the parts
this repo actually has. Do **NOT** assume the backend/frontend/mobile trio: a repo may be
backend-only, frontend-only, mobile-only, or any mix. Scan for markers, then **PROPOSE** a
surface key + path + commands per detected part; the user confirms, edits, or **renames** each.

```bash
ls package.json go.mod pom.xml build.gradle build.gradle.kts requirements.txt \
   pyproject.toml Gemfile Cargo.toml pubspec.yaml composer.json 2>/dev/null
ls -d android ios web frontend backend server api admin mobile app 2>/dev/null
```

Map markers to suggestions (illustrative, not exhaustive — adapt to what you find; the surface
KEY is the user's to choose, e.g. `backend`, `web`, `api`, `admin`, `mobile`):

| Marker                                   | Suggested key | Suggested commands (confirm with user)              |
|------------------------------------------|---------------|------------------------------------------------------|
| `package.json` (web deps)                | web/frontend  | `npm ci` / `npm run lint` / `npm test` / `npm run build` |
| `go.mod`                                 | backend/api   | `go mod download` / `go vet ./...` / `go test ./...` / `go build ./...` |
| `pom.xml`, `build.gradle`                | backend       | `mvn -q install -DskipTests` / `mvn checkstyle:check` / `mvn test` / `mvn package` |
| `requirements.txt`, `pyproject.toml`     | backend/api   | `pip install -e .` / `ruff check` / `pytest` / `python -m build` |
| `Gemfile`                                | backend       | `bundle install` / `rubocop` / `rspec` |
| `Cargo.toml`                             | backend       | `cargo fetch` / `cargo clippy` / `cargo test` / `cargo build` |
| `pubspec.yaml`, `android/`, `ios/`       | mobile        | `flutter pub get` / `flutter analyze` / `flutter test` / `flutter build` |
| `composer.json`                          | backend       | `composer install` / `phpcs` / `phpunit` |

Rules:
- Write **ONLY the surfaces that exist** into the config. There is no fixed set — one surface or many.
- A **single-app repo** uses one surface mapped to `path: "."`.
- Leave any individual command `""` to skip it (e.g. no `integration`/`e2e` yet).
- `coverage_command` must print ONE number 0–100 to stdout, or `""` to skip; set a per-surface
  `coverage_threshold` (or `0` to defer to `agents.qc.coverage_threshold`).
- The QC **tiers** (`quick` ⊆ `full` ⊆ `regression`) are lists of command-*types*, not shell
  commands — the shell commands you collect here are what those tiers invoke per touched surface.
  Leave tier definitions at template defaults unless the user asks otherwise.

For each confirmed surface key `<s>`, set `surfaces.<s>.label: "component/<s>"`. The
`labels.component` map is then **generated to match** — one `component/<surface>` per declared
surface (Step 6 / Step 8).

```yaml
# example: a backend-only repo declares exactly one surface
surfaces:
  api:
    path: "."
    label: "component/api"
    commands: { install: "go mod download", lint: "go vet ./...", test: "go test ./...", integration: "", e2e: "", build: "go build ./..." }
    coverage_command: ""
    coverage_threshold: 0
    forbidden_paths: []
```

## 6. Create labels

Create every AgentFlow label idempotently. Always: **8** `flow:*`, **3** `type/*`,
`needs-clarification`, `needs-human` — PLUS **one `component/<surface>` per surface declared in
Step 5** (the component labels are dynamic). Meanings live in skill: **project-board-protocol**.
Use `--force` so re-runs update color/description instead of erroring:

```bash
# flow:* (state machine — exactly one per active issue) — blue family
gh label create "flow:inbox"                  --color 1D76DB --description "AgentFlow: triage"                 --force
gh label create "flow:refined"                --color 1D76DB --description "AgentFlow: DoR gate / clarify"     --force
gh label create "flow:ready-for-dev"          --color 1D76DB --description "AgentFlow: DEV queue"              --force
gh label create "flow:in-progress"            --color 1D76DB --description "AgentFlow: DEV coding (soft lock)" --force
gh label create "flow:in-qc"                  --color 1D76DB --description "AgentFlow: QC reviewing"           --force
gh label create "flow:changes-requested"      --color 1D76DB --description "AgentFlow: rework"                --force
gh label create "flow:ready-for-human-review" --color 1D76DB --description "AgentFlow: human review/merge"     --force
gh label create "flow:done"                   --color 1D76DB --description "AgentFlow: terminal"               --force

# type/* — green family
gh label create "type/feature"     --color 0E8A16 --description "AgentFlow: new capability"  --force
gh label create "type/improvement" --color 0E8A16 --description "AgentFlow: enhancement"     --force
gh label create "type/bug"         --color 0E8A16 --description "AgentFlow: defect"          --force

# component/<surface> — ONE per declared surface (loop over the Step 5 keys) — purple family
for s in <surface keys from Step 5>; do
  gh label create "component/$s" --color 5319E7 --description "AgentFlow: $s surface" --force
done

# aux signals — amber / red
gh label create "needs-clarification" --color FBCA04 --description "AgentFlow: PO input needed"    --force
gh label create "needs-human"         --color D93F0B --description "AgentFlow: escalated to human" --force
```

Do **not** create `component/*` labels for surfaces the repo doesn't have — they must mirror the
declared `surfaces:` keys exactly.

## 7. Optional board

Drive all GitHub Projects v2 details from skill: **project-board-protocol** (its
"Optional GitHub Projects v2 board (human mirror)" section).

- **create** or **link** (chosen in Step 4) → that skill creates/links the board, mirrors the
  `flow:*` labels to a Status field (HUMAN MIRROR only — labels stay authoritative), and returns
  the board **node id** (`PVT_…`). Store it at `board.id` and set
  `connections.github_project.enabled: true`.
- **skip** → `board.id: ""` and `connections.github_project.enabled: false`. **Labels-only mode
  works fully** — routing always reads the `flow:*` label, never a column.

Keep `board.id` and `connections.github_project.enabled` **in sync**.

## 8. Scaffold project skills (opt-in)

Offer to create starter **role-prefixed** skill stubs under `.claude/skills/`, named
`<role>-<area>` so the right agent picks them up: `dev-*` → DEV, `qc-*` → QC, `po-*` → PO.
Propose names matched to the detected surfaces, e.g. `dev-<surface>-development` per surface,
`qc-automation-test`, `po-discovery`. **Ask before creating.** For each accepted stub, write a
`SKILL.md` with YAML frontmatter (`name` = the directory name) + a short description + a TODO body:

```markdown
---
name: dev-api-development
description: API surface conventions for DEV — TODO: fill in.
---

# dev-api-development

TODO: document this project's API conventions, patterns, and gotchas DEV should follow.
```

Then **register** each in the yaml `skills:` map with `{ role, surfaces?, description? }` — this
registry is the single source of truth / overview. Agents also auto-discover any
`.claude/skills/<their-role>-*` even if unlisted; an agent loads the role-prefixed skills relevant
to the surface(s) the current issue touches (registry `surfaces` matched to the issue's
`component/*` labels; unlisted or no-`surfaces` = always relevant). See skill: **setup-agentflow**.

```yaml
skills:
  dev-api-development: { role: dev, surfaces: ["api"], description: "API surface conventions" }
  qc-automation-test:  { role: qc,  description: "E2E suite authoring" }
  po-discovery:        { role: po,  description: "Discovery & story-mapping checklist" }
```

List exactly what was created. If the user declines, leave `skills: {}`.

## 9. Generate config

Write `.claude/agentflow.yaml` by copying `templates/agentflow.yaml.template` and substituting
**every** placeholder, writing the **dynamic surfaces**, the **skills registry** (Step 8), and the
**full connection spec** (Step 4). Read the template to confirm the full set; as of v0.0.1:

```bash
mkdir -p .claude
```

| Placeholder                                 | Value                                                        |
|---------------------------------------------|--------------------------------------------------------------|
| `{{PROJECT_NAME}}`                          | project name (default = REPO)                                |
| `{{PROJECT_SUMMARY}}`                       | the confirmed one-liner from Step 2                          |
| `{{OWNER}}` / `{{REPO}}`                     | from Step 2 (`project.repo` and `connections.github.repo`)   |
| `{{DEFAULT_BRANCH}}`                        | default branch from Step 2                                   |
| `{{GITHUB_PROJECT_ENABLED}}`                | `true`/`false` — must match `board.id` being set vs `""`     |
| `{{PROJECT_OWNER}}` / `{{PROJECT_OWNER_TYPE}}` | owner login / `org`\|`user`                               |
| `{{FIGMA_ENABLED}}`                         | `true` only if `FIGMA_TOKEN` set AND user enabled it         |
| `{{PROJECT_ID}}`                            | board node id from Step 7, or `""`                           |
| `surfaces:` block                           | one block per **detected** surface (Step 5): `path`, `label`, six `commands`, `coverage_command`, `coverage_threshold`, `forbidden_paths`. Delete the template's example/placeholder surface entirely. |
| `labels.component`                          | one `<surface>: "component/<surface>"` per declared surface  |
| `skills:`                                   | the Step 8 registry, or `{}`                                 |
| `{{COVERAGE_THRESHOLD}}`                    | fallback `agents.qc.coverage_threshold` (e.g. `0` to disable)|

Leave the curated comments and tier defaults from the template intact. Do not invent keys the
template lacks. Confirm `{{GITHUB_PROJECT_ENABLED}}` and `{{PROJECT_ID}}` agree, and that every
`surfaces.<s>.label` has a matching `labels.component.<s>` entry and a created `component/<s>` label.

## 10. Generate README

Write `README.agentflow.md` into the repo root from `templates/README.project.md` (substitute any
project-specific values, otherwise copy verbatim). This is the per-repo quick reference pointing
users at `/start`, `/task`, `/status`, `/handoff`, and re-running `/agentflow-init`.

## 11. Verify (light smoke check)

```bash
# yaml parses
python3 -c "import yaml; yaml.safe_load(open('.claude/agentflow.yaml'))" && echo "yaml: ok"
# labels exist: 8 flow:*, 3 type/*, one component/* per surface, 2 needs-*
gh label list --json name -q '.[].name' | grep -E '^(flow:|type/|component/|needs-)' | sort
```

- If a board was created/linked, confirm it resolves (defer to skill: **project-board-protocol**
  for the lookup) and that `board.id` matches `connections.github_project.enabled`.
- **Optional** end-to-end label check — **ask the user first**: create a throwaway issue, add
  `flow:inbox`, swap it to `flow:refined`, then close it. Clean up after yourself; never leave
  test artifacts behind without telling the user.

```bash
# only with user consent
gh issue create --title "AgentFlow setup check" --body "temporary — safe to close" --label "flow:inbox"
# ...swap label flow:inbox → flow:refined to prove transitions, then:
gh issue close <n> --comment "AgentFlow verification complete."
```

## 12. Summary

Print a tight report:

```
AgentFlow initialized on <OWNER/REPO> (v0.0.1)

Project     : <name> — <summary>
Connections : github ✓   github_project <on PVT_… | off>   figma <on | off (FIGMA_TOKEN absent)>
Env         : GITHUB_TOKEN set ✓   FIGMA_TOKEN <set | absent>
Surfaces    : <key>=<path> [, <key>=<path> …]   (only the surfaces that exist)
              command coverage per surface: lint/test/integration/e2e/build
Labels      : <13 + N> created/updated (flow:* ·8, type/* ·3, component/* ·N, needs-* ·2)
Board       : <PVT_… | labels-only>
Skills      : <scaffolded role-prefixed stubs, or none>
Files       : .claude/agentflow.yaml, README.agentflow.md, [.claude/skills/<role>-* …]

Next: run /start to enter team mode, then /task <description> to file your first item.
```

---

**Re-runs:** safe at any time. Re-detect surfaces, add a board you skipped, register new skills,
or refresh connections/env — each step reuses the existing `.claude/agentflow.yaml` values as
defaults and asks before overwriting. Labels and any board are reconciled idempotently.
