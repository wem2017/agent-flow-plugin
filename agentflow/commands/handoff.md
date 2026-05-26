---
description: Manually reroute an issue to a specific agent or flow:* state.
argument-hint: <issue-number> <agent|flow:state>
---

Manual override for board routing. Useful for unblocking a card, bouncing back to PO, or skipping a stage.

Parse `$ARGUMENTS` as `<issue-number> <target>` where target is one of:
- `po` — reroute to PO (state `flow:inbox`)
- `dev` — reroute to DEV (state `flow:ready-for-dev`)
- `qc` — reroute to QC (state `flow:in-qc`, requires an open PR)
- `review` — mark for human review (state `flow:ready-for-human-review`)
- a literal `flow:*` label — set that state directly

Steps:

1. Read `.claude/agentflow.yaml` for `project.repo` and `labels.flow`.
2. Resolve the target `flow:*` label.
3. Read the issue's current `flow:*` label, then swap it:
   `gh issue edit <n> --repo <repo> --remove-label "<current flow label>" --add-label "<target flow label>"`.
4. Comment on the issue: `[USER:<login>] Manually rerouted to <target>: <reason if provided>` (substitute the repo owner's actual GitHub login) — ask the user for a one-line reason if they did not supply one.
5. Append the event to the AGENTFLOW-STATE sticky comment (and update `Current state`).
6. If target is `dev` or `qc`, invoke that sub-agent so it picks up immediately.
