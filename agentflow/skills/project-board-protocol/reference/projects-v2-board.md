# Optional GitHub Projects v2 board (human mirror)

> Reference for skill `project-board-protocol`. Read `../SKILL.md` first — this file is the
> heavy, rarely-needed board mechanics, split out so the common (labels-only) path stays lean.

**The one rule that overrides everything below:** the `flow:*` **LABEL is authoritative** for
routing. The Projects v2 board is a **human-only visual mirror**. Agents decide what to do next by
reading the issue's `flow:*` label — they **never** read a board column to make a decision. Syncing
the board is **optional, best-effort, and may lag**. If a mirror write fails, log it and continue;
the pipeline is unaffected.

When `board.id` is `""` (labels-only mode), ignore this file entirely: the full PO/DEV/QC pipeline
works with labels alone, and `GITHUB_TOKEN` needs **no** `project` scope.

## Contents

- [How Projects v2 is driven (GraphQL vs the official MCP `projects` toolset)](#how-projects-v2-is-driven)
- [Resolve the board](#resolve-the-board)
- [Create a board (init: `github_project=create`)](#create-a-board)
- [Link an existing board](#link-an-existing-board)
- [Mirror a flow:* label → column](#mirror-a-flow-label--column)
- [List actionable board items (orchestrator queue)](#list-actionable-board-items)
- [Board-driven mode amendment](#board-driven-mode-amendment)
- [Canonical status_map (board-driven mode)](#canonical-status_map-board-driven-mode)
- [Scopes](#scopes)
- [Helper scripts](#helper-scripts)

## How Projects v2 is driven

Projects v2 has **no `gh`-CLI REST path** — `gh issue edit` swaps a label but **cannot** move a
card. Two mechanisms exist; pick **one** per install and be consistent:

1. **`gh api graphql`** (default — what the snippets below use). Works for everything: resolving the
   board node id, **creating** the project and its single-select Status field, adding items, and
   setting Status. Project + Status-**field** creation is **GraphQL-only** — the MCP server cannot
   create the 8-option field.
2. **The official `github` MCP server's `projects` toolset** (optional, item-level only). When the
   server is run with the `projects` toolset enabled, it exposes `projects_list` / `projects_get`
   (reads) and `projects_write` (methods `add_project_item` / `update_project_item` /
   `delete_project_item`). It keys off **owner + project number**, not the `PVT_` node id, and it
   **cannot** create the Status field. If a project adopts it for the per-item mirror, persist
   **both** the project number and the `PVT_` node id under `board:`.

**Recommended default: keep one mechanism — `gh api graphql` — for both bootstrap and mirror.** It
avoids node-id-vs-number plumbing and needs no opt-in toolset. The MCP `projects_write` path is a
documented alternative, not a requirement. (Bootstrapping the Status field always stays on GraphQL
regardless.)

Connection config: `connections.github_project` toggles the link (`enabled`, `owner`, `owner_type`,
`auth.token_env`, `auth.scopes`, `mcp.server`) and `board.id` / `board.columns` carry the node id
and the eight column names. A connection is usable only when `enabled:true` AND every required env
var is present (see skill: `setup-agentflow`).

## Resolve the board

A board has a **node id** of the form `PVT_xxx`. Resolve it from
`connections.github_project.owner` + `owner_type` and the board **number** (or run
`scripts/resolve-board.sh <owner> <owner_type> <number>`):

```bash
# owner_type: org
gh api graphql -f query='
  query($login:String!, $number:Int!){
    organization(login:$login){ projectV2(number:$number){ id title } }
  }' -F login="<owner>" -F number=<N>

# owner_type: user
gh api graphql -f query='
  query($login:String!, $number:Int!){
    user(login:$login){ projectV2(number:$number){ id title } }
  }' -F login="<owner>" -F number=<N>
```

The returned `id` (`PVT_…`) is what belongs in `board.id`. A human-facing project **number** (the
`/projects/<N>` URL) maps to exactly one node id via the query above; store the node id, not the
number, so later calls skip the lookup.

## Create a board

Used by /agentflow-init when the user opts to create a board. Two steps: create the project, then
give its **Status** field options that match `board.columns`.

1. Create the Projects v2 project under the resolved owner node id:

```bash
# get the owner node id first
gh api graphql -f query='query($l:String!){ organization(login:$l){ id } }' -F l="<owner>"

gh api graphql -f query='
  mutation($owner:ID!, $title:String!){
    createProjectV2(input:{ ownerId:$owner, title:$title }){
      projectV2{ id number }
    }
  }' -F owner="<ownerNodeId>" -F title="<project.name>"
```

Persist the returned `projectV2.id` to `board.id` and set `connections.github_project.enabled: true`.

2. Locate or create the single-select **Status** field. A new project ships with a default `Status`
   field carrying `Todo/In Progress/Done`. AgentFlow needs the **eight** options in `board.columns`
   (Inbox, Refined, Ready for Dev, In Progress, In QC, Changes Requested, Ready for Human Review,
   Done). Recreate the field with exactly those options, in order:

```bash
gh api graphql -f query='
  mutation($project:ID!){
    createProjectV2Field(input:{
      projectId:$project,
      dataType: SINGLE_SELECT,
      name: "Status",
      singleSelectOptions: [
        { name: "Inbox",                  color: GRAY,   description: "" },
        { name: "Refined",                color: PURPLE, description: "" },
        { name: "Ready for Dev",          color: BLUE,   description: "" },
        { name: "In Progress",            color: YELLOW, description: "" },
        { name: "In QC",                  color: ORANGE, description: "" },
        { name: "Changes Requested",      color: RED,    description: "" },
        { name: "Ready for Human Review", color: PINK,   description: "" },
        { name: "Done",                   color: GREEN,  description: "" }
      ]
    }){ projectV2Field { ... on ProjectV2SingleSelectField { id options { id name } } } }
  }' -F project="<board.id>"
```

The option `name` strings MUST equal the values under `board.columns` one-to-one — that string
match is how a `flow:*` label is mapped to an option later. (`singleSelectOptions` requires
`name`, `color`, and `description` on every option.)

## Link an existing board

Used by /agentflow-init when the user provides a board number/id. Validate, do not mutate the
user's data:

1. Resolve the id (Resolve the board, above). If it does not resolve under `owner`/`owner_type`,
   stop and tell the user.
2. Read its `Status` field and confirm an option exists for each of the eight `board.columns` values:

```bash
gh api graphql -f query='
  query($id:ID!){ node(id:$id){ ... on ProjectV2 {
    field(name:"Status"){ ... on ProjectV2SingleSelectField { id options { id name } } }
  }}}' -F id="<board.id>"
```

3. If any column is missing, do NOT silently rewrite the board — list the missing option names and
   guide the user to add them (or to let init recreate the field).

## Mirror a flow:* label → column

Given an issue and its current `flow:*` label, mirror it to the board (or run
`scripts/mirror-label-to-board.sh`). Map `labels.flow.<key>` → `board.columns.<key>` **one-to-one**
(same `<key>`: e.g. `flow:in-qc` → key `in_qc` → `board.columns.in_qc` = "In QC"). Three ids are
needed: the **item id** (the issue's card), the Status **field id**, and the target **option id**.

```bash
# 1. add the issue to the project (idempotent; returns the existing item if present)
gh api graphql -f query='
  mutation($project:ID!, $content:ID!){
    addProjectV2ItemById(input:{ projectId:$project, contentId:$content }){
      item { id }
    }
  }' -F project="<board.id>" -F content="<issueNodeId>"

# 2. set its Status to the option whose name == board.columns.<key>
gh api graphql -f query='
  mutation($project:ID!, $item:ID!, $field:ID!, $option:String!){
    updateProjectV2ItemFieldValue(input:{
      projectId:$project, itemId:$item, fieldId:$field,
      value:{ singleSelectOptionId:$option }
    }){ projectV2Item { id } }
  }' -F project="<board.id>" -F item="<itemId>" \
     -F field="<statusFieldId>" -F option="<optionId>"
```

Resolve `<issueNodeId>` with `gh issue view <n> --json id` (or the GitHub MCP). Get
`<statusFieldId>` and the `<optionId>` for the target column from the `Status` field query above,
matching on the option `name`. This mirror runs **after** the label swap, never instead of it; on
any error, log and move on.

## List actionable board items

**Board-driven mode only.** When a board spans many issues, the orchestrator reads the **whole**
board in one shot to build its work queue. This is the one query that reads board state as a
*queue*. Paginate over every item and pull, per item: the issue **number**, the **item id** (reuse
it directly in the mirror's `updateProjectV2ItemFieldValue`, skipping the `addProjectV2ItemById`
round-trip), the issue's live **labels** (the authoritative `flow:*`), the issue **state** (skip
`CLOSED`), and the current **Status** option name.

```bash
gh api graphql -f query='
  query($project:ID!, $cursor:String){
    node(id:$project){ ... on ProjectV2 {
      items(first:50, after:$cursor){
        pageInfo{ hasNextPage endCursor }
        nodes{
          id
          fieldValueByName(name:"Status"){
            ... on ProjectV2ItemFieldSingleSelectValue { name optionId }
          }
          content{
            ... on Issue {
              number
              state
              url
              repository{ nameWithOwner }
              labels(first:20){ nodes{ name } }
            }
            ... on DraftIssue { title }   # draft cards have no issue → not routable
          }
        }
      }
    }}}' -F project="<board.id>" -F cursor="<endCursor|null>"
# loop while .data.node.items.pageInfo.hasNextPage, passing endCursor as the next cursor
```

The list returns **all** board items; the orchestrator applies the *actionable* filter client-side
(Status whose `status_map` owner is an agent, issue `state == OPEN`). A **draft** card (no
`content.number`) is outside the label state machine — surface it to the human to convert to an
issue via `/task`.

## Board-driven mode amendment

The default protocol (in `../SKILL.md`) makes the `flow:*` **label authoritative** and treats the
board as a **human-only mirror** that agents never read. **Board-driven mode** relaxes this in
exactly one place: the **orchestrator** (`/start`) reads board Status as its **work queue** via the
list query above. This is the *only* sanctioned reader of columns, and even it does not *trust* the
column for state — for each item it re-reads the issue's live `flow:*` label and routes off the
**label** (label wins on any drift), then re-mirrors Status to match. PO/DEV/QC sub-agents still
**never** read or write the board; all board writes stay at the orchestrator layer (`/start`,
`/task`). The board is a queue + mirror; the label is the truth.

## Canonical status_map (board-driven mode)

A repo running board-driven `/start` (`board.id` non-empty + `connections.github_project.enabled:
true`) uses the canonical table below. It is the single routing table `/start` reads — read it here,
do not hardcode a different one. The `column` strings match the canonical `board.columns`; if a repo
renamed a column, map by the **`<key>`** (e.g. `in_qc`), not the display string.

```yaml
status_map:
  inbox:                  { column: "Inbox",                  flow_label: "flow:inbox",                  owner: "po",    action: "triage & refine the issue into AC" }
  refined:                { column: "Refined",                flow_label: "flow:refined",                owner: "po",    action: "DoR gate / clarification buffer" }
  ready_for_dev:          { column: "Ready for Dev",          flow_label: "flow:ready-for-dev",          owner: "dev",   action: "pick oldest, implement, open PR" }
  in_progress:            { column: "In Progress",            flow_label: "flow:in-progress",            owner: "dev",   action: "active coding (soft lock) — NOT re-spawnable; break out if paused/blocked" }
  in_qc:                  { column: "In QC",                  flow_label: "flow:in-qc",                  owner: "qc",    action: "run the issue's QC tier per touched surface" }
  changes_requested:      { column: "Changes Requested",      flow_label: "flow:changes-requested",      owner: "dev",   action: "rework against the latest QC rejection" }
  ready_for_human_review: { column: "Ready for Human Review", flow_label: "flow:ready-for-human-review", owner: "human", action: "human reviews / merges, or 2-strike decision" }
  done:                   { column: "Done",                   flow_label: "flow:done",                   owner: "human", action: "terminal" }
```

> **`in_progress` is a special case.** Its `owner` is `dev` (the work belongs to DEV), but the card
> is **in-flight under the soft lock** — the orchestrator must **never re-spawn DEV** on it. A card
> sitting in `flow:in-progress` between polls means DEV paused or is blocked → **break out to the
> human**, do not route it forward. See `commands/start.md` (polling loop, "next step" decision).

## Scopes

- Org board: `GITHUB_TOKEN` needs `project` **and** `read:org`.
- User board: `GITHUB_TOKEN` needs `project`.
- **Labels-only** mode (`board.id` = `""`): none of the above; the pipeline still works end to end.
  Prefer this when no human needs the visual board.
- **Board-driven mode** (a board on the agent decision path): `project` scope is **mandatory** —
  `/start` reads the board to build its queue and stops at boot if the scope is missing.
  (Labels-only installs keep `/task`/agents without it; they just lose the board-driven `/start`.)
- If the optional MCP `projects` toolset is used for the mirror, the `github` MCP server must be run
  with that toolset enabled (it is **not** on by default); otherwise the `projects_*` tools silently
  do not exist and the mirror falls back to GraphQL.

## Helper scripts

Two deterministic operations are bundled as scripts so the agent runs them instead of re-typing
fragile GraphQL (low-freedom rule, see Anthropic skill best-practices):

- `scripts/resolve-board.sh <owner> <owner_type> <number>` → prints the `PVT_…` node id.
- `scripts/mirror-label-to-board.sh <board_id> <issue_node_id> <status_field_id> <option_id>` →
  adds the issue to the board and sets its Status option (the two mutations above).

Both are thin wrappers over `gh api graphql`; read them before first use to confirm they match your
`board.columns`.
