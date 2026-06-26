---
description: Create a new AgentFlow work item (GitHub issue) from a freeform description, and add it to the repo's Project board so /start will pick it up.
argument-hint: <description of the work>
---

You are dispatching a new work item. PO owns intake; `/task` adds the result to the board.

1. Confirm `.claude/agentflow.yaml` exists in the current repo. If not, tell the user to run `/agentflow-init` first and stop.
2. Invoke the `po` sub-agent with this exact payload:

   ```
   USER_MESSAGE: $ARGUMENTS
   ```

   PO creates the issue, applies `type/*` + `component/*` labels, runs the DoR gate, and sets the initial `flow:*` label (`flow:ready-for-dev` | `flow:refined` | `flow:inbox`).

3. **Add the new issue to the board** (so the board-driven `/start` will poll it). `/task` does this itself — PO stays board-agnostic:
   - **Find the board.** Read this repo's `board.id` from `.claude/agentflow.yaml`. The board is always configured (`connections.github_project.enabled: true`, `board.id` is a non-empty `PVT_…`), so `/task` always mirrors the new issue onto the board.
   - Read the `flow:*` label PO just set, resolve the issue node id (`gh issue view <n> --repo <project.repo> --json id`), and **mirror** to the Status that the canonical `status_map` (skill: `project-board-protocol`) maps that label to — using `addProjectV2ItemById` (a brand-new issue has no card yet) then `updateProjectV2ItemFieldValue` per skill: `project-board-protocol` ("Mirror a flow:* label → column").

4. Relay the PO's reply (issue link + summary) back to the user verbatim, plus a one-line `added to board: <Status>` (a brand-new issue lands in `Inbox`).

Do not write the issue yourself. Do not paraphrase the user's request. The PO agent owns intake; `/task` only mirrors the result onto the board.
