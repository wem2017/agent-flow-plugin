---
description: Bootstrap an AgentFlow PROGRAM — one shared GitHub Projects v2 board that aggregates issues from MANY member repos. Creates/links the board, writes the program manifest, and per-member runs /agentflow-init + points each repo at the shared board.
argument-hint: "[workspace-root] [member repo paths…] (interactive if omitted)"
---

You are bootstrapping an **AgentFlow program**: a single shared GitHub Projects v2
board that gathers issues from **several repos** so one orchestrator (`/start`) can
drive them all. This is **idempotent and re-runnable** — re-run it to add a member,
relink the board, or refresh the manifest. Never destroy a hand-edited
`agentflow.program.yaml` without warning; if one exists, read it, treat its values as
the defaults for each step, and confirm before overwriting.

The generated `<workspace-root>/.claude/agentflow.program.yaml` is the **single source
of truth for the program** (the shared board + `status_map` + member list). Each member
repo keeps its **own** `.claude/agentflow.yaml`. Read the authoritative schemas first:
`templates/agentflow.program.yaml.template` and `templates/agentflow.yaml.template`.

Work through the steps **in order**. Stop on the first failed precondition with a precise
fix. **Never echo a secret value.** A program REQUIRES a board, so unlike `/agentflow-init`
the `project` token scope is a **hard** requirement here.

---

## 1. Preconditions

```bash
gh auth status                                  # must be authenticated
[ -n "${GITHUB_TOKEN:-}" ] && echo "GITHUB_TOKEN: set" || echo "GITHUB_TOKEN: MISSING"
gh auth status 2>&1 | grep -qi "project" && echo "project scope: ok" \
  || echo "project scope: MISSING"
```

- `gh` not authenticated → "Run `gh auth login` (same account as your token) and retry." **Stop.**
- `GITHUB_TOKEN` missing → export it and re-run. **Stop.**
- **`project` scope missing → a shared board cannot be created/read without it.** Tell the
  user to run `gh auth refresh -s project` (and `read:org` too if the board owner is an org),
  then re-run. **Stop.** See skill: `project-board-protocol` → Scopes.
- A fine-grained PAT must have account-level **Projects** access — a single-repo-scoped token
  cannot own a user/org project.

## 2. Discover member repos

Resolve the set of repos this program spans, in priority order:

1. **Explicit** — repo paths passed in `$ARGUMENTS`. Preferred (deterministic).
2. **Scan siblings** — from the chosen workspace root, list candidate git repos and show them
   for the user to **check off**. Do NOT auto-include — a parent dir often holds unrelated repos.
   ```bash
   for d in */; do [ -d "$d/.git" ] && printf "%s\t%s\n" "$d" "$(git -C "$d" remote get-url origin 2>/dev/null)"; done
   ```
3. **Ask** — if neither, prompt for repo paths one at a time.

For each member, derive identity exactly as `/agentflow-init` step 2:

```bash
gh repo view --json nameWithOwner,defaultBranchRef,owner \
  -q '{repo:.nameWithOwner, branch:.defaultBranchRef.name, owner:.owner.login, type:.owner.type}'
```

**Validate every member shares the SAME owner + owner_type** as the board owner (a user board
holds items from repos that user owns; an org board, the org's). Flag any mismatch and stop —
a board cannot aggregate repos across different owners.

## 3. Workspace root + manifest location

- Default workspace root = the **common parent** of the members. Confirm with the user.
- Canonical manifest path: `<workspace-root>/.claude/agentflow.program.yaml`. If the user
  prefers not to drop a `.claude/` into a non-repo parent, fall back to keeping it inside the
  first member repo and have the others point at it; record the choice.
- Compute each member's `path` and `config` **relative to the manifest's dir**. Keep `repo`
  (`OWNER/REPO`) as the stable identity; `path` is convenience that `/start` re-validates.

## 4. Create or link the shared board

Drive all GraphQL from skill: `project-board-protocol` (its board section). The board owner
here may be a **user** or an **org** — pick the matching query variant.

1. **Look for an existing board with this title** (avoid duplicates on re-run):
   ```bash
   # user owner
   gh api graphql -f query='query($l:String!){ user(login:$l){ projectsV2(first:50){ nodes{ id number title } } } }' -F l="<owner>"
   # org owner: organization(login:$l){ projectsV2(... ) }
   ```
   If a board titled `<PROGRAM_NAME>` exists (or the user supplied a number/id) → **link** it:
   resolve its node id (project-board-protocol "Resolve the board"), read its `Status` field,
   and confirm an option exists for each of the 8 `board.columns`. If any are missing, **do not
   silently rewrite** — list them and let the user add them or have init recreate the field.
2. **Else create** it: get the owner node id, `createProjectV2(title:"<PROGRAM_NAME>")`, then
   create the `Status` field with **exactly** the 8 options in `board.columns`, in order
   (project-board-protocol "Create a board"). Persist the returned `id` (`PVT_…`) and `number`.

Linking validates without mutating; creating is skipped when the titled board already resolves.

## 5. Write the program manifest

Copy `templates/agentflow.program.yaml.template` to the manifest path, substituting:

| Placeholder | Value |
|-------------|-------|
| `{{PROGRAM_NAME}}` | the program/board name (e.g. `cinestar-agent-flow`) |
| `{{PROGRAM_SUMMARY}}` | a confirmed one-liner |
| `{{BOARD_OWNER}}` / `{{BOARD_OWNER_TYPE}}` | from step 2 |
| `{{BOARD_ID}}` / `{{BOARD_NUMBER}}` | from step 4 |
| `status_map` | leave the template's static 8-entry map intact |
| `members:` | one block per confirmed member (`repo`, `name`, `path`, `config`, `default_branch`) |

If the manifest exists, treat its values as defaults and confirm before overwriting.

## 6. Per-member: init + point at the shared board

For **each** member, `cd` into its `path` and:

1. **Ensure it is per-repo init'd.** If it has no `.claude/agentflow.yaml` → run the full
   `/agentflow-init` flow (all 12 steps) there. If it already has one → a re-run is safe;
   only reconcile the board fields below.
2. **Point it at the shared board** (the cross-repo wiring — same id in every member):
   ```yaml
   connections:
     github_project:
       enabled: true
       owner: "<board owner>"
       owner_type: "<org|user>"
   board:
     id: "<shared PVT_… from step 4>"
   ```
   Keep `board.id` ↔ `connections.github_project.enabled` in sync.
3. **Add the program back-pointer** to that repo's `.claude/agentflow.yaml`:
   ```yaml
   program:
     name: "<PROGRAM_NAME>"
     manifest: "<relative path back to the manifest>"
   ```
4. **Validate consistency:** every member must carry **byte-identical** `board.columns` and the
   8 `flow:*` label strings (that one-to-one match is how a label maps to a Status option). Refuse
   on drift — fix the diverging member first.
5. Each repo's own `/agentflow-init` already created its `flow:*` / `type/*` / `component/*`
   labels; nothing extra to create here.

## 7. Verify (light smoke check)

```bash
python3 -c "import yaml; yaml.safe_load(open('<manifest>'))" && echo "program yaml: ok"
```

- Confirm the board resolves under its owner (project-board-protocol "Resolve the board") and its
  `Status` has all 8 options.
- Confirm **every** member's `board.id` equals the program `board.id`, and each `members[].config`
  path exists and parses.

## 8. Summary

```
AgentFlow PROGRAM initialized: <PROGRAM_NAME>

Board    : <PVT_…>  (#<number>)  owner <owner>/<type>
Manifest : <workspace-root>/.claude/agentflow.program.yaml
Members  :
  <owner/repo>   path <…>   branch <…>   board linked ✓
  <owner/repo>   path <…>   branch <…>   board linked ✓
Status map: Inbox→po · Refined→po · Ready for Dev→dev · In QC→qc · Changes Requested→dev
            (In Progress / Ready for Human Review / Done → human)

Next: run /start from the workspace root to poll the board, or /task <desc> inside a
member repo to file work. New cards on the board are picked up on the next /start poll.
```

---

**Re-runs:** safe any time. Re-link the board (no duplicate), add a member, refresh the manifest,
or re-point a member — each step reuses existing values as defaults and asks before overwriting.
