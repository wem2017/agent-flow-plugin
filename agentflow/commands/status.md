---
description: Show an overview of the AgentFlow pipeline for this repo — open-issue counts per flow:* state.
---

Print a concise pipeline summary for this repo.

1. Read `.claude/agentflow.yaml` for `project.repo` and `labels.flow`.
2. Count open issues per state with one `gh` call each:

   ```bash
   gh issue list --repo <project.repo> --state open --label "<labels.flow.X>" --json number -q 'length'
   ```

   For `done`, use `--label flow:done` (portable; avoid platform-specific `date` math).
3. Print:

   ```
   PROJECT: <repo>

   Inbox                   <n>
   Refined                 <n>
   Ready for Dev           <n>
   In Progress             <n>
   In QC                   <n>
   Changes Requested       <n>
   Ready for Human Review  <n>
   Done                    <n>
   ```

Counts only — do not list individual cards.
