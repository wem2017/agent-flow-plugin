---
name: project-bootstrap
description: Create the GitHub Project v2, the standard columns and labels, and write the .claude/agentflow.yaml config. Use this once per repo, invoked by /agentflow-init.
---

# Project bootstrap

End-to-end setup for a new repo. Idempotent — safe to re-run.

v0.2 runs in terminal mode — the orchestrator break-out is the notification, so this skill does **not** ask for Telegram/Zalo credentials and the generated yaml has no `notifications:` block.

## Preconditions

- `gh` CLI authenticated (`gh auth status`).
- Token scopes include `repo`, `project`, `read:org`.
- Working directory is a git repo with a GitHub remote (`git remote get-url origin`).

If any precondition fails, abort with a clear message — do not attempt to fix it for the user.

## Steps

### 1. Gather inputs

Ask the user one question at a time. Provide a default when sensible.

| Question                          | Default                                |
|-----------------------------------|----------------------------------------|
| Project display name              | repo name from `origin`                |
| GitHub Project mode               | `create` — new Project v2 (alt: `link` an existing one) |
| If `link`: project number or URL  | — accept `https://github.com/orgs/<owner>/projects/<n>`, `https://github.com/users/<user>/projects/<n>`, or bare `<n>` |
| Default branch                    | detect via `git symbolic-ref refs/remotes/origin/HEAD` |
| Test command                      | detect (see below)                     |
| Lint command                      | detect (see below)                     |
| Coverage threshold                | `80`                                   |

**Test/lint detection heuristics:**
- `pubspec.yaml` present → `flutter test` / `flutter analyze`
- `package.json` present → `npm test` / `npm run lint`
- `pyproject.toml` or `setup.py` → `pytest` / `ruff check .`
- `Cargo.toml` → `cargo test` / `cargo clippy --all-targets -- -D warnings`
- `go.mod` → `go test ./...` / `golangci-lint run`
- otherwise → leave blank, prompt user

### 2. Create or link the GitHub Project

**If mode = `create`:**

```bash
gh project create --owner <owner> --title "<name>" --format json
```

Capture the returned `id` (PVT_xxx node ID) and `number`. Then add the 7 columns via `gh project field-create` on the Status field. Use the canonical names from `templates/agentflow.yaml.template`.

**If mode = `link`:**

1. Parse the user's input — accept any of:
   - `https://github.com/orgs/<owner>/projects/<n>`
   - `https://github.com/users/<user>/projects/<n>`
   - bare project number `<n>` (assume current repo's owner)
2. Resolve to the node ID and verify access:
   ```bash
   gh project view <number> --owner <owner> --format json
   ```
   If the call fails, abort with the exact error and a hint about `project` scope on the token.
3. Inspect existing Status field options:
   ```bash
   gh project field-list <number> --owner <owner> --format json
   ```
   For each of the 7 canonical columns missing from the Status field, create it via `gh project field-create` (or add an option to the existing single-select Status field). Do **not** rename or delete columns the user already has — just add what's missing and warn the user about extra columns AgentFlow won't manage.

### 3. Create labels

`type/feature`, `type/improvement`, `type/bug`. Use `gh label create --force`.

### 4. Write `.claude/agentflow.yaml`

Copy `templates/agentflow.yaml.template` and substitute the gathered values. Do not commit the file yet — let the user review.

### 5. Write `README.agentflow.md`

Copy from `templates/README.project.md` to the repo root.

### 6. Verification ticket

Create an issue titled `[AgentFlow] Setup complete` with body:

```
This is a verification ticket. The PO/DEV/QC pipeline created it to confirm board automation works. Close it manually after the card moves through Inbox → Done in your board UI.
```

Add it to the project at column `Inbox`.

### 7. Final summary

Print:

```
✅ AgentFlow ready for <repo>
   Board:  <project URL>
   Config: .claude/agentflow.yaml
   Next:   /start   (then chat with the team in this terminal)
```

## Failure recovery

If any step fails after partial creation, print exactly what was created and what was not, plus the gh command needed to clean up. Do not silently retry — the user might be hitting a permissions issue.
