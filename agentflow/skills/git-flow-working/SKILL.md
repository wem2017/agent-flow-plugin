---
name: git-flow-working
description: Applies tech-agnostic git conventions for AgentFlow agents (mainly DEV) — branching off the default branch, Conventional Commits (full type set + breaking-change notation), PR shape and issue-linking keywords, rebase-first sync, and the hard safety rules (no force-push to shared branches, no merge, no touching forbidden_paths). Use when an agent creates a branch, commits, or opens/updates a PR.
---

# AgentFlow Git Flow

How DEV turns an issue into a reviewable PR without ever breaking the repo. This is language- and framework-agnostic: it only assumes git and the GitHub primitives. All names below come from `.claude/agentflow.yaml` — read the yaml, never hardcode. Pair this with skill: project-board-protocol for the state machine and skill: setup-agentflow for gating GitHub access.

## Branching

Fresh work always branches from `project.default_branch`, never from another feature branch. The branch name is:

```
<agents.dev.branch_prefix><kind>/<issue#>-<kebab-slug>
```

where **kind** comes from the issue's `type/*` label: `type/feature → feat`, `type/bug → fix`, `type/improvement → chore`.

With the default `agents.dev.branch_prefix: "agent/dev/"`, issue #42 `type/feature` "CSV export for reports" becomes `agent/dev/feat/42-csv-export`; issue #43 `type/bug` "logo redirect" becomes `agent/dev/fix/43-logo-redirect`:

```bash
git fetch origin
git switch -c agent/dev/feat/42-csv-export origin/<default_branch>
```

Rules:

- One issue → one branch → one PR. The `<issue#>` in the name ties the branch to its issue and to the in-flight guard (`flow:in-progress`) in skill: project-board-protocol — the claim itself is the issue's assignee, set when `/start` picks the ticket out of `flow:inbox`.
- **Rework re-uses the SAME branch and PR.** When an issue returns as `flow:changes-requested`, check it out and push more commits — never open a duplicate branch or PR for the same issue.
- Human (non-agent) work uses conventional prefixes instead: `feature/`, `fix/`, `chore/`. Agents only ever create branches under `agents.dev.branch_prefix`.

```bash
# resume an existing rework branch
git fetch origin
git switch agent/dev/feat/42-csv-export   # already exists from the first attempt
```

## Commits

Use [Conventional Commits 1.0.0](https://www.conventionalcommits.org/): `<type>(<scope>): <subject>`. The spec recognizes `feat` and `fix`; the rest below are the conventional (Angular) set tooling expects — use them so changelog/semver automation classifies each commit correctly.

| type        | use for                                                        |
|-------------|----------------------------------------------------------------|
| `feat:`     | a new capability (→ MINOR bump)                                |
| `fix:`      | a bug fix (→ PATCH bump)                                        |
| `refactor:` | behavior-preserving restructuring                              |
| `perf:`     | a behavior-preserving performance improvement                  |
| `test:`     | adding or fixing tests only                                    |
| `docs:`     | docs / comments only                                           |
| `build:`    | build system or dependency changes (e.g. lockfiles, packaging) |
| `ci:`       | CI configuration and scripts                                   |
| `style:`    | formatting only — whitespace, semicolons (no logic change)     |
| `chore:`    | other maintenance not covered above                            |

- Subject in the **imperative** mood, no trailing period, ≤ ~72 chars: `feat(reports): add CSV export endpoint`.
- `scope` is optional; prefer a surface or module name matching a declared surface key or module (`reports`, `auth`, or any `surfaces.<name>` key).
- **Breaking change:** append `!` after the type/scope **and/or** add a `BREAKING CHANGE:` footer (uppercase, or `BREAKING-CHANGE:`) describing the break — e.g. `feat(api)!: drop v1 auth header`. This signals an API break to QC and humans (→ MAJOR bump). Don't break API silently.
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
  - `Closes #<issue>` (auto-links and auto-closes on merge). Any closing keyword works, case-insensitive: `close/closes/closed`, `fix/fixes/fixed`, `resolve/resolves/resolved`. **Auto-close fires only when the PR's base is the default branch** — AgentFlow always targets `project.default_branch`, so this holds; keep it that way. For an issue in **another** repo use the qualified form `Closes owner/repo#<n>`.
  - The issue's Acceptance Criteria mirrored as a checklist (tick items as they land — this feeds the DoD in skill: project-board-protocol).
  - Which surface(s) it touches (the `component/*` labels) and how to run each — one project may have a single surface or many.
- **Request no reviewers.** QC reviews on the PR and a human merges; do not add GitHub reviewers or auto-merge.

```bash
gh pr create \
  --base "<default_branch>" \
  --head "agent/dev/feat/42-csv-export" \
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

### QC test commits

QC also commits to **DEV's existing PR branch** (the one it checked out with `gh pr checkout <n>`). Using its automation skill, QC may **add test identifiers** the suite needs (e.g. `testID` / `data-testid` / keys / a11y labels) to the implementation and **author test files** mapped to the AC, then `git add` + `git commit -m "test(...): …"` + `git push` to that same branch. QC:

- pushes to the **existing** PR branch only — never opens a new branch or PR, and never force-pushes;
- changes **test code and test identifiers only** — never implementation logic. A real logic bug is a `[QC] ❌` back to DEV, not a fix QC applies;
- honors the same forbidden-paths **union** as DEV (`agents.dev.forbidden_paths` + every touched surface's `forbidden_paths`) for any file it edits;
- **never merges.**

```bash
gh pr checkout 42                       # DEV's existing branch (e.g. agent/dev/feat/42-csv-export)
git add <test files + touched impl test-ids>
git commit -m "test(reports): cover CSV export AC1-AC3"
git push                                # same branch — no new branch, no --force
```

See skill: project-board-protocol for the QC verdict and the post-commit `HEAD_SHA` pin.

## Sync & conflicts

Keep the branch current with `default_branch` so the PR merges cleanly:

```bash
git fetch origin
git rebase origin/<default_branch>     # preferred — clean linear history
# ...resolve any conflicts locally...
git add <resolved-files>
git rebase --continue
```

- **Rebase is the default** — it keeps a linear history. Use `git merge origin/<default_branch>` **only** when the project's documented convention requires merge commits (stated in `CLAUDE.md`, or branch-protection that mandates them); otherwise always rebase.
- Resolve conflicts **locally**; never push a branch with conflict markers.
- A rebase rewrites your branch, so the follow-up push needs a lease, not a plain force: `git fetch origin` immediately before, then `git push --force-with-lease --force-if-includes` (lease + include-check guard against clobbering work you haven't seen). Never on a branch someone else shares — see Safety rules.
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

- DEV: while coding, run the relevant `surfaces.<name>.commands` for every surface you changed (skip any command set to `""`). On a fresh or rebased branch, run `commands.install` **first** so deps are present before lint/test. **Lint/analyze must be green before handoff** — every touched surface's `commands.lint` (e.g. `go vet`, `flutter analyze`, `eslint`) must exit 0 before DEV hands the issue to QC. This is a named pre-handoff gate, not optional.
- QC: for the issue's tier, run each type in `agents.qc.tiers.<tier>` against **every** touched surface, in order; all must exit 0 (see skill: project-board-protocol). QC also runs `commands.install` first on its fresh PR-head checkout.

```bash
# For each surface S named by the issue's component/* labels (could be one, could be many):
for S in <the touched surface keys>; do
  ( cd <surfaces.$S.path> \
      && <surfaces.$S.commands.install> \   # FIRST — skip if "" (missing deps cause false-fail lint/test)
      && <surfaces.$S.commands.lint> \
      && <surfaces.$S.commands.test> )      # skip any "" command
done
```

Mention every touched surface in the PR body so QC knows the full command set to run.
