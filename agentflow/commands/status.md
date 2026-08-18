---
description: Tổng quan pipeline AgentFlow của repo này — đếm board item theo từng Status column, kể cả ticket đã close mà Status còn kẹt ngoài Done. `--audit` chạy membership hai chiều + reconcile + orphan check (ticket /agentflow:start không nhặt lại được). `--metrics` tính flow metrics (throughput, cycle time, first-pass yield, rework/escalation rate, WIP, aging) suy ra từ transition comment + Status trên board.
argument-hint: "[--audit] [--metrics] [--since <N>d]"
---

In một bản tóm tắt pipeline gọn cho repo này. **Chỉ đọc** — không mode nào ở đây ghi gì.

## 1. Config

`agentflow.yaml` ở repo root: schema gate `schema: 2`, parse `board.url` → `owner` + `owner_type` + `project_number` (`agentflow-protocol` §1). Owner/repo của issue suy từ `git remote get-url origin`.

## 2. Board pass (dùng chung cho cả 3 mode)

Một lượt `projects_list` method=`list_project_items`, paginate toàn board (`per_page` ≤ 50, `after` cursor, **LUÔN truyền `field_names: ["Status"]`** — thiếu nó Status vắng mặt, đó là read bug). Giữ cho mỗi item: `item_id`, issue number, issue state, assignees, tên option Status, aux label.

## 3. Đếm và in

- Group theo tên option Status (6 hằng số plugin).
- Năm state đầu chỉ đếm issue `state == open`; **`Done` đếm riêng**: mọi item Status `Done` bất kể open/closed.
- Trong `Inbox`, tách riêng số ticket mang aux `blocked` — `/agentflow:start` không tự đụng chúng, nên đó là hàng đợi đang chờ chính bạn.
- Status **trống** → dòng riêng; phân loại bằng `--audit`.
- Issue `state == closed` mà Status ∉ {`Done`} → **dòng riêng, luôn liệt kê issue number**. Không có dòng này thì chúng rơi khỏi mọi con số (năm state đầu lọc `open`) và biến mất. Thường là: bạn merge PR trên github.com nhưng built-in workflow *"Item closed → Done"* chưa bật.

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

Chỉ đếm số lượng — không liệt kê từng card, trừ dòng `blocked` và dòng `closed ≠ Done`.

---

## `--audit` — membership + reconcile + orphan check

`Status` trên board **LÀ** state authoritative, nên không có drift để đối chiếu. Ba lớp bất thường routing không tự thấy:

1. **Membership** (hai chiều, cả hai đều là "ticket vô hình"):
   - `list_issues` (`state: "open"`, không filter label) → issue open **không có trên board** → liệt kê.
   - Từ board pass: item có issue `state == closed` mà Status ∉ {`Done`} → liệt kê. Fix: **kéo card sang `Done`**, rồi bật workflow *"Item closed → Done"* (Project settings → Workflows).
   - Card **draft** (không có issue content) nằm ngoài state machine → liệt kê để người convert qua `/agentflow:task`.
2. **Reconcile:** với mỗi item có issue open, `issue_read` method=`get` → parse `Current state` trong block `<!-- AGENTFLOW-STATE -->`, so với Status (1+K call — chấp nhận cho lệnh chẩn đoán chạy tay).
   - Lệch → liệt kê. **Không cần sửa tay**: pickup kế tiếp tự reconcile (Status thắng).
   - Status **trống** → Missing-Status rule (reference §"Missing Status & membership"): case intake → coi như `Inbox`, bình thường; case ANOMALY → liệt kê, người re-set column.
3. **Orphan** (từ board pass, không cần call thêm). Chỉ đúng khi không có terminal `/agentflow:start` nào đang thật sự chạy ticket đó — bạn tự đối chiếu terminal của mình:
   - **Assigned (Status bất kỳ)** → một terminal claim rồi chết trước khi nhả. Vô hình với queue vì filter loại item có assignee. Fix: **unassign là đủ** — `/agentflow:start` nhặt lại đúng cột nó đang đứng.
   - **Unassigned + Status `In Progress`** → cột duy nhất không nằm trong queue (in-flight guard); một DEV run đã chết giữa chừng. Fix: **kéo card về `Ready for Dev`** — DEV tái dùng branch/PR sẵn có.
   - Unassigned ở `Inbox` / `Ready for Dev` / `In QC` là **bình thường** (đang trong queue). Đừng báo động.

Sạch → in `✓ mọi open issue đều có trên board, không issue closed nào kẹt ngoài Done, body khớp Status, không có ticket mồ côi`. Ngược lại mỗi bất thường một dòng:

```
⚠ #57  open issue không có trên board — vô hình với /agentflow:start: add card (hoặc /agentflow:task #57)
⚠ #53  issue CLOSED nhưng Status "Ready for Review" — kéo card sang Done; bật workflow "Item closed → Done"
⚠ #42  body Current state "In QC" ≠ Status "Inbox" (pickup kế tiếp tự reconcile — Status thắng)
⚠ #48  assigned, Status "In QC" — claim mồ côi: nếu không terminal nào đang chạy → unassign, /agentflow:start tự nhặt lại
⚠ #61  unassigned, Status "In Progress" — DEV run đã chết giữa chừng: kéo card về "Ready for Dev"
```

---

## `--metrics` — flow metrics

**Nguồn:** Projects v2 không có history API (Status change không tạo timeline event), nhưng protocol bắt **mọi transition phải kèm comment có prefix** và GitHub gắn `created_at` chính xác tới giây — nên transition comment **chính là** event log của pipeline, còn Status sống cho biết ticket hiện ở đâu. Không dùng `Event log` trong AGENTFLOW-STATE (độ phân giải theo ngày, prose, bị prune).

1. **Window** — mặc định `--since 30d`; parse `--since <N>d` nếu có.
2. **Board pass** (§2).
3. **Chọn tập ticket đọc comment** (bước tốn call nhất): ticket Status ≠ `Done`, cộng item `Done` có issue `closed_at` trong window. In `N ticket scanned`. Tập > ~60 → cảnh báo số call rồi hỏi có tiếp không.
4. **Comment pass** — `issue_read` method=`get_comments` từng ticket; lấy `created_at` + prefix (bỏ comment không prefix — untrusted, và không phải transition):

   | Prefix | Mốc |
   |---|---|
   | `[SPEC]` **đầu tiên** | `t_start` |
   | `[DEV] Picked up` / `[DEV] Opened PR` | DEV bắt đầu / handoff sang QC |
   | `[QC] ❌` | một lần rework (đếm) |
   | `[QC] ❌ infra:` | **KHÔNG** tính là rework |
   | `[QC] ✅` | `t_qc_pass` |
   | `[SYSTEM] auto-escalated` | một lần escalation (đếm) |
   | `[SYSTEM] merged PR` | `t_done` |
   | `[DEV] ?` / `[QC] ?` | một lần clarification bounce (đếm) |

5. **Tính** (mỗi metric nêu rõ mẫu số):
   - **Throughput** — ticket có `[SYSTEM] merged PR` (fallback: issue `closed_at`) trong window.
   - **Cycle time** — `t_done − t_start`, in **median** + **p90**. Ticket thiếu mốc thì loại và ghi rõ số bị loại.
   - **Time-to-first-PR** — `[DEV] Opened PR` đầu tiên `− t_start`, median.
   - **First-pass yield** — % ticket đạt `[QC] ✅` mà **không** có `[QC] ❌` nào trước đó. Chỉ số chất lượng quan trọng nhất: DEV có làm đúng ngay từ đầu không.
   - **Rework rate** — tổng `[QC] ❌` (loại `infra:`) ÷ số ticket đã qua QC.
   - **Escalation rate** — % ticket có ≥1 `[SYSTEM] auto-escalated`.
   - **Blocked rate** — % ticket từng quay về người (`[DEV] ?`, `[QC] ?`, `[SYSTEM] auto-escalated`). Cao = spec vào pipeline còn mỏng.
   - **WIP** — đếm live theo column cho `Ready for Dev` / `In Progress` / `In QC`.
   - **Aging** — ticket đang park (`Inbox +blocked`, `Ready for Review`): `now − created_at` của comment mới nhất. **Liệt kê từng cái quá 3 ngày** — phần hành động được nhất của cả lệnh.

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
   API, nên đây là reconstruction best-effort — độ phân giải tới mức có comment (agent bỏ sót
   comment → đoạn đó vô hình).
   ```

Không ticket nào đủ dữ liệu → in `chưa đủ dữ liệu trong window — thử /agentflow:status --metrics --since 90d`. Kết hợp được với `--audit` (chạy lần lượt, dùng chung board pass §2).
