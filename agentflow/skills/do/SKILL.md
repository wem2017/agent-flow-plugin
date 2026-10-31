---
name: do
description: Xử lý MỘT issue chỉ định (#n) qua các stage agent làm được — DEV → REVIEWER → pipeline staging → QC — cho tới khi nó dừng ở cổng của người (Ready to Merge, QC tay, cần thông tin, bị chặn).
argument-hint: "#<số issue> [--model sonnet|opus]"
disable-model-invocation: true
---

Bạn là **orchestrator cho đúng một ticket**: `$ARGUMENTS`. Đọc `${CLAUDE_PLUGIN_ROOT}/references/protocol.md` rồi `${CLAUDE_PLUGIN_ROOT}/references/dispatch.md`, áp dụng y nguyên với hàng đợi chỉ có ticket này và giới hạn **1 ticket**.

## Khác với `/agentflow:run`

1. **Tìm item**: `issue_read method=get` (assert OPEN). Lấy `item_id` + Status + Priority/Size bằng `list_project_items` (`query: "is:open is:issue repo:<owner>/<repo>"`, `field_names` như dispatch §2, paginate) và match `number` + `content.repository` — dừng paginate ngay khi thấy. Không có trên board → `add_project_item` rồi coi Status trống như `backlog`.
2. **Ticket không có `labels.agent` mà assign cho người khác** → hỏi một câu xác nhận trước khi tiếp quản; không trả lời thì dừng. Có `labels.agent` thì assignee không quan trọng.
3. **Ticket không có `labels.agent` nhưng đang ở stage sau `ready`** (người tự làm dở) → hỏi xác nhận "agent tiếp quản #n ở <stage>?" — đồng ý thì gắn `labels.agent` rồi chạy theo bảng hành động.
4. **`backlog`** → đây là cổng của PO. Trình tóm tắt 3 dòng: AC có chưa, Size/Priority có chưa, cái gì còn thiếu. Đề nghị `/agentflow:task #<n>` để hoàn thiện spec. **Chỉ khi người dùng nói rõ chuyển sang Ready** (họ là PO đang ra quyết định) mới ghi Status `ready` rồi chạy tiếp.
5. **`blocked` / `needs_info`** → đọc comment chặn mới nhất, trình cho người: đã trả lời chưa? Người xác nhận đã gỡ → bỏ label rồi chạy tiếp; không thì dừng.
6. **`ready_to_merge`** → áp bảng dispatch §3 như thường (PR đã merge → *done*, QC người đã pass → *qc-manual-pass*, feedback → rework). Rơi vào dòng "chờ người merge" → báo, in link PR, dừng. Không bao giờ merge.
7. `--model` → ghi đè model của DEV cho ticket này.

Người dùng đang ngồi trước terminal: được hỏi **tối đa một câu** ở các điểm 2–5 trên. Sau khi bắt đầu chain thì không hỏi nữa.

## Báo cáo

Một khối ≤ 6 dòng: `#n` + tiêu đề, các stage đã đi qua (`ready → in_progress → in_review → in_qc → ready_to_merge`), PR + sha, việc người cần làm tiếp (kèm link), số lần spawn.
