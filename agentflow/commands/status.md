---
description: Hiển thị tổng quan pipeline AgentFlow của repo này — số open-issue theo từng state flow:*.
---

In ra một bản tóm tắt pipeline ngắn gọn cho repo này.

1. Đọc `.claude/agentflow.yaml` để lấy `project.repo` và `labels.flow`.
2. Đếm số open issue theo từng state, mỗi state một lần gọi `list_issues` (7 flow state → 7 call):

   - Params: `owner`/`repo` (parse từ `project.repo` dạng `owner/repo`), `labels: ["<labels.flow.X>"]`, `state: "open"`.
   - Đếm số item trả về cho mỗi state.

   Với `done`, dùng `labels: ["flow:done"]` (portable; tránh phép tính `date` phụ thuộc platform).
3. In ra:

   ```
   PROJECT: <repo>

   Inbox                   <n>
   Ready for Dev           <n>
   In Progress             <n>
   In QC                   <n>
   Refined (needs human)   <n>
   Ready for Human Review  <n>
   Done                    <n>
   ```

Chỉ đếm số lượng — không liệt kê từng card.
