---
description: Chạy DESIGNER trên một ticket UI — biến brief của PMO thành design artifact (file trong design folder và/hoặc frame Figma + spec) theo đúng design system rules, rồi handoff cho DEV.
argument-hint: <#issue | mô tả công việc>
---

Bạn đang dispatch một design pass. DESIGNER phụ trách; `/design` chỉ định tuyến và mirror kết quả lên board.

## Boot checks (chạy một lần, theo thứ tự)

1. **Định vị repo config.** Tìm từ cwd đi ngược lên để tìm `.claude/agentflow.yaml`. Không tìm thấy → dừng: "No `.claude/agentflow.yaml` found. Run `/agentflow-init` in this repo first."
2. **Kiểm tra design đã bật.** Đọc `design.enabled`. Nếu không phải `true` → dừng: "Design step is disabled for this repo. Enable it by setting `design.enabled: true` (and `design.folder` / `design.rules_file`) in `.claude/agentflow.yaml`, and mark your UI surfaces with `ui: true` — or re-run `/agentflow-init`."
3. **Kiểm tra có surface UI.** Nếu không surface nào trong `surfaces.*` có `ui: true` → dừng: "No surface is marked `ui: true` — nothing for DESIGNER to work on. Mark your UI surfaces in `.claude/agentflow.yaml`."
4. **Auth check.** `GITHUB_TOKEN` có mặt và một probe `get_me` thành công. Thiếu/fail → báo user và dừng.

## Quy trình

1. **Phân giải `$ARGUMENTS`:**

   - **Bắt đầu bằng `#` hoặc là một số** → đây là một issue có sẵn. Đọc nó (`issue_read` method=`get`) và kiểm tra label:
     - Status "In Design" → tiếp tục thẳng sang bước 2.
     - Status "Inbox" và có label `component/*` của một surface `ui: true` → PMO chưa gate nó. Nói cho user biết và gợi ý chạy `/start` (hoặc để họ xác nhận) trước khi force; **đừng** tự ghi Status thay PMO — DoR gate là việc của PMO.
     - Status khác → dừng và nói state hiện tại là gì. Một ticket đang ở "In Progress" hay "In QC" thì không phải lúc làm design.
     - Mang aux label `design-review` → đây là một design review, không phải design pass: chuyển user sang `/design-review #<n>` và dừng.
   - **Là văn bản tự do** → chưa có ticket. Giao PMO intake trước, y hệt `/task`:

     ```
     USER_MESSAGE: $ARGUMENTS
     ```

     PMO tạo issue, gắn `type/*` + `component/*`, gate DoR, và ghi Status ban đầu. Nếu PMO route nó sang "Refined" (thiếu info) hoặc "Ready for Dev" (không đụng UI), **dừng lại** và relay kết quả đó — không có design pass nào để chạy. Chỉ tiếp tục khi nó ở "In Design".
   - **Rỗng** → liệt kê các ticket đang mở có Status "In Design" (`projects_list` method=`list_project_items`, `field_names: ["Status"]`, filter client-side, sort theo issue number) và hỏi user chọn cái nào. Không có cái nào → nói vậy rồi dừng.

2. **Spawn DESIGNER** với repo context tường minh:

   ```
   Agent(subagent_type="designer", prompt="ISSUE: #<n>\nREPO: <project.repo>")
   ```

   DESIGNER tự quyết đây là design **mới** hay **update** bằng cách đọc `design.folder` + Figma — đừng nói trước cho nó, và đừng hỏi user.

3. **Đọc lại Status** (`projects_get` method=`get_project_item` với `item_id`) — đó là state authoritative. Đọc `Resume hints` trong state section (`issue_read` method=`get`) nếu cần thêm ngữ cảnh.

4. **Mirror label → board Status** (best-effort) qua `status_map` canonical (skill: `project-board-protocol`). Lỗi thì log và tiếp tục — label vẫn authoritative.

5. **Relay** comment `[DESIGNER]` mới nhất nguyên văn, cộng một dòng state: `#<n> → <flow label mới>` và đường dẫn artifact / Figma node nếu có.

## Quy tắc bắt buộc

- **Không tự làm design.** DESIGNER làm; command này chỉ định tuyến. Đừng viết spec, đừng chọn token, đừng tạo file trong `design.folder`.
- **Không swap label thay cho agent.** Chỉ DESIGNER (hoặc PMO) đổi state của ticket.
- **Không mở PR, không merge.** Design artifact đi cùng PR của DEV; con người vẫn là người merge duy nhất.
- Nếu DESIGNER route ticket sang "Refined", relay câu hỏi của nó nguyên văn và bảo user dùng `/review-refined` — đừng tự trả lời thay con người.
