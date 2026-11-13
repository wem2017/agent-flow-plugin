---
name: init
description: Cài AgentFlow lên repo hiện tại — kiểm token/quyền GitHub, link board có sẵn (map cột) hoặc tạo board mới theo preset, tạo label/issue type, scaffold issue form + PR template, chốt convention git và lệnh check từ chính repo, nối Figma + Telegram, ghi agentflow.yaml + .claude/settings.local.json rồi chạy smoke test. Chạy lại được (idempotent).
argument-hint: "(không có tham số — wizard tương tác)"
disable-model-invocation: true
---

Setup **một lần cho mỗi repo**, chạy lại an toàn. Đã có `agentflow.yaml` → đọc nó, dùng value làm mặc định cho từng bước, xác nhận trước khi ghi. `schema` khác `5` → nói rõ file sẽ được viết lại theo schema 5 (không migrate), hỏi lại từng giá trị.

Làm **theo thứ tự**. Precondition fail → nói đúng cách sửa rồi **dừng**. **Không bao giờ echo giá trị secret.** Mỗi bước hỏi người tối đa một lượt (gom câu hỏi), luôn kèm phương án đề xuất. Tool chẩn đoán: `agentflow-board` (nằm trên PATH khi plugin bật; `agentflow-board --help`).

## 1. Preconditions

```bash
git rev-parse --show-toplevel && git remote get-url origin && python3 --version
```

Không phải git repo / không có `origin` GitHub / không có `python3` (≥3.9) → dừng với hướng dẫn cụ thể. Mọi path dưới đây relative tới repo root.

## 2. Secret file guard — TRƯỚC khi nói tới token

```bash
for p in .claude/settings.local.json .claude/worktrees/; do
  git check-ignore -q "$p" || { [ -s .gitignore ] && [ -n "$(tail -c1 .gitignore)" ] && echo >> .gitignore; echo "$p" >> .gitignore; }
done
git check-ignore -q .claude/settings.local.json && echo ignored || echo "WARN not ignored"
git ls-files --error-unmatch .claude/settings.local.json >/dev/null 2>&1 && echo "WARN tracked — git rm --cached .claude/settings.local.json" || echo untracked
```

Chưa `ignored` + `untracked` → **dừng**.

## 3. Token + quyền

`agentflow-board whoami`. Token là token của `gh`: `$GH_TOKEN` → `$GITHUB_TOKEN` → `gh auth token` (script và MCP dùng chung — `scripts/mcp-headers.py` là `headersHelper` của MCP). Plugin không lưu token vào file nào.
Bắt buộc **full scope** (mọi scope classic token): `whoami` exit 1 ⇒ **dừng** tới khi đủ.
- Người tự chạy `! <lệnh gh auth>` lỗi in ra, rồi chạy lại `whoami`. Không đọc/in/ghi token hộ — guard chặn `gh auth token`.
- Refresh vẫn thiếu, hoặc token fine-grained → người tạo classic token theo link FAIL (ô tick sẵn), nạp ở terminal riêng: `gh auth login -h github.com --with-token`.
- `agentflow-settings has GITHUB_TOKEN` exit 0 (token cũ từ bản < 2.2) → đề nghị `agentflow-settings unset GITHUB_TOKEN` (tương tự `GH_TOKEN`): biến trong `env` được Claude Code đưa vào session và thắng tài khoản `gh`. Người muốn giữ thì để, doctor chỉ báo ⚠.
- Probe MCP `get_me` (tool deferred — nạp bằng ToolSearch trước). Fail mà script chạy được → `/mcp` → `plugin:agentflow:github` → Reconnect (helper đọc lại token mỗi lần connect, không cần restart).

## 4. Repo + convention (đọc từ repo, đề xuất, người chốt)

1. `agentflow-board repo <owner/repo của remote>` → canonical (`redirected: true` → báo một dòng, dùng canonical), owner type, default branch.
2. Đọc nếu có: `CONTRIBUTING.md`, `CLAUDE.md`, `.github/pull_request_template.md`, `.github/ISSUE_TEMPLATE/`, `.github/workflows/` (tên file), `git branch -r --sort=-committerdate | head -15`, `git log origin/<default> --format=%s -15`.
3. Đề xuất một bảng, người sửa/chốt:

| Key | Cách đề xuất |
|---|---|
| `git.base` | nhánh PR đang nhắm tới (CONTRIBUTING / PR gần đây); mặc định default branch |
| `git.protected` | nhánh môi trường/deploy (vd `production`, `main`), **không** gồm nhánh staging |
| `staging.branch` | nhánh chỉ để build test (`staging`, `develop`…), **khác** `git.base`, bắt buộc có trên origin. Không có → đề nghị tạo từ base, người đồng ý mới push |
| `git.branch` | pattern của nhánh gần đây; mặc định `{type}/{issue}-{slug}` |
| `git.commit` | Conventional Commits có scope surface nếu repo đang dùng |
| `git.link` | **`Closes`** — AgentFlow QC trước merge nên merge = xong. Repo đang dùng `Refs` (QC sau merge) → giải thích khác biệt một câu, người chọn |
| `types` | issue type của org (bước 6) hoặc tiền tố nhánh repo đang dùng (`feat`/`fix`/`improve`/`chore`) |

## 5. Surfaces + lệnh check

Scan marker (`package.json`, `pubspec.yaml`, `go.mod`, `pyproject.toml`, `Cargo.toml`, `build.gradle*`, `pom.xml`…) ở root và thư mục con cấp 1. Đề xuất mỗi phần build riêng một surface: `path`, `platform` (option của field Platform), `check` (typecheck/lint/format/analyze), `test`, `e2e` — **lấy nguyên lệnh** từ bảng quality gate trong CONTRIBUTING, script trong `package.json`, `Makefile`, hoặc job CI; `e2e_dir` = thư mục test e2e có sẵn (`e2e/`, `.maestro/`, `cypress/`, `integration_test/`, `testDir` của Playwright), DEV commit flow vào đó; mobile: `install` = lệnh build + cài bản trỏ staging lên emulator, lấy từ README/script, không đoán. Surface UI (mobile, web) chưa có e2e → Maestro: `e2e_dir: .maestro`, `e2e: maestro test .maestro`; đã có framework khác → hỏi người giữ hay chuyển Maestro. Repo một khối → bỏ hẳn `surfaces`, trừ khi có e2e (một surface `path: ./`). `forbidden`: thư mục secret thấy được (vd `secret/**`) + file credential.

## 6. Board

Chi tiết + lệnh: `${CLAUDE_PLUGIN_ROOT}/skills/init/references/board-setup.md`. Tóm tắt:
- **Link board có sẵn** (người dán URL) → `agentflow-board inspect <url>` → map 7 stage vào option Status theo tên gần nhất, trình bảng cho người chốt. Thiếu stage → `status-plan` (rename / thêm, giữ id option ⇒ card không mất Status) → người duyệt → `status-apply --yes`. Field Priority/Size/Platform thiếu → `ensure-field`.
- **Tạo board mới** → `agentflow-board create` với preset 7 cột + Priority/Size/Platform(+Sprint).
- Kiểm workflow *Item closed → Done* (doctor báo) — chỉ bật được bằng UI: hướng dẫn một dòng.
- Đề nghị cập nhật README của board theo luồng mới (template trong reference).

## 7. Issue type, label, template

- `classify`: org có issue types → `issue-type`; `agentflow-board issue-types --org <org>`, thiếu type trong `types` → đề nghị `--ensure` (cần quyền admin org). Repo cá nhân → `classify: label`, label = tên type.
- Label: `agentflow-board labels --repo <canonical> --label "<tên>|<màu>|<mô tả ≤100 ký tự>" …` cho mọi value trong `labels` (bảng màu + mô tả trong reference). Label đã có giữ nguyên tên, chỉ cập nhật màu/mô tả khi người đồng ý.
- Repo chưa có issue form / PR template → đề nghị scaffold từ `${CLAUDE_PLUGIN_ROOT}/templates/` (reference §Template). Có rồi → giữ, chỉ kiểm PR template có chỗ cho `<git.link> #` và "Kiểm chứng lại".

## 8. Figma, người, thông báo, loop

- **Figma**: dùng không? Có → `design.figma: true`; kiểm tool MCP `figma` có trong session; chưa authenticate → "chạy `/mcp` → figma → Authenticate". Thấy prototype trong repo (`docs/design`, `*.html` thiết kế…) → đề xuất `design.repo`.
- **people**: `po`, `qc`, `reviewers` (GitHub login) — gợi ý từ assignee/collaborator. Mention chính token owner không tạo notification.
- **Telegram**: dùng không? Có → `notify.telegram: true`; kiểm `agentflow-settings has TELEGRAM_BOT_TOKEN && agentflow-settings has TELEGRAM_CHAT_ID`; thiếu → người ghi bằng `set-secret` (có hiệu lực ngay), chưa có thì giữ `notify.telegram: false`.
- **staging**: `url` (API/web), `build` (cách lấy bản build mobile), `notes` (path secret folder của project chứa app id, tài khoản test, vd `secret/staging/` — gitignored, không nằm trong `forbidden`), `timeout_min`, `skip_checks` (glob tên check release mobile, DEV không chờ). Kiểm trong `.github/workflows/`: có pipeline chạy khi push vào nhánh staging và báo check về commit, không có → nói rõ DEV sẽ `blocked` khi hết timeout. Check phải bao trùm bước deploy server/web, không thì flow chạy nhầm bản cũ. Nhánh staging phải cho push trực tiếp, không bật rule bắt buộc PR hay status check trước khi push.
- **run**: giữ mặc định (`parallel 2`, `max_tasks 5`, `max_review_rounds 3`, `max_qc_rounds 2`, `max_test_rounds 3`, SA opus, DEV opus) trừ khi người muốn đổi.

## 9. Ghi file

1. **`agentflow.yaml`**: copy `${CLAUDE_PLUGIN_ROOT}/agentflow.yaml` rồi chỉ điền value (giữ comment). Không đọc được template → dừng, không dựng từ trí nhớ. Không bịa key mới.
2. **`.claude/settings.local.json`** — chỉ qua `agentflow-settings` (merge, giữ mọi key; `agentflow-settings show` xem cây key, value trong `env` bị che):
   - `agentflow-settings set enabledPlugins.<id> true` — id: `jq -r '.plugins|keys[]|select(startswith("agentflow@"))' ~/.claude/plugins/installed_plugins.json`.
   - `agentflow-settings set extraKnownMarketplaces.<marketplace>.source '<json>'` = source đang đăng ký trong `~/.claude/plugins/known_marketplaces.json` (không đọc được → bỏ, đừng bịa).
   - `agentflow-settings allow [--user] <rule…>` (rule: dòng ⚠ `permissions.allow` ở doctor) **chỉ khi người đồng ý** chạy loop không hỏi quyền; đề xuất `--user` (mọi repo) hơn repo này. Không dùng `defaultMode: bypassPermissions`: Claude Code bỏ qua nó trong settings project. Nói rõ: lớp chặn khi đó là hook của plugin (merge/approve PR, force-push, push nhánh protected, đọc/sửa `forbidden`). Hook đọc cấu trúc lệnh và mở lệnh bọc, nhưng không thấy được thứ chỉ lộ ra lúc chạy (script sinh sau, `make deploy`) — không tuyệt đối. Branch protection trên GitHub vẫn là lớp chắc nhất, doctor báo nếu base chưa có.
3. Repo nhiều người: `agentflow.yaml` commit được; mỗi người tự chạy `/agentflow:init` để có settings local riêng, và đăng nhập `gh` bằng tài khoản của mình.

## 10. Verify

1. `agentflow-board doctor` — phải `KẾT QUẢ: OK` (⚠ được phép), kể cả dòng `env của .claude/settings.local.json` khi bật Telegram. ✗ → sửa theo dòng báo rồi chạy lại.
2. **Smoke test đường runtime (MCP)** — bắt buộc, không cần hỏi: tạo issue `AgentFlow setup check` → `add_project_item` → `update_project_item` Status = `backlog` → `get_project_item` (`field_names:["Status"]`) assert = `backlog` → đổi sang `ready` và đọc lại → **dọn dẹp kể cả khi fail**: `delete_project_item` + đóng issue. Fail → bảng nguyên nhân trong reference §Smoke.
3. Guard: `printf '%s' '{"tool_name":"Bash","tool_input":{"command":"git push --force"},"cwd":"'"$PWD"'"}' | python3 "${CLAUDE_PLUGIN_ROOT}/scripts/guard.py"; echo $?` → phải `2`.
4. Telegram bật → `agentflow-notify blocked "AgentFlow: notify OK (setup check)"`.

## 11. Tóm tắt (≤ 15 dòng)

Repo · board (URL, map 7 stage) · base/protected · staging (branch, url, pipeline) · surfaces · labels · type mode · Figma · Telegram · people · permission mode · file đã ghi · việc tay còn lại (workflow board, Figma OAuth). Kết thúc: `Tiếp: /agentflow:task <mô tả> để tạo việc + chuyển Ready, rồi /agentflow:run (hoặc /agentflow:do #n).`
