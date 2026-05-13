---
description: Bootstrap AgentFlow in the current repo — create the board, labels, columns, and config file.
---

Set up AgentFlow for this repository. Invoke the **project-bootstrap** skill, which handles the entire flow:

1. Verify `gh` CLI is authenticated and the user has `repo` + `project` scopes.
2. Verify the current directory is a git repo with a GitHub remote. If not, ask the user.
3. Ask the user (sequentially, single answers):
   - Project name (default: repo name)
   - GitHub Project v2 mode: `create` a new one, or `link` an existing one
     - if `link`: accept project number or URL (`/orgs/<owner>/projects/<n>` or `/users/<user>/projects/<n>`)
   - Default branch (default: detect from `git symbolic-ref refs/remotes/origin/HEAD`)
   - Test command (default: detect — `flutter test` for Flutter, `npm test` for Node, `pytest` for Python, etc.)
   - Lint command (default: detect)

4. **Create or link** on GitHub:
   - If `create`: new Project v2 with the 7 standard columns (Inbox, Refined, Ready for Dev, In Progress, In QC, Ready for Human Review, Done)
   - If `link`: resolve the URL/number to a node ID via `gh project view`, then add only the missing canonical columns to the existing Status field (don't rename or delete what's already there; warn about extra columns AgentFlow won't manage)
   - Labels: `type/feature`, `type/improvement`, `type/bug`
5. **Generate** `.claude/agentflow.yaml` from the template, filled with answers above.
6. **Generate** `README.agentflow.md` at repo root.
7. **Create a verification issue** titled `[AgentFlow] Setup complete` and walk it through the columns to confirm the pipeline works end-to-end.
8. Print a final summary with: board URL, config file path, and the next command the user should try (`/start` to enter terminal team mode).
