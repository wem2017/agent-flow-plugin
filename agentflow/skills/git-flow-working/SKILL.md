---
name: git-flow-working
description: Tech-agnostic git conventions every agent (mainly DEV) follows — branching off default_branch, Conventional Commits, PR shape, rebase/sync, and the hard safety rules (no force-push, no merge, no touching forbidden_paths). Read this before creating a branch, committing, or opening/updating a PR.
---

# AgentFlow Git Flow

How DEV turns an issue into a reviewable PR without ever breaking the repo. This is language- and framework-agnostic: it only assumes git and the GitHub primitives. All names below come from `.claude/agentflow.yaml` — read the yaml, never hardcode. Pair this with skill: project-board-protocol for the state machine and skill: setup-agentflow for gating GitHub access.

## Branching

Fresh work always branches from `project.default_branch`, never from another feature branch. The branch name is:

```
<agents.dev.branch_prefix><issue#>-<kebab-slug>
```

With the default `agents.dev.branch_prefix: "agent/dev/"`, issue #42 "CSV export for reports" becomes:

```bash
git fetch origin
git switch -c agent/dev/42-csv-export origin/<default_branch>
```

Rules:

- One issue → one branch → one PR. The `<issue#>` in the name ties the branch to its issue and to the soft lock (`flow:in-progress`) in skill: project-board-protocol.
- **Rework re-uses the SAME branch and PR.** When an issue returns as `flow:changes-requested`, check it out and push more commits — never open a duplicate branch or PR for the same issue.
- Human (non-agent) work uses conventional prefixes instead: `feature/`, `fix/`, `chore/`. Agents only ever create branches under `agents.dev.branch_prefix`.

```bash
# resume an existing rework branch
git fetch origin
git switch agent/dev/42-csv-export   # already exists from the first attempt
```

## Commits

Use [Conventional Commits](https://www.conventionalcommits.org/): `<type>(<scope>): <subject>`.

| type        | use for                                  |
|-------------|------------------------------------------|
| `feat:`     | a new capability                         |
| `fix:`      | a bug fix                                 |
| `refactor:` | behavior-preserving restructuring        |
| `test:`     | adding or fixing tests only              |
| `docs:`     | docs / comments only                     |
| `chore:`    | build, deps, tooling                     |

- Subject in the **imperative** mood, no trailing period, ≤ ~72 chars: `feat(reports): add CSV export endpoint`.
- `scope` is optional; prefer a surface or module name matching a declared surface key or module (`reports`, `auth`, or any `surfaces.<name>` key).
- Reference the issue in the body, not the subject: `Refs #42` (let the PR carry `Closes #42`).
- Keep commits **small and reviewable** — one logical change each. Don't bundle a refactor with a feature.

```bash
git add src/reports/export.*
git commit -m "feat(reports): add CSV export endpoint" -m "Refs #42"
```

## Pull requests

Open the PR as soon as there is something to review. Shape:

- **Title:** `<type>(#<issue>): <summary>` — e.g. `feat(#42): CSV export for reports`.
- **Body must include:**
  - `Closes #<issue>` (auto-links and auto-closes on merge).
  - The issue's Acceptance Criteria mirrored as a checklist (tick items as they land — this feeds the DoD in skill: project-board-protocol).
  - Which surface(s) it touches (the `component/*` labels) and how to run each — one project may have a single surface or many.
- **Request no reviewers.** QC reviews on the PR and a human merges; do not add GitHub reviewers or auto-merge.

```bash
gh pr create \
  --base "<default_branch>" \
  --head "agent/dev/42-csv-export" \
  --title "feat(#42): CSV export for reports" \
  --body "Closes #42

## Acceptance Criteria
- [ ] Endpoint returns RFC 4180 CSV
- [ ] Empty result set returns header row only

## Surfaces
- component/<surface> — install/lint/test via surfaces.<surface>.commands (one bullet per touched surface)"
```

After opening the PR, post `[DEV]` on the issue with the PR link and swap the `flow:*` label per skill: project-board-protocol.

### Rework on an existing PR

Don't open a new PR. Push to the same branch, then comment:

```
[DEV] Reworked rejection #N — addressed: <one line per QC item, citing the fix>
```

Tick any AC checkboxes the rework now satisfies. DEV MUST read the latest `QC rejections` entry in the state comment before changing code (see skill: project-board-protocol).

## Sync & conflicts

Keep the branch current with `default_branch` so the PR merges cleanly:

```bash
git fetch origin
git rebase origin/<default_branch>     # preferred — clean linear history
# ...resolve any conflicts locally...
git add <resolved-files>
git rebase --continue
```

- **Rebase is preferred** for a linear history. If the team's convention is merge commits, `git merge origin/<default_branch>` is acceptable — pick one and be consistent.
- Resolve conflicts **locally**; never push a branch with conflict markers.
- **After any sync, re-run the touched surface's tier commands** (the types in `agents.qc.tiers.<tier>`, mapped to `surfaces.<name>.commands`) — a clean rebase can still break behavior.

## Safety rules (hard — never violate)

| Rule | Why |
|------|-----|
| Never `git push --force` a shared / PR branch | Rewrites history QC may have reviewed; breaks the PR. Use `--force-with-lease` only on an agent branch nobody else has touched, and only right after a local rebase. |
| Never push to `project.default_branch` | It is protected and human-owned. All changes flow through a PR. |
| Never merge a PR | Only the human merges, after the issue reaches `flow:ready-for-human-review`. Agents stop there. |
| Never edit `agents.dev.forbidden_paths` | Global no-touch globs (CI, infra, secrets, keystores). Enforced for every surface. |
| Never edit a surface's `forbidden_paths` | Per-surface no-touch globs (e.g. signing configs). |
| Never commit a secret | Reference creds by `${ENV_NAME}` (declared under `env:`); never hardcode a token. See skill: setup-agentflow. |

Before committing, sanity-check the diff against the forbidden globs:

```bash
git diff --cached --name-only   # confirm nothing matches agents.dev.forbidden_paths
                                # or the touched surface's forbidden_paths
```

If a needed change falls inside a forbidden path, **stop and escalate** to the human via the clarification/escalation path in skill: project-board-protocol — do not work around it. The effective no-touch set is the **union** of `agents.dev.forbidden_paths` and every touched surface's `forbidden_paths`.

## Surfaces & commands

`surfaces:` is an open map — a project declares only the surfaces it has (keys it chose: maybe just `.`, maybe `backend`+`web`+`mobile`, any mix). Never assume a fixed trio. An issue's `component/*` labels name exactly which surface(s) it touches.

An issue may carry one `component/*` label or several. Keep it in **one branch and one PR** regardless — do not split by surface. But run each touched surface's commands independently:

- DEV: while coding, run the relevant `surfaces.<name>.commands` for every surface you changed (skip any command set to `""`).
- QC: for the issue's tier, run each type in `agents.qc.tiers.<tier>` against **every** touched surface, in order; all must exit 0 (see skill: project-board-protocol).

```bash
# For each surface S named by the issue's component/* labels (could be one, could be many):
for S in <the touched surface keys>; do
  ( cd <surfaces.$S.path> && <surfaces.$S.commands.lint> && <surfaces.$S.commands.test> )   # skip "" commands
done
```

Mention every touched surface in the PR body so QC knows the full command set to run.
