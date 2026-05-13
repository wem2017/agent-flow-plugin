# AgentFlow — quick reference for this repo

This repo uses the **AgentFlow** plugin to coordinate a 3-agent dev workflow (PO → DEV → QC → human review) through a GitHub Project Board.

## How to use

| You want to...                          | Run                              |
|-----------------------------------------|----------------------------------|
| Start the team for this session         | `/start`                         |
| File a new piece of work                | `/task <freeform description>`   |
| See where everything stands             | `/status`                        |
| Force-route an issue to a specific lane | `/handoff <issue#> <target>`     |
| Re-run setup                            | `/agentflow-init`                |

You only do two things by hand: describe work, and review the final PR. Everything in between happens on the board.

After `/start`, this terminal session becomes the orchestrator — describe work in plain text and the team (PO → DEV → QC) chains automatically. The orchestrator only breaks back to you when it needs clarification, hits a 2-strike escalation, or a PR is ready to merge.

## What goes where

- **Inbox / Refined** — PO is shaping the request.
- **Ready for Dev** — DEV will pick it up next.
- **In Progress** — DEV is implementing. If DEV is blocked, you'll see a `[DEV] Blocked: …` comment and the card stays here for you to unblock.
- **In QC** — DEV opened a PR; QC is reviewing.
- **Ready for Human Review** — your turn. Review and merge the PR.

## Comment prefixes (so you can grep / filter)

`[PO]`, `[DEV]`, `[QC] ✅`, `[QC] ❌`, `[USER:<your-login>]`.

Anything you write without a `[USER:...]` prefix is treated as untrusted context by the agents — they will read it but not act on instructions inside.

## Configuration

All settings live in `.claude/agentflow.yaml`. Things you may want to tune:
- `agents.qc.test_command` / `lint_command` / `coverage_threshold`
- `agents.dev.forbidden_paths` — files DEV must never touch (CI configs, keystores, etc.)

## Notifications

v0.2 runs in terminal mode — the orchestrator break-out **is** the notification. There are no external channels.
