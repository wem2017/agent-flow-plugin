# {{TITLE}} — cách làm việc

Board chung của PO, Dev, QC — có agent AgentFlow làm SA (solution architect) và Dev kiêm automation test. Người giữ đúng ba cổng: **chốt việc**, **QC tay khi cần**, **merge**.

## Luồng Status

**{{BACKLOG}} → {{READY}} → {{IN_PROGRESS}} → {{IN_REVIEW}} → {{IN_QC}} → {{READY_TO_MERGE}} → {{DONE}}**

| Cột | Ai | Việc |
|---|---|---|
| {{BACKLOG}} | PO | Viết vấn đề, giá trị, tiêu chí nghiệm thu (không viết giải pháp kỹ thuật), đặt Priority + Size, rồi **kéo sang {{READY}}** — hoặc dùng `/agentflow:task`: một expert PO cố vấn tới khi ticket đủ, bạn xác nhận thì nó chuyển giúp |
| {{READY}} | Agent SA → Agent DEV | SA phân tích yêu cầu, chọn giải pháp hợp tech stack, đánh giá rủi ro, lập test case, comment thiết kế (`[AF:SA] design`) và gắn `{{AGENT}}`; DEV nhận việc. Nhãn `{{QC_FAILED}}` = QC người trả về, sửa trước việc mới |
| {{IN_PROGRESS}} | Agent DEV | Code theo thiết kế, gắn element id, viết flow automation (Maestro), mở draft PR, merge lên staging, chờ deploy server/web, chạy flow liên quan, tự sửa tối đa 3 vòng. Vẫn fail ⇒ ghi lỗi block lên ticket + `{{BLOCKED}}` |
| {{IN_REVIEW}} | Agent SA | Review theo thiết kế: độ đúng, đủ, kiến trúc, bảo mật, hiệu năng, test. ✅: có mục QC tay ⇒ {{IN_QC}}, không ⇒ undraft ⇒ {{READY_TO_MERGE}} |
| {{IN_QC}} | QC người | Nhãn `{{QC_MANUAL}}` = test mục "QC tay" của PR trên staging |
| {{READY_TO_MERGE}} | Người | PR đã undraft. Approve + merge. Muốn sửa: comment trên dòng code của PR, Request changes, hoặc gắn `{{CHANGES_REQUESTED}}` |
| {{DONE}} | — | PR đã merge, issue tự đóng |

## Nhãn

- `{{BLOCKED}}` — bị chặn, lý do ở comment. Gỡ xong thì **bỏ nhãn**, agent tự chạy tiếp.
- `{{NEEDS_INFO}}` — agent cần thông tin. Trả lời trong comment rồi **bỏ nhãn**.
- `{{QC_FAILED}}` — QC người trả về: gắn nhãn này + comment lỗi khi test tay fail.
- `{{AGENT}}` — ticket do agent xử lý.

Nhánh staging chỉ để build test: DEV merge dồn nhánh ticket vào đó, không merge ngược về PR hay master. Nhánh lệch nhiều so với master thì người tự reset, agent không làm việc này.

## Góp ý trên PR

Comment trên dòng code của PR (hoặc Request changes) khi ticket ở {{IN_REVIEW}}, {{IN_QC}} hay {{READY_TO_MERGE}} → agent đưa ticket về {{IN_PROGRESS}}. DEV xét từng góp ý: hợp lý thì sửa rồi trả lời `[AF:DEV] fixed`, không hợp lý thì trả lời lý do `[AF:DEV] reply` ngay trong thread. Vẫn muốn sửa thì reply lại trong thread, agent sẽ làm theo. Xem xong thì bạn resolve thread. Comment thường (không gắn vào dòng code) chỉ được đọc kèm, không tự đưa ticket về.

## QC người

SA ✅ comment link mục "QC tay" của PR (bước + kỳ vọng), mục "Đề xuất kiểm chứng thêm" là regression nên xem, test trên staging. Pass: tick hết rồi kéo card sang **{{READY_TO_MERGE}}** (lượt agent kế tiếp sẽ undraft PR). Fail: gắn `{{QC_FAILED}}` + comment lỗi — agent tự sửa.

## Lệnh (Claude Code, trong repo)

`/agentflow:task <mô tả>` tạo issue · `/agentflow:do #n` xử lý một ticket · `/agentflow:run` chạy hết hàng đợi · `/agentflow:status` · `/agentflow:doctor` · `/agentflow:learn`
