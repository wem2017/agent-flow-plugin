---
description: Hiển thị tổng quan pipeline AgentFlow của repo này — số open-issue theo từng state flow:*.
---

In ra một bản tóm tắt pipeline ngắn gọn cho repo này.

1. Đọc `.claude/agentflow.yaml` để lấy `project.repo` và `labels.flow`.
2. Đếm số open issue theo từng state, mỗi state một lệnh `gh`:

   ```bash
   gh issue list --repo <project.repo> --state open --label "<labels.flow.X>" --json number -q 'length'
   ```

   Với `done`, dùng `--label flow:done` (portable; tránh phép tính `date` phụ thuộc platform).
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
