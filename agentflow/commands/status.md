---
description: Tổng quan pipeline AgentFlow của repo này — số board item theo từng Status column, kể cả ticket đã close mà Status còn kẹt ngoài Done. `--audit` chạy membership hai chiều + reconcile + orphan check (ticket /agentflow:start không nhặt lại được). `--metrics` tính flow metrics (throughput, cycle time, first-pass yield, rework/escalation rate, WIP, aging) suy ra từ transition comment + Status trên board.
argument-hint: "[--audit] [--metrics] [--since <N>d]"
---

In một bản tóm tắt pipeline gọn cho repo này.

1. Đọc `agentflow.yaml` ở repo root (`board.number`, `board.owner_type`); owner/repo suy từ `git remote get-url origin`. Version gate `agentflow: "1.0"`.
2. Đếm qua **một** lượt `projects_list` method=`list_project_items`, paginate toàn board (`per_page` ≤ 50, `after` cursor, **LUÔN truyền `field_names: ["Status"]`** — caveat: reference §"List board items"):
   - Group theo tên option Status (6 hằng số plugin).
   - Năm state đầu chỉ đếm item có issue `state == open`; **`Done` đếm riêng**: mọi item Status `Done` bất kể issue open/closed.
   - Trong `Inbox`, tách riêng số ticket mang aux `blocked` — **`/agentflow:start` không tự đụng chúng**, nên con số này là hàng đợi đang chờ chính bạn.
   - Item Status **trống** → đếm vào dòng riêng; phân loại bằng `--audit`.
   - **Item có issue `state == closed` mà Status ∉ {`Done`}** → đếm vào **dòng riêng, luôn liệt kê issue number**. Không có dòng này thì chúng rơi khỏi mọi con số (năm state đầu lọc `open`) và biến mất — reference §"Missing Status & membership" ca 4. Thường là: bạn đã merge PR trên github.com nhưng built-in workflow *"Item closed → Done"* chưa bật.
3. In:

   ```
   PROJECT: <owner/repo>   board #<N>

   Inbox                <n>   (trong đó blocked: <b> — chờ bạn, chạy /agentflow:task #<n>)
   Ready for Dev        <n>
   In Progress          <n>
   In QC                <n>
   Ready for Review     <n>
   Done                 <n>
   (Status trống)       <n>                    # chỉ in khi > 0
   ⚠ closed ≠ Done      <n>  #<a>, #<b>        # chỉ in khi > 0 — kéo card sang Done
   ```

Chỉ đếm số lượng — không liệt kê từng card (trừ dòng `blocked` và dòng `closed ≠ Done`: liệt kê issue number để bạn xử lý được ngay).

---

## `--audit` — membership + reconcile + orphan check

`Status` trên board **LÀ** state authoritative, nên không có gì để "đối chiếu drift". Nhưng còn ba lớp bất thường mà routing không tự thấy. `--audit` **chỉ đọc**, không sửa gì.

1. **Board pass:** một `projects_list` như trên; giữ cho mỗi item: issue number, issue state, assignees, tên option Status, aux label. Card **draft** (không có issue content) nằm ngoài state machine — liệt kê để người convert qua `/agentflow:task`.
2. **Membership check** — hai chiều, cả hai đều là "ticket vô hình":
   - `list_issues` (`state: "open"`, không filter label) → issue open nào **không có trên board** → liệt kê. Nó vô hình với routing.
   - Từ data bước 1 (không cần call thêm): item nào có issue `state == closed` mà Status ∉ {`Done`} → liệt kê. Đây là lane thoát bị bỏ lỡ — bạn merge PR trên github.com và built-in workflow *"Item closed → Done"* chưa bật. Fix: **kéo card sang `Done`**, rồi bật workflow đó (Project settings → Workflows) để lần sau không lặp lại.
3. **Reconcile check:** với mỗi board item có issue open, `issue_read` method=`get` lấy body, parse `Current state` trong block `<!-- AGENTFLOW-STATE -->` (1+K call — chấp nhận cho một lệnh chẩn đoán chạy tay). So với Status:
   - Lệch → liệt kê. **Không cần sửa tay**: pickup kế tiếp tự reconcile — Status thắng.
   - Status **trống** → Missing-Status rule (reference): case intake → coi như `Inbox` (bình thường); case ANOMALY → liệt kê, người re-set column.
4. **Orphan check** (từ data bước 1, không cần call thêm). `/agentflow:start` claim mọi ticket **unassigned + không `blocked` + Status ∈ {`Inbox`, `Ready for Dev`, `In QC`}**, và nhả claim mỗi khi nó dừng — nên chỉ còn hai lớp bất thường, cả hai đều là **assignee bị bỏ quên**. Các case dưới chỉ đúng khi không có terminal `/agentflow:start` nào đang thật sự chạy ticket đó (audit không tự kiểm được; bạn tự đối chiếu terminal của mình):
   - **Assigned + Status bất kỳ** → một terminal đã claim rồi chết trước khi nhả (crash, đóng terminal, mất mạng giữa chừng). Ticket vô hình với queue vì filter loại item có assignee. Fix: **unassign là đủ** — `/agentflow:start` sẽ tự nhặt lại đúng cột nó đang đứng (`Ready for Dev` / `In QC` chạy tiếp; `Inbox` chạy spec pass). Không cần kéo card.
   - **Unassigned + Status `In Progress`** → cột duy nhất không nằm trong queue (in-flight guard). Một DEV run đã chết giữa chừng. Fix: **kéo card về `Ready for Dev`** — DEV sẽ tái dùng branch/PR sẵn có và chạy tiếp, không build lại.
   - Ngoài hai case trên, một ticket unassigned ở `Inbox` / `Ready for Dev` / `In QC` là **bình thường** — nó đang nằm trong queue chờ `/agentflow:start`. Đừng báo động.
5. In `✓ mọi open issue đều có trên board, không issue closed nào kẹt ngoài Done, body khớp Status, không có ticket mồ côi` nếu sạch; ngược lại mỗi bất thường một dòng, ví dụ:

   ```
   ⚠ #57  open issue không có trên board — vô hình với /agentflow:start: add card (hoặc /agentflow:task #57)
   ⚠ #53  issue CLOSED nhưng Status "Ready for Review" — kéo card sang Done; bật workflow "Item closed → Done"
   ⚠ #42  body Current state "In QC" ≠ Status "Inbox" (pickup kế tiếp tự reconcile — Status thắng)
   ⚠ #48  assigned, Status "In QC" — claim mồ côi: nếu không terminal nào đang chạy → unassign, /agentflow:start tự nhặt lại
   ⚠ #61  unassigned, Status "In Progress" — DEV run đã chết giữa chừng: kéo card về "Ready for Dev"
   ```

---

## `--metrics` — flow metrics

**Nguồn dữ liệu, và vì sao là nó.** Projects v2 **không có history API** — Status change không tạo timeline event — nên không đọc ngược được "ticket ở column nào lúc nào". Nhưng protocol bắt **mọi transition phải kèm một comment có prefix**, và GitHub gắn `created_at` chính xác tới giây cho từng comment. Vậy **transition comment CHÍNH LÀ event log của pipeline**, còn Status sống trên board cho biết hiện tại ticket ở đâu.

> Dùng comment, **không** dùng `Event log` trong AGENTFLOW-STATE: event log chỉ có độ phân giải theo ngày, do agent soạn bằng prose nên format có thể trôi, và bị prune.

**Giới hạn phải nói thẳng khi in kết quả:** độ phân giải chỉ tới mức **có comment** (agent bỏ sót comment → đoạn đó vô hình); ticket bị xoá comment thì mất; đây là **reconstruction best-effort**, không phải per-status timing chính xác.

1. **Window** — mặc định `--since 30d`; parse `--since <N>d` nếu có.
2. **Board pass** — một lượt `list_project_items` như trên.
3. **Chọn tập ticket đọc comment** (bước tốn call nhất): chỉ ticket có Status ≠ `Done`, cộng item `Done` mà issue `closed_at` nằm trong window. In rõ `N ticket scanned`. Tập > ~60 → cảnh báo một dòng về số call rồi hỏi có tiếp không.
4. **Comment pass** — `issue_read` method=`get_comments` cho từng ticket; lấy `created_at` + prefix (bỏ comment không prefix — untrusted, và không phải transition):

   | Prefix | Mốc |
   |---|---|
   | `[SPEC]` **đầu tiên** | ticket bắt đầu được spec — `t_start` |
   | `[DEV] Picked up` / `[DEV] Opened PR` | DEV bắt đầu / handoff sang QC |
   | `[QC] ❌` | một lần rework (đếm) |
   | `[QC] ❌ infra:` | **KHÔNG** tính là rework (lỗi môi trường) |
   | `[QC] ✅` | pass — `t_qc_pass` |
   | `[SYSTEM] auto-escalated` | một lần escalation (đếm) |
   | `[SYSTEM] merged PR` | `t_done` |
   | `[DEV] ?` / `[QC] ?` | một lần clarification bounce (đếm) |

5. **Tính** (mỗi metric nêu rõ mẫu số):
   - **Throughput** — số ticket có `[SYSTEM] merged PR` (fallback: issue `closed_at`) trong window.
   - **Cycle time** — `t_done − t_start`; in **median** và **p90** (median chống outlier tốt hơn mean cho mẫu nhỏ). Ticket không đủ hai mốc thì loại và ghi rõ số bị loại.
   - **Time-to-first-PR** — `[DEV] Opened PR` đầu tiên `− t_start`, median.
   - **First-pass yield** — % ticket đạt `[QC] ✅` mà **không** có `[QC] ❌` nào trước đó. Đây là chỉ số chất lượng quan trọng nhất: nó đo DEV có làm đúng ngay từ đầu không.
   - **Rework rate** — tổng `[QC] ❌` (loại `infra:`) ÷ số ticket đã qua QC.
   - **Escalation rate** — % ticket có ≥1 `[SYSTEM] auto-escalated`.
   - **Blocked rate** — % ticket từng phải quay về người (suy từ `[DEV] ?`, `[QC] ?`, `[SYSTEM] auto-escalated`). Cao = spec vào pipeline còn mỏng.
   - **WIP hiện tại** — đếm live theo column cho `Ready for Dev` / `In Progress` / `In QC`.
   - **Aging** — với ticket đang **park** (`Inbox +blocked`, `Ready for Review`), tính `now − created_at` của comment mới nhất. **Liệt kê từng cái quá 3 ngày** — đây là phần hành động được nhất của cả lệnh: nó chỉ đúng ticket đang chặn dòng chảy.

6. **In:**

   ```
   PROJECT: <owner/repo>   window: last <N>d   scanned: <K> tickets

   FLOW
     Throughput (merged)        <n>
     Cycle time  median / p90   <Xd Yh> / <Xd Yh>      (<m> ticket đủ mốc, <e> bị loại)
     Time to first PR (median)  <Xh>

   QUALITY
     First-pass yield           <n>%   (<a>/<b> ticket qua QC không lần ❌ nào)
     Rework rate                <x.x> ❌/ticket        (infra failures không tính)
     Escalation rate            <n>%   (<a>/<b>)
     Blocked rate               <n>%   (<a>/<b>)

   WIP  (live)
     Ready for Dev <n> · In Progress <n> · In QC <n>

   AGING  (đang chờ người > 3d)
     #42  Ready for Review  6d   PR #57 chờ merge
     #38  Inbox +blocked    4d   chờ bạn trả lời [DEV] ? về scope export

   Nguồn: transition comment (timestamp GitHub) + Status trên board. Projects v2 không có history
   API, nên đây là reconstruction best-effort — độ phân giải tới mức có comment.
   ```

Không ticket nào đủ dữ liệu → in `chưa đủ dữ liệu trong window — thử /agentflow:status --metrics --since 90d`. `--metrics` **chỉ đọc**; kết hợp được với `--audit` (chạy lần lượt, dùng chung board pass).
