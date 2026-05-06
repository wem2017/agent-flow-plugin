---
name: notify
description: Send a notification to the channel(s) configured in agentflow.yaml — Telegram and Zalo OA in v0.1. Use whenever a PR reaches Ready for Human Review or a build fails.
---

# Notify

Sends a single message to every configured channel. Reads `.claude/agentflow.yaml` → `notifications:` block.

## v0.1 supported channels

- `telegram` — Bot API `sendMessage`
- `zalo` — Zalo Official Account `message/cs` API
- `none` — no-op (skill returns immediately)

Email and ZNS template messages are out of scope for v0.1 (see "Alternatives" below).

## Inputs

```
channels: [telegram, zalo] | telegram | zalo | none   # falls back to yaml notifications.channels
event:    review_ready | build_failed
issue:    { number, title, repo, url }
detail:   one-line string
```

The caller must verify the event matches `notifications.triggers` in yaml before invoking this skill. The skill does not filter.

If `channels` is a list, send to each channel independently. A failure on one channel must not block the others.

## Common payload

`event_label` is humanised: `review_ready` → "Ready for review", `build_failed` → "Build failed".

The message body sent to every channel:

```
<event_label>: #<num> "<title>"
Detail: <detail>
Owner: <mention>
Link: <url>
```

## Telegram flow

1. Read `notifications.telegram.bot_token_env` from yaml. Read that env var. If unset, skip channel and return error `bot_token_env_missing`.
2. Read `notifications.telegram.chat_id`. If missing, skip and return `chat_id_missing`.
3. Read `notifications.telegram.mention` (optional).
4. POST to `https://api.telegram.org/bot<TOKEN>/sendMessage` via `curl`:

   ```json
   {
     "chat_id": "<chat_id>",
     "text": "<body>",
     "disable_web_page_preview": false
   }
   ```

5. Expect HTTP 200 with `{"ok": true}`. On non-200 or `ok: false` retry once with 2s backoff. On second failure, log and return error — do not throw.

## Zalo flow (Official Account `message/cs`)

1. Read `notifications.zalo.access_token_env` from yaml. Read that env var. If unset, skip and return `zalo_access_token_env_missing`.
2. Read `notifications.zalo.user_id`. If missing, skip and return `zalo_user_id_missing`. (This is the OA-scoped user_id of the recipient — not their phone or display name.)
3. POST to `https://openapi.zalo.me/v3.0/oa/message/cs` via `curl`:

   - Header: `access_token: <token>`
   - Header: `Content-Type: application/json`
   - Body:

     ```json
     {
       "recipient": { "user_id": "<user_id>" },
       "message":   { "text": "<body>" }
     }
     ```

4. Expect HTTP 200 with `{"error": 0, ...}`. On non-zero `error` field retry once with 2s backoff. On second failure, log and return error — do not throw.
5. **Token expiry**: Zalo OA `access_token` lives 90 days. If the response indicates expiry (error code `-216` / `190`), return `zalo_token_expired` so the caller can surface a refresh prompt. The skill does not refresh tokens itself.
6. **Messaging window**: the recipient must have interacted with the OA recently (followed + not exceeded inactivity window). If error code `-32` is returned, surface `zalo_window_closed` — the user needs to send any message to the OA to re-open the window.

## Hard rules

- **Never** echo bot tokens, OA access tokens, full webhook URLs, or chat/user IDs to the agent log. Read from env at call time and redact in any error output.
- **Never** include the issue body or PR diff in the notification — links only. Both Telegram chats and Zalo OAs may have multiple readers.
- One notification per event per card per 4h, **per channel**. The caller deduplicates using the AGENTFLOW-STATE event log.
- Channel failures are independent: if Telegram succeeds and Zalo fails, the overall result is a partial success — return per-channel status, not a single bool.

## Alternatives (out of scope for v0.1)

- **Zalo ZNS** — template-based transactional messages keyed by phone number. Requires template approval through Zalo Cloud. Better than `message/cs` for one-off alerts to users who haven't followed the OA, but the approval step makes it a poor fit for dev workflow. Add as `zalo_zns` channel in v0.2 if needed.
- **Inbound Telegram/Zalo commands** — both require a long-running webhook listener or polling worker, which a one-shot skill cannot provide. Tracked as v0.2.
