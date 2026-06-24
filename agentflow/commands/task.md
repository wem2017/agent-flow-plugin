---
description: Create a new AgentFlow work item (GitHub issue) from a freeform description, and add it to the shared Project board so /start will pick it up.
argument-hint: <description of the work>
---

You are dispatching a new work item. PO owns intake; `/task` adds the result to the board.

1. Confirm `.claude/agentflow.yaml` exists in the current repo. If not, tell the user to run `/agentflow-init` first and stop.
2. Invoke the `po` sub-agent with this exact payload:

   ```
   USER_MESSAGE: $ARGUMENTS
   ```

   PO creates the issue, applies `type/*` + `component/*` labels, runs the DoR gate, and sets the initial `flow:*` label (`flow:ready-for-dev` | `flow:refined` | `flow:inbox`).

3. **Add the new issue to the shared board** (so the board-driven `/start` will poll it). `/task` does this itself — PO stays board-agnostic:
   - **Find the board.** Search upward from cwd for `.claude/agentflow.program.yaml`. If found, read `board.id` + `status_map` and confirm this repo (`gh repo view --json nameWithOwner -q .nameWithOwner`) is one of `members[].repo`. If no program manifest, fall back to this repo's own `board.id` (from `.claude/agentflow.yaml`). If neither is set (labels-only) → **skip the board step** (the issue still routes by label) and say so.
   - Read the `flow:*` label PO just set, resolve the issue node id (`gh issue view <n> --repo <repo> --json id`), and **mirror** to the Status that `status_map` maps that label to — using `addProjectV2ItemById` (a brand-new issue has no card yet) then `updateProjectV2ItemFieldValue` per skill: `project-board-protocol` ("Mirror a flow:* label → column").

4. Relay the PO's reply (issue link + summary) back to the user verbatim, plus a one-line `added to board: <Status>` (or `labels-only: no board configured`).

Do not write the issue yourself. Do not paraphrase the user's request. The PO agent owns intake; `/task` only mirrors the result onto the board.
