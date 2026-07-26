---
description: Chạy design-QC trên UI mà DEV đã build — đối chiếu implementation với design artifact và design system rules, rồi ký duyệt hoặc trả về DEV kèm findings.
argument-hint: <#issue>
---

Bạn đang dispatch một design review. DESIGNER phụ trách verdict; `/design-review` chỉ định tuyến và mirror kết quả lên board.

Đây là entry point **thủ công** — chạy được bất cứ lúc nào ticket đã có PR. Khi `design.design_review: true`, QC cũng tự route ticket vào đúng pass này sau khi ✅, và bạn không cần gõ command.

## Boot checks (chạy một lần, theo thứ tự)

1. **Định vị repo config.** Tìm từ cwd đi ngược lên để tìm `.claude/agentflow.yaml`. Không tìm thấy → dừng: "No `.claude/agentflow.yaml` found. Run `/agentflow-init` in this repo first."
2. **Kiểm tra design đã bật.** `design.enabled` không phải `true` → dừng: "Design step is disabled for this repo — nothing to review against. Enable it in `.claude/agentflow.yaml`."
3. **Auth check.** `GITHUB_TOKEN` có mặt và một probe `get_me` thành công. Thiếu/fail → báo user và dừng.

## Quy trình

1. **Phân giải ticket.**
   - `$ARGUMENTS` là `#<n>` hoặc một số → dùng nó.
   - Rỗng → liệt kê các ticket đang mở mang aux label `design-review`, rồi tới các ticket có Status "Ready for Human Review" có đụng surface UI, và hỏi user chọn. Không có cái nào → nói vậy rồi dừng.

2. **Assert có PR để review.** Tìm open PR link tới issue: comment `[DEV] Opened PR #<m>` (authoritative), hoặc `search_pull_requests` với query `<issue#> in:body state:open`. **Không có open PR → dừng**: "Issue #<n> has no open PR — there's no built UI to review yet." Design review so implementation với artifact; không có implementation thì không có gì để so.

3. **Assert ticket đụng UI.** Ít nhất một label `component/*` của issue phải map tới một surface có `ui: true`. Không có → dừng và nói rõ ticket này không đụng surface UI nào.

4. **Đảm bảo ticket đang ở lane design review.** Nếu nó chưa mang aux label `design-review`, add nó bằng full-set update (đọc labels hiện tại → tính set mới → `issue_write` method=`update`, giữ nguyên mọi `type/*` / `component/*`) — **aux label đi TRƯỚC** — rồi ghi Status → "In Design" (`board.columns.in_design`) qua `projects_write` method=`update_project_item`. Ghi một dòng event vào state section nêu rõ review này do con người khởi động, và post một `[SYSTEM]` comment (Status change không tạo timeline event). Đây là **ngoại lệ có chủ đích** với quy tắc "command không tự ghi state" — nó chỉ mở lane cho DESIGNER, không quyết định gì về nội dung.

5. **Spawn DESIGNER:**

   ```
   Agent(subagent_type="designer", prompt="ISSUE: #<n>\nREPO: <project.repo>")
   ```

   Aux label `design-review` là thứ báo cho DESIGNER biết đây là review pass chứ không phải design pass.

6. **Đọc lại Status** (`projects_get` method=`get_project_item`):
   - "Ready for Human Review" → ✅ pass.
   - "Ready for Dev" + aux `rework` → ❌ fail, ticket đã quay về DEV.

7. **Mirror label → board Status** (best-effort) qua `status_map` canonical (skill: `project-board-protocol`).

8. **Relay** comment `[DESIGNER] ✅` / `[DESIGNER] ❌` nguyên văn, cộng một dòng state: `#<n> → <flow label mới>`.

## Quy tắc bắt buộc

- **Không tự đưa verdict.** DESIGNER quyết định pass/fail; command này chỉ định tuyến và relay.
- **Không sửa code để "fix" finding.** Fix là việc của DEV qua rework loop.
- **Không merge.** Kể cả khi ✅, con người vẫn là người merge duy nhất.
- Một `[DESIGNER] ❌` tính vào `consecutive_fail` y như QC ❌ và dùng chung ngưỡng escalation `2` — sau đó ticket park ở "Refined" chờ con người. Đừng chạy `/design-review` lặp lại để "thử lại"; sửa nguyên nhân trước.
