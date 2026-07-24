# Changelog

Mỗi entry = một lượt cải tiến (thường qua `/improve`): tóm tắt bài học + files đã đổi.

## [0.7.0] - 2026-07-24

Lượt này đến từ một expert review đa tầng của chính plugin (không phải từ một session usage đơn lẻ).

- **Human merge gate giờ được enforce ở tầng tool, không còn là honor-system.** Thêm `disallowedTools`
  vào frontmatter cả ba agent: cả ba **mất hẳn** `merge_pull_request`; PMO mất thêm
  `create_pull_request` / `pull_request_review_write` / `Edit` / `Write` / `NotebookEdit`; DEV mất
  `pull_request_review_write` (không tự approve PR của mình); QC mất `create_pull_request`. Trước đây
  một agent bị derail/inject vẫn gọi được tool merge — prose là thứ duy nhất chặn nó. Ghi rõ trong
  README phần nào **chưa** enforce (`forbidden_paths`, force-push, và `Bash` vẫn là escape hatch) để
  không tạo cảm giác an toàn giả — files: agents/pmo.md, agents/dev.md, agents/qc.md, README.md
- **Connection `notify` (Telegram) — outbound break-out notification tùy chọn.** `/start` mirror mỗi
  break-out ra kênh ngoài (`refined` / `blocked` / `stuck` / `ready_for_human_review`), giúp chạy
  `/loop` unattended không còn mù — trước đây ticket park ở `Refined` mà không ai biết cho tới khi
  quay lại terminal. Ping **một chiều tới con người**: không agent nào đọc kênh này và board vẫn là
  nơi phối hợp duy nhất, nên non-goal "no message bus" nguyên vẹn. Gate-before-use như figma; send là
  best-effort, fail không bao giờ dừng pipeline. Init có smoke test để bắt sai token/chat id ngay lúc
  setup — files: templates/agentflow.yaml.template, skills/setup-agentflow/SKILL.md, commands/start.md,
  commands/agentflow-init.md, .env.example, README.md, templates/README.project.md
- **`/status --metrics` — flow metrics cho người quản lý pipeline.** Throughput, cycle time
  median/p90, time-to-first-PR, **first-pass yield**, rework rate (loại trừ `infra:`), escalation
  rate, DoR bounce rate, WIP live, và danh sách ticket đang chờ người quá 3 ngày. Suy ra từ **các
  transition comment** (timestamp GitHub chính xác) + Status trên board — Projects v2 không có history
  API nên đây là reconstruction best-effort, và output nói thẳng điều đó. `--since <N>d` đổi window;
  giới hạn tập ticket đọc comment để chặn chi phí call — files: commands/status.md, README.md,
  templates/README.project.md
- **Sửa các message "reply `go`" gây hiểu nhầm.** `go` chỉ drain inbox queue, **không resume** một
  ticket đã claim đang nằm ngoài Inbox — nhưng break message ở safety cap, ở `In Progress`, và ở
  no-progress guard đều gợi ý ngược lại, dẫn user vào ngõ cụt. Giờ nói rõ ticket sẽ không tự resume
  và trỏ đúng đường phục hồi (`/status --audit` → unassign + kéo về Inbox, hoặc `/review-refined`).
  `/status --audit` cũng thôi gọi case này là "nghi orphan sau crash" — nó sinh ra từ cả các đường
  **bình thường** (chạm cap, hết turn, DEV blocked) — files: commands/start.md, commands/status.md
- **Sync card marketplace đã stale 2 version** — vẫn quảng cáo `flow:*` labels (bỏ từ v0.4.0), role
  `PO` (giờ là PMO), prefix `po-*` (giờ `pmo-*`). Đây là text đầu tiên user đọc trước khi cài, và nó
  drift được lâu như vậy vì `claude plugin validate` không đọc file nằm ngoài `agentflow/` — CONTRIBUTING
  giờ ghi rõ khoảng mù đó — files: .claude-plugin/marketplace.json, .claude-plugin/plugin.json

## [0.6.0] - 2026-07-23
- Thêm command `/improve` — vòng lặp tự cải tiến plugin: nhận bài học từ usage thực tế (trống → tự mine session tìm friction point), route vào đúng file tri thức trong SOURCE (confirm-first, phân tầng plugin/project, STOP cho protocol-change class), bump version + CHANGELOG, chạy release loop theo CONTRIBUTING.md — files: commands/improve.md, README.md, CONTRIBUTING.md
- Bootstrap CHANGELOG (lịch sử 0.1.0→0.5.0 trước đó không backfill)
