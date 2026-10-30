# Changelog

## 2.1.0 — 2026-10-30

Config `schema: 4`, không migrate — chạy lại `/agentflow:init` (cần nhánh staging + pipeline).

- Luồng mới: DEV mở **draft PR** → REVIEWER → ✅ merge dồn vào nhánh staging, push để build → In QC + nhãn `deploying`, orchestrator canh check của head staging → QC test trên staging → ✅ undraft → Ready to Merge. Feedback của người ở Ready to Merge đưa PR về draft.
- **REVIEWER** chạy Opus, vai expert software engineer / solution architect: mọi điểm chưa tối ưu đều ❌, có giới hạn để vòng sửa hội tụ. Tự giải conflict trên staging, không chắc thì `blocked`.
- **QC** chỉ test trên staging (API, e2e của repo, Chrome, mobile), không viết test, không commit. AC không tự động được thành checklist cho QC người, test trên staging.
- **QC ❌ về Ready** + `qc-failed`, kèm bước tái hiện, bằng chứng, nghi vấn; DEV sửa trước việc mới, rồi review phần mới → staging → QC lại. Review ❌ vẫn về In Progress.
- Pipeline fail: QC đọc log, do ticket → ❌, do hạ tầng/ticket khác → `blocked`. Quá `staging.timeout_min` → `blocked`.
- Config: thêm block `staging`, nhãn `labels.deploying`; `run.max_rounds` tách thành `max_review_rounds` (3) + `max_qc_rounds` (2); `run.models.reviewer` mặc định opus; bỏ `qc.pr_build`. State block: `round` tách thành `review_round` + `qc_round`, thêm `deploy_sha`, `deploy_at`.
- `agentflow-board checks`; doctor kiểm nhánh staging; guard cho push thường vào staging, vẫn chặn force-push, xoá nhánh và ghi file thẳng qua MCP.

## 2.0.0 — 2026-10-30

Viết lại toàn bộ (config `schema: 3`, không migrate từ v1.5 — chạy lại `/agentflow:init`).

- Luồng QC-trước-merge 7 stage (`backlog → ready → in_progress → in_review → in_qc → ready_to_merge → done`), tên cột thật map trong `board.status`.
- Thêm agent **REVIEWER**; QC viết thêm test, so UI với Figma, soạn checklist cho QC người (`qc-manual`).
- Chặn = label (`blocked`, `needs-info`) tại chỗ thay vì đẩy về Inbox; tự sửa khi có Request changes / `changes-requested` trên PR; escalate sau `run.max_rounds`.
- Lệnh mới: `/agentflow:do #n`, `/agentflow:run` (song song qua worktree, model theo Size), `/agentflow:doctor`, `/agentflow:learn` (thay `improve`, dùng journal). Bỏ `/agentflow:start`.
- Lệnh chuyển sang `skills/` với `disable-model-invocation` (không tốn context khi không gọi).
- Hook guard PreToolUse: chặn merge/approve PR, force-push, push base/protected, đọc/sửa/in secret.
- `bin/agentflow-board`: tạo board theo preset, sửa Status option giữ id (không mất card), field, label, issue type, doctor, metrics. `bin/agentflow-journal`, `bin/agentflow-notify`.
- State block ẩn (`<!-- agentflow:state -->`), comment `[AF:ROLE] event`, lệnh check của surface lưu trong config.
- GitHub MCP auth qua `headersHelper` (`scripts/mcp-headers.py`) — sửa lỗi connect chập chờn khi lấy `${GITHUB_TOKEN}` từ env của settings; đổi token chỉ cần `/mcp` → Reconnect.
- `.claude/settings.local.json` thành path forbidden; `bin/agentflow-settings` sửa nó mà không lộ secret. Guard chặn thêm dispatch workflow (`actions_run_trigger`, `gh workflow run`).
- Script HTTP tự fallback sang `curl` khi Python không tin được CA (python.org build trên macOS, proxy công ty).
