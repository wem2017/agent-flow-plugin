---
description: Show an overview of the AgentFlow pipeline — open-issue counts per flow:* state.
---

Print a concise board summary for the project.

1. Read `.claude/agentflow.yaml` to get `project.repo` and `labels.flow`.
2. Count open issues per state with one `gh` call each (no GraphQL, no board needed):

   ```bash
   gh issue list --repo <project.repo> --state open --label "<labels.flow.X>" --json number -q 'length'
   ```

   For the `done` count, use `--state closed --search "closed:>=$(date -v-7d +%F)"` (or `--label flow:done`) to approximate the last 7 days.
3. Print this exact format:

   ```
   PROJECT: <repo>

   Inbox                   <n>
   Refined                 <n>
   Ready for Dev           <n>
   In Progress             <n>
   In QC                   <n>
   Changes Requested       <n>
   Ready for Human Review  <n>
   Done (last 7d)          <n>
   ```

4. Do not list individual cards. Counts only.
