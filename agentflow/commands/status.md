---
description: Show an overview of the AgentFlow project board — counts per column.
---

Print a concise board summary for the project.

1. Read `.claude/agentflow.yaml` to get `project.repo` and `board.id`.
2. Use `gh api graphql` (or the GitHub MCP) to fetch the project's items grouped by column status.
3. Print this exact format:

   ```
   PROJECT: <repo> (board <id>)

   Inbox                   <n>
   Ready for Dev           <n>
   In Progress             <n>
   In QC                   <n>
   Ready for Human Review  <n>
   Done (last 7d)          <n>
   ```

4. Do not list individual cards. Counts only.
