---
name: status
description: Tổng quan AgentFlow của repo này — số ticket theo stage, việc đang chờ người (merge, QC tay, cần thông tin, bị chặn), bất thường (issue đã đóng mà chưa Done, ticket agent bị người khác giữ, cột ngoài mapping). --metrics thêm flow metrics (cycle time, first-pass yield, số lần review/QC fail) và thống kê journal. Chỉ đọc.
argument-hint: "[--metrics] [--days N]"
disable-model-invocation: true
---

**Chỉ đọc — không ghi gì lên GitHub.** Dùng `agentflow-board` (một lệnh trả kết quả đã gom, rẻ token hơn nhiều so với đọc từng issue qua MCP).

## 1. Đếm

Đọc `agentflow.yaml` (schema gate). Chạy:

```bash
agentflow-board inspect "<board.url>" --done "<board.status.done>"
agentflow-board items "<board.url>" --open --fields "Status,<fields.priority>"
```

In bảng theo **stage** (dùng `board.status` để đổi tên cột → stage), không in từng card trừ các dòng chờ người:

```
<repo> · board <title>
backlog         <n>
ready           <n>    (QC trả về: <k>)
in_progress     <n>    (rework: <k>)
in_review       <n>
in_qc           <n>    (đang build staging: <d> · chờ QC tay: <k>)
ready_to_merge  <n>    ← chờ merge: #a, #b
done            <n>
Chờ người: needs-info #… · blocked #… · qc-manual #…
```

## 2. Bất thường (mỗi cái một dòng `⚠`, kèm cách sửa)

- `closed_not_done` khác rỗng → issue đã đóng mà card chưa sang done: kéo card, bật workflow *Item closed*.
- Option Status ngoài mapping có card (inspect `open_by_status` có tên không thuộc `board.status`) → card vô hình với agent.
- Status trống `(trống)` → card chưa vào luồng.
- Ticket mang `labels.agent` mà assign cho người khác → agent sẽ bỏ qua; người đó giữ hay trả lại?
- Ticket mang `labels.agent` ở `in_progress` không có rework label → DEV run trước có thể đã chết giữa chừng; `/agentflow:do #n` sẽ resume.
- Ticket mang `labels.deploying` đã quá `staging.timeout_min` theo `deploy_at` trong state → `/agentflow:run` sẽ gắn `blocked`.
- `.claude/worktrees/af-*` của issue đã đóng → `/agentflow:run` sẽ dọn, hoặc `git worktree remove`.

Sạch → `✓ không có bất thường`.

## 3. `--metrics` — **chỉ khi `$ARGUMENTS` có `--metrics`**, không thì bỏ qua mục này

```bash
agentflow-board metrics "<board.url>" --days <N|30> --stages "ready_to_merge=<board.status.ready_to_merge>" \
  --parked "<labels.blocked>,<labels.needs_info>,<labels.qc_manual>"
agentflow-journal stats
```

In nguyên output, thêm tối đa 3 dòng **nhận định**: first-pass yield thấp → agent nào hay bị trả về và vì sao (đọc 1–2 verdict ❌ gần nhất nếu cần); journal có ≥ 3 entry cùng loại → gợi `/agentflow:learn`.
