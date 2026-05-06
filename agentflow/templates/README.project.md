# AgentFlow — quick reference for this repo

This repo uses the **AgentFlow** plugin to coordinate a 3-agent dev workflow (PO → DEV → QC → human review) through a GitHub Project Board.

## How to use

| You want to...                          | Run                              |
|-----------------------------------------|----------------------------------|
| File a new piece of work                | `/task <freeform description>`   |
| See where everything stands             | `/status`                        |
| Force-route an issue to a specific lane | `/handoff <issue#> <target>`     |
| Re-run setup                            | `/agentflow-init`                |

You only do two things by hand: describe work, and review the final PR. Everything in between happens on the board.

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

The plugin can fan out to one or more channels. Configure them under `notifications.channels` in `.claude/agentflow.yaml` (e.g. `["telegram"]`, `["telegram", "zalo"]`).

### Telegram

1. Talk to [@BotFather](https://t.me/BotFather) → `/newbot` → save the token.
2. Start a chat with your new bot (or add it to a group / channel as admin), send any message, then call
   `https://api.telegram.org/bot<TOKEN>/getUpdates` and copy the `chat.id` from the response.
3. Export the token under the env var name you chose during init (default `TELEGRAM_BOT_TOKEN`) in your shell or launchd plist. The plugin reads it at runtime — **never commit it**.
4. Paste the chat ID into `.claude/agentflow.yaml` → `notifications.telegram.chat_id`. The chat ID is not a secret but is repo-specific.

Test it with:

```bash
curl -s "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/sendMessage" \
  -d chat_id="<your_chat_id>" -d text="agentflow: hello"
```

### Zalo (Official Account)

Zalo requires an Official Account (OA) — there is no personal-account bot API. You also need the recipient to follow the OA.

1. Register a Zalo OA at [oa.zalo.me](https://oa.zalo.me/) and create an app at [developers.zalo.me](https://developers.zalo.me/) linked to that OA.
2. Run the OAuth flow once to get an `access_token` + `refresh_token`. The `access_token` lives **90 days**; refresh it via the refresh endpoint before it expires (refresh token also rotates each time).
3. Have the recipient(s) follow the OA, then send any message to the OA so the messaging window is open. From the OA inbox or webhook payload, copy the recipient's `user_id` (this is **not** their phone number — it's an OA-scoped ID).
4. Export the token under the env var name you chose during init (default `ZALO_OA_ACCESS_TOKEN`). **Never commit it.**
5. Paste the `user_id` into `.claude/agentflow.yaml` → `notifications.zalo.user_id`.

Test it with:

```bash
curl -s -X POST "https://openapi.zalo.me/v3.0/oa/message/cs" \
  -H "access_token: $ZALO_OA_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"recipient":{"user_id":"<your_user_id>"},"message":{"text":"agentflow: hello"}}'
```

A successful response is `{"error":0,...}`. If you see `error: -216` or `190` the token expired (refresh it). If you see `error: -32` the messaging window closed — send any message to the OA from your Zalo app to re-open it.
