---
description: Manually reroute an issue to a specific agent or flow:* state, scoped to a repo, and mirror the new state to the shared board.
argument-hint: <owner/repo> <issue-number> <agent|flow:state>
---

Manual override for board routing. Useful for unblocking a card, bouncing back to PO, or skipping a stage.

Parse `$ARGUMENTS` as `<owner/repo> <issue-number> <target>`. With a multi-repo program a bare issue number is ambiguous, so the **repo is required**. If the first token is not `owner/repo`, show this grammar and stop. `<target>` is one of:

- `po` — reroute to PO (state `flow:inbox`)
- `dev` — reroute to DEV (state `flow:ready-for-dev`)
- `qc` — reroute to QC (state `flow:in-qc`, requires an open PR)
- `review` — mark for human review (state `flow:ready-for-human-review`)
- a literal `flow:*` label — set that state directly

Steps:

1. **Resolve the repo's config.** Search upward from cwd for `.claude/agentflow.program.yaml`; find the member whose `repo == <owner/repo>` and read that member's `.claude/agentflow.yaml` for `labels.flow` (+ `board.id` / `status_map`). If there is no program manifest, use the current repo's `.claude/agentflow.yaml` and require `<owner/repo>` to equal its `project.repo`.
2. Resolve the target `flow:*` label from `labels.flow`.
3. Read the issue's current `flow:*` label, then swap it, scoped to the repo:
   `gh issue edit <n> --repo <owner/repo> --remove-label "<current flow label>" --add-label "<target flow label>"`.
4. Comment on the issue: `[USER:<login>] Manually rerouted to <target>: <reason>` (substitute the repo owner's actual GitHub login) — ask the user for a one-line reason if none was given.
5. Append the event to the `AGENTFLOW-STATE` sticky comment (and update `Current state`).
6. **Mirror the new state to the board** (so the next `/start` poll doesn't re-route off a stale Status): map the new `flow:*` label → Status via `status_map`, resolve the issue node id, and run the mirror write in skill: `project-board-protocol`. Best-effort; on error, log and continue (the label stays authoritative). Skip if no `board.id` is configured.
7. If the target is `dev` or `qc`, invoke that sub-agent so it picks up immediately — in the member repo's directory and with `REPO: <owner/repo>` in the prompt.
