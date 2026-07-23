---
description: Tạo một AgentFlow work item mới (GitHub issue) từ một mô tả freeform, rồi thêm nó vào Project board của repo để /start pick lên.
argument-hint: <mô tả công việc>
---

Bạn đang dispatch một work item mới. PMO phụ trách intake; `/task` đảm bảo kết quả land trên board.

1. Xác nhận `.claude/agentflow.yaml` tồn tại trong repo hiện tại. Nếu không, bảo user chạy `/agentflow-init` trước rồi dừng. Gate `agentflow_version` (skill: `setup-agentflow` → "Version gate").
2. Gọi sub-agent `pmo` với đúng payload sau (`<project.repo>` đọc từ `.claude/agentflow.yaml`):

   ```
   USER_MESSAGE: $ARGUMENTS
   REPO: <project.repo>
   ```

   PMO tạo issue, gắn label classification `type/*` + `component/*`, shape body, rồi add issue lên board và set Status ban đầu `Inbox` (`board.columns.inbox`). **Intake không gate DoR** — orchestrator nhặt ticket từ inbox queue và spawn PMO Job 1b để gate. (WHY intake luôn land ở Inbox: `/start` chỉ scan inbox queue — pmo.md Job 1 / protocol §Claim & parallel terminals.)

3. **Đảm bảo issue nằm trên board với Status "Inbox"** (để `/start` board-driven poll nó — issue không có trên board là vô hình với routing). `/task` tự ghi explicit, kể cả khi PMO đã ghi, và không bao giờ dựa vào built-in workflow "Item added" (không verify được nó đã bật):
   - **Tìm board.** Đọc `board.number` + `board.columns` từ `.claude/agentflow.yaml` của repo này, và `owner`/`owner_type` từ `connections.github_project`. Board luôn được cấu hình.
   - Thêm card bằng `projects_write` method=`add_project_item` (`owner`, `owner_type`, `project_number` = `board.number`, `item_type=issue`, `item_owner`, `item_repo`, `issue_number`) — idempotent, trả item có sẵn nếu PMO đã add — rồi `update_project_item` set Status = `board.columns.inbox` (by-name shape, theo skill: `project-board-protocol` → reference "Status transition"). Ghi trùng value "Inbox" với PMO là same-value, vô hại.
   - **Board write là mandatory-success — fail thì KHÔNG nuốt lỗi.** Issue lúc đó tồn tại nhưng không nằm trên board, tức vô hình với `/start`. Báo user rõ: issue `#<n>` đã được tạo nhưng board write fail (kèm lỗi), rồi hướng dẫn retry sau khi fix nguyên nhân (thường là `GITHUB_TOKEN` thiếu scope `project`, hoặc `board.number` sai): chạy lại `/task` với issue sẵn có (chỉ lặp lại bước add này), hoặc add card thủ công trong Projects UI và set Status "Inbox". Lưới an toàn: membership check của `/status` cũng phát hiện issue OPEN nằm ngoài board.

4. Relay reply của PMO (issue link + summary) lại cho user nguyên văn, cộng thêm một dòng `added to board: <Status>` (issue brand-new nằm ở `Inbox`).

Không tự viết issue. Không paraphrase request của user.
