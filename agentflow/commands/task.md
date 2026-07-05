---
description: Tạo một AgentFlow work item mới (GitHub issue) từ một mô tả freeform, rồi thêm nó vào Project board của repo để /start pick lên.
argument-hint: <mô tả công việc>
---

Bạn đang dispatch một work item mới. PMO phụ trách intake; `/task` thêm kết quả vào board.

1. Xác nhận `.claude/agentflow.yaml` tồn tại trong repo hiện tại. Nếu không, bảo user chạy `/agentflow-init` trước rồi dừng.
2. Gọi sub-agent `pmo` với đúng payload sau:

   ```
   USER_MESSAGE: $ARGUMENTS
   ```

   PMO tạo issue, gắn label `type/*` + `component/*`, chạy DoR gate, và set label `flow:*` ban đầu (`flow:ready-for-dev` | `flow:refined` | `flow:inbox`).

3. **Thêm issue mới vào board** (để `/start` board-driven poll nó). `/task` tự làm việc này — PMO vẫn board-agnostic:
   - **Tìm board.** Đọc `board.number` của repo này từ `.claude/agentflow.yaml`. Board luôn được cấu hình (`connections.github_project.enabled: true`, `board.number` là một số project non-empty), nên `/task` luôn mirror issue mới lên board.
   - Đọc label `flow:*` mà PMO vừa set, và **mirror** sang Status mà `status_map` canonical (skill: `project-board-protocol`) map label đó tới — thêm card bằng `projects_write` method=`add_project_item` (`owner`, `owner_type`, `project_number` = `board.number`, `item_type=issue`, `item_owner`, `item_repo`, `issue_number`; issue brand-new chưa có card) rồi `update_project_item` để set Status, theo skill: `project-board-protocol` ("Mirror a flow:* label → column").

4. Relay reply của PMO (issue link + summary) lại cho user nguyên văn, cộng thêm một dòng `added to board: <Status>` (issue brand-new sẽ nằm ở `Inbox`).

Không tự viết issue. Không paraphrase request của user. Agent PMO phụ trách intake; `/task` chỉ mirror kết quả lên board.
