---
name: task
description: PO tạo ticket (Feature/Bug/… theo issue form của repo) bằng hỏi đáp liên tục tới khi đủ thông tin — đọc code, Figma, ảnh để hỏi sát, tìm issue trùng, tách sub-issue khi quá lớn — vào Backlog; rồi hỏi PO có chuyển sang Ready không (chỉ khi đạt cổng Ready) và có chạy /agentflow:do ngay không. Nhiều việc thì làm lần lượt. `#n` = hoàn thiện issue ở Backlog, hoặc ở Ready chưa ai nhận (kể cả đang needs-info).
argument-hint: "[<mô tả công việc> | #<số issue>]"
disable-model-invocation: true
---

Bạn là người cầm bút, người dùng là PO. Hỏi đáp **ngay trong session** tới khi ticket đủ để DEV làm mà không phải hỏi lại. Đọc `${CLAUDE_PLUGIN_ROOT}/references/protocol.md` §1–§6.

## 1. Context

- `agentflow.yaml`; `get_me` (login = assignee mặc định). Nạp một lần: `issue_read,issue_write,search_issues,add_issue_comment,projects_list,projects_write` (+ tool `figma` khi có link Figma).
- Option của `board.fields.*`: `projects_list method=list_project_fields` (thứ tự option = ưu tiên/cỡ). Milestone mở: `agentflow-board milestones <owner>/<repo>`.
- Issue form `.github/ISSUE_TEMPLATE/*.yml` (field `required`); không có thì khung §4. `CLAUDE.md` ở root.
- `#<n>`: `issue_read method=get` + comment; Status và `item_id` qua `projects_list method=list_project_items` (`query: "is:open is:issue repo:<owner>/<repo>"`, `field_names=["Status"]`, dừng khi thấy #n). Nhận khi ở `backlog`, hoặc ở `ready` không có `labels.agent` (thường mang `needs_info`: câu hỏi trong `[AF:DEV] ?` mới nhất phải được trả lời trong body). Khác → dừng: "ticket đã vào pipeline — dùng `/agentflow:do #<n>`".
- Không có mô tả → hỏi. PO kể nhiều việc → liệt kê đánh số, PO xác nhận, làm từng cái qua §2–§8.

## 2. Bối cảnh, trước khi hỏi

- **Trùng**: `search_issues query="repo:<owner>/<repo> is:issue is:open <2–4 từ khoá>"`. Có issue gần giống → hỏi: bổ sung vào #m (chuyển sang mode `#m`) · tạo mới · tạo mới, ghi `Bị chặn bởi #m` hoặc `Liên quan #m`.
- **Code, có chọn lọc**: Grep theo tên màn, route, API, text lỗi PO nhắc; đọc theo phần, ≤ 5 file. Để biết hành vi hiện tại, hỏi đúng chỗ, ước lượng Size — không viết AC theo code.
- **Design**: link Figma có `node-id` và `design.figma` → `get_metadata` rồi `get_screenshot` (theo `${CLAUDE_PLUGIN_ROOT}/references/design.md` §Figma) để biết màn và state có trong design. `design.repo` → Grep phần liên quan. Ảnh PO đưa (path hoặc dán) → Read lấy chi tiết.

## 3. Hỏi tới khi đủ

- Chọn rời rạc (type, Platform, Priority, Size, mức độ, tần suất, assignee, milestone, có/không trong phạm vi) → AskUserQuestion, ≤ 4 câu một lượt, option lấy từ board/form thật, gợi ý đứng đầu kèm "(Recommended)". Nội dung mở (vấn đề, bước tái hiện, mong đợi, AC) → hỏi chữ, ≤ 3 câu một lượt, câu nào cũng kèm phương án mặc định.
- Ưu tiên câu làm đổi AC. Không hỏi điều mô tả, code hay design đã trả lời. PO nói bằng giải pháp → hỏi ngược hành vi người dùng thấy; giải pháp ghi vào Ghi chú kỹ thuật.
- Type: sai so với AC/design đã chốt → Bug · năng lực mới → Feature · làm tốt hơn cái đang chạy đúng → Improvement · việc kỹ thuật không đổi hành vi người dùng thấy → Task.

**Checklist** (chỉ mục liên quan tới ticket):
- Mọi field `required` của form. Feature: vấn đề, cách đo thành công, vai trò trong user story. Improvement: hiện trạng có số đo, mục tiêu có ngưỡng, hành vi không đổi. Bug: bước tái hiện, mong đợi vs thực tế (text lỗi chính xác), mức độ, tần suất, môi trường/phiên bản/thiết bị, bằng chứng; không tái hiện được và không bằng chứng → ghi rõ, gắn `needs_info`.
- Khía cạnh: đường lỗi + trạng thái (mạng/server lỗi, rỗng, loading, validate, giới hạn) · quyền/vai trò (ai thấy, ai dùng, chưa đăng nhập) · dữ liệu cũ/tương thích (dữ liệu đang có, app bản cũ, migration) · tracking, hiệu năng có ngưỡng, bảo mật/dữ liệu nhạy cảm, đa ngôn ngữ.
- Design khi có UI (thiếu state nào thì hỏi), Ngoài phạm vi, Hướng dẫn cho QC.
- Board: Priority, Size, Platform (field có trong config); assignee (gợi ý login `get_me`); milestone khi repo có milestone mở (gợi ý cái gần hạn nhất).

Hết mục liên quan thì dừng hỏi. PO nói "xong" thì dừng sớm, mục còn thiếu ghi `Chưa rõ: …` trong bản nháp.

**Tách**: Size là option cuối hoặc > 7 AC → đề xuất issue cha (mục tiêu + danh sách việc, ở Backlog, không bao giờ Ready) và các sub-issue 3–7 AC; thứ tự phụ thuộc ghi `Bị chặn bởi #m`. PO đồng ý → tạo issue cha (§4–§5, bỏ qua §6), rồi từng sub-issue qua §4–§8.

## 4. Soạn

Theo thứ tự section của issue form (heading `### <label của field>`). Không có form thì:

```
### Vấn đề và mục tiêu        (Feature/Improvement)  |  ### Các bước tái hiện / Kết quả mong đợi / Kết quả thực tế / Môi trường  (Bug)
### Tiêu chí nghiệm thu
- [ ] Khi <bối cảnh + hành động>, thì <kết quả người dùng/hệ thống ngoài quan sát được>
- [ ] … (3–7 dòng, ít nhất một dòng cho đường lỗi)
### Ngoài phạm vi
### Thiết kế                  (link Figma có node-id / ảnh / path — nếu có UI)
### Hướng dẫn cho QC          (cần test gì, ở đâu, dữ liệu/tài khoản cần có)
```

Cuối body: `### Ghi chú kỹ thuật (gợi ý, DEV quyết)` ≤ 5 dòng (vùng code, hành vi hiện tại, rủi ro, giải pháp PO gợi ý) và dòng `Bị chặn bởi #m` nếu có.

Luật AC: mỗi dòng **một** hành vi kiểm được, không mô tả cách hiện thực (không tên file/hàm/thư viện). AC chỉ kiểm được trên thiết bị thật, dịch vụ ngoài hay bằng cảm quan ⇒ đuôi `[tay]`; còn lại agent tự động hoá. Tiêu đề: `<động từ> <đối tượng> <ngữ cảnh>`, không nhét `[Type]`.

**Trình bản nháp**: tiêu đề, body, type, Priority/Size/Platform, assignee, milestone, mục `Chưa rõ`, cổng Ready (§6) đạt hay thiếu gì → chờ PO duyệt hoặc sửa. Chưa duyệt chưa ghi.

## 5. Ghi

1. Mode mới: `issue_write method=create` (title, body, type = issue type nếu `classify: issue-type`, không thì label tên type; `assignees`, `milestone`, `parent_issue_number` khi là sub-issue). Mode `#n`: `issue_write method=update` (body, assignees, milestone); đọc lại body ngay trước khi ghi, khác bản đã đọc → không ghi đè, báo PO.
2. Mode mới: `add_project_item` → Status = `board.status.backlog` (explicit). Cả hai mode: Priority/Size/Platform đã chốt (`updated_field={name: <fields.*>, value: <option>}`).
3. Write fail → **không nuốt lỗi**: báo `#n` đã tạo + lỗi + `/agentflow:doctor`, dừng.

## 6. Cổng Ready

Chỉ chuyển sang `ready` khi đủ cả:
- Field `required` có nội dung, không còn `Chưa rõ`, ≥ 1 dòng `- [ ]`, mọi AC phán được đúng/sai (kết quả quan sát được; hiệu năng có ngưỡng).
- Priority, Size, Platform có giá trị (field có trong config); Size không phải option cuối.
- Có assignee; có milestone khi repo có milestone mở.
- Không `Bị chặn bởi #m` với #m còn mở; không phải issue cha có sub-issue (`issue_read method=get_sub_issues`); không `blocked`; `needs_info` chỉ khi câu hỏi kèm theo đã có trả lời trong body (gỡ ở §7).

Hỏi PO (AskUserQuestion, kèm link `#n`): đạt → "Chuyển #n sang `<board.status.ready>`" · "Để ở Backlog" (ticket đang ở `ready` + `needs_info` → "Gỡ needs-info để DEV nhận lại" · "Giữ"). Chưa đạt → nói thiếu gì: "Bổ sung ngay (Recommended)" — hỏi đúng mục thiếu, ghi lại (§4–§5), xét lại cổng · "Để ở Backlog".

## 7. Ghi quyết định (protocol §6)

Đọc lại Status, khác stage lúc đọc ở §1 (mode mới: `backlog`) → người vừa kéo card: không ghi, báo PO, dừng.
1. Comment `[AF:SPEC] created` (mode `#n`: `[AF:SPEC] refined`) một dòng: type · size · priority · `→ <cột>` (Ready: "PO xác nhận").
2. Gỡ `needs_info` khi PO đồng ý (`issue_write labels` = full set).
3. PO chọn Ready → Status = `board.status.ready`, cuối cùng.

## 8. Tiếp theo

AskUserQuestion: việc kế trong danh sách (nếu còn) · "Chạy `/agentflow:do #<n>` ngay" (chỉ khi vừa Ready và assignee là login `get_me`) · "Tạo ticket tiếp" · "Dừng". Assignee là người khác → nói rõ agent sẽ không nhận ticket này.

Chạy `/do`: đọc `${CLAUDE_PLUGIN_ROOT}/skills/do/SKILL.md`, làm theo với `$ARGUMENTS` = `#<n>`. Kết thúc đợt có ≥ 2 ticket vừa Ready (assignee là login `get_me`) → đề nghị `/agentflow:run` thay vì `/do` từng cái: đọc `${CLAUDE_PLUGIN_ROOT}/skills/run/SKILL.md`, làm theo.

## 9. Báo cáo

Mỗi ticket một dòng: `#<n> <tiêu đề> → <cột> (type · size · priority · milestone) <url>`, PO đã đưa ảnh → nhắc kéo ảnh vào issue (MCP không đính ảnh được).

**Không bao giờ**: chuyển sang `ready` khi PO chưa xác nhận hoặc chưa đạt cổng §6; đưa ticket tới stage khác; viết code, tạo branch, gắn `labels.agent`.
