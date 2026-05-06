---
description: Create a new task on the AgentFlow project board from a freeform description.
argument-hint: <description of the work>
---

You are dispatching a new work item.

1. Confirm `.claude/agentflow.yaml` exists. If not, tell the user to run `/agentflow-init` first and stop.
2. Invoke the `po` sub-agent with this exact payload:

   ```
   USER_MESSAGE: $ARGUMENTS
   ```

3. Relay the PO's reply (issue link + summary) back to the user verbatim.

Do not write the issue yourself. Do not paraphrase the user's request. The PO agent owns intake.
