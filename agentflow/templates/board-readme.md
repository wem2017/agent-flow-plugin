# {{TITLE}} — cách làm việc

Board chung của PO, Dev, QC — có agent AgentFlow làm Dev, Reviewer và QC tự động. Người giữ đúng ba cổng: **chốt việc**, **QC tay khi cần**, **merge**.

## Luồng Status

**{{BACKLOG}} → {{READY}} → {{IN_PROGRESS}} → {{IN_REVIEW}} → {{IN_QC}} → {{READY_TO_MERGE}} → {{DONE}}**

| Cột | Ai | Việc |
|---|---|---|
| {{BACKLOG}} | PO | Viết tiêu chí nghiệm thu, đặt Priority + Size, rồi **kéo sang {{READY}}** |
| {{READY}} | Agent DEV | Nhận việc, tạo nhánh, code. Nhãn `{{QC_FAILED}}` = QC trả về, sửa trước việc mới |
| {{IN_PROGRESS}} | Agent DEV | Code, chạy check, mở draft PR; sửa theo review |
| {{IN_REVIEW}} | Agent Reviewer | Review độ đúng, đủ và chất lượng giải pháp; ✅ thì merge lên staging |
| {{IN_QC}} | Agent QC (+ QC người) | Nhãn `{{DEPLOYING}}` = chờ pipeline staging. Sau đó test trên staging, viết test e2e tự động và commit vào PR; nhãn `{{QC_MANUAL}}` = chờ QC người test tay theo checklist |
| {{READY_TO_MERGE}} | Người | PR đã undraft. Approve + merge. Muốn sửa: comment trên dòng code của PR, Request changes, hoặc gắn `{{CHANGES_REQUESTED}}` |
| {{DONE}} | — | PR đã merge, issue tự đóng |

## Nhãn

- `{{BLOCKED}}` — bị chặn, lý do ở comment. Gỡ xong thì **bỏ nhãn**, agent tự chạy tiếp.
- `{{NEEDS_INFO}}` — agent cần thông tin. Trả lời trong comment rồi **bỏ nhãn**.
- `{{QC_FAILED}}` — QC trả về (QC người: gắn nhãn này + comment lỗi khi test tay fail).
- `{{DEPLOYING}}` — đã merge lên staging, đang chờ pipeline.
- `{{AGENT}}` — ticket do agent xử lý.

Nhánh staging chỉ để build test: PR đã review được merge dồn vào đó, không merge ngược về PR hay master. Nhánh lệch nhiều so với master thì người tự reset, agent không làm việc này.

## Góp ý trên PR

Comment trên dòng code của PR (hoặc Request changes) khi ticket ở {{IN_REVIEW}}, {{IN_QC}} hay {{READY_TO_MERGE}} → agent đưa ticket về {{IN_PROGRESS}}. DEV xét từng góp ý: hợp lý thì sửa rồi trả lời `[AF:DEV] fixed`, không hợp lý thì trả lời lý do `[AF:DEV] reply` ngay trong thread. Vẫn muốn sửa thì reply lại trong thread, agent sẽ làm theo. Xem xong thì bạn resolve thread. Comment thường (không gắn vào dòng code) chỉ được đọc kèm, không tự đưa ticket về.

## QC người

Agent comment checklist `[AF:QC] 🧪`, test trên staging. Pass: tick hết rồi kéo card sang **{{READY_TO_MERGE}}** (lượt agent kế tiếp sẽ undraft PR). Fail: gắn `{{QC_FAILED}}` + comment lỗi — agent tự sửa.

## Lệnh (Claude Code, trong repo)

`/agentflow:task <mô tả>` tạo issue · `/agentflow:do #n` xử lý một ticket · `/agentflow:run` chạy hết hàng đợi · `/agentflow:status` · `/agentflow:doctor` · `/agentflow:learn`
