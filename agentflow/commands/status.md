---
description: Show an overview of the AgentFlow pipeline — board-wide counts per status plus a per-repo breakdown (program mode), or open-issue counts per flow:* state (single-repo mode).
---

Print a concise pipeline summary.

## Program mode (shared board)

1. Search upward from cwd for `.claude/agentflow.program.yaml`. If found, read `program.name`, `board.id`, and `board.columns`.
2. **One board query** (skill: `project-board-protocol` → "List actionable board items"), paginating. This returns every item with its `repository.nameWithOwner`, issue `state`, and `Status` name — across **all** member repos in a single call.
3. Bucket **open** items two ways from that one result set (no extra calls):
   - **By status** (program-wide): count per `board.columns` value.
   - **By repo**: group by `repository.nameWithOwner`, then by status.
4. Print:

   ```
   PROGRAM: <program.name>   board <board.id>

   By status (all repos)
     Inbox                   <n>
     Refined                 <n>
     Ready for Dev           <n>
     In Progress             <n>
     In QC                   <n>
     Changes Requested       <n>
     Ready for Human Review  <n>
     Done                    <n>

   By repo
     <owner/repo-a>          Inbox 1 · Ready for Dev 2 · In QC 1
     <owner/repo-b>          Refined 1 · Changes Requested 1
   ```

## Single-repo mode (no program manifest)

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
