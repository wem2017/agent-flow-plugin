---
description: Manually reroute an issue to a specific agent or column.
argument-hint: <issue-number> <agent|column>
---

Manual override for board routing. Useful for unblocking a card, bouncing back to PO, or skipping a stage.

Parse `$ARGUMENTS` as `<issue-number> <target>` where target is one of:
- `po` — reroute to PO (moves card to `Inbox`)
- `dev` — reroute to DEV (moves card to `Ready for Dev`)
- `qc` — reroute to QC (moves card to `In QC`, requires an open PR)
- `review` — mark for human review (moves to `Ready for Human Review`)
- a literal column name in quotes — move directly to that column

Steps:

1. Read `.claude/agentflow.yaml` for repo + board ID + column mapping.
2. Resolve the target column name.
3. Move the card via GitHub Projects v2 API.
4. Comment on the issue: `[USER:owner] Manually rerouted to <target>: <reason if provided>` — ask the user for a one-line reason if they did not supply one.
5. Append the event to the AGENTFLOW-STATE sticky comment.
6. If target is `dev` or `qc`, invoke that sub-agent so it picks up immediately.
