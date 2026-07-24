---
description: Hiển thị tổng quan pipeline AgentFlow của repo này — số board item theo từng Status column. Kèm `--audit` để chạy membership check (open issue không có trên board), reconcile check (body Current state lệch Status) và visibility/orphan check (ticket /start không thấy — kể cả assigned mồ côi sau crash). Kèm `--metrics` để tính flow metrics (throughput, cycle time, rework rate, escalation rate, DoR bounce, aging/WIP) suy ra từ các transition comment + Status trên board.
argument-hint: "[--audit] [--metrics] [--since <N>d]"
---

In ra một bản tóm tắt pipeline ngắn gọn cho repo này.

1. Đọc `.claude/agentflow.yaml` để lấy `project.name`, `project.summary`, `project.repo`, `connections.github_project` (`owner`, `owner_type`) và `board.number` / `board.columns`. In dòng đầu output: `<project.name> — <project.summary>` (yaml đã có trong tay — không cần call nào thêm).
2. Đếm qua **một** lượt `projects_list` method=`list_project_items`, paginate toàn board (`per_page` ≤50, `after` để paginate, LUÔN truyền **`field_names: ["Status"]`** — caveat: reference §"List actionable board items"):

   - Params: `owner`/`owner_type` (từ `connections.github_project`), `project_number` (= `board.number`).
   - Group theo tên option Status, map về `board.columns.<key>`. Sáu state đầu chỉ đếm item có issue `state == open`; **Done đếm riêng**: mọi item Status "Done" bất kể issue open/closed (ticket Done thường đã close).
   - Item có Status **trống** → đếm vào dòng `(Status trống)` riêng — phân loại nó bằng `--audit` (Missing-Status rule — reference §"Missing Status & membership").
3. In ra:

   ```
   <project.name> — <project.summary>
   PROJECT: <repo>

   Inbox                   <n>
   Ready for Dev           <n>
   In Progress             <n>
   In QC                   <n>
   Refined (needs human)   <n>
   Ready for Human Review  <n>
   Done                    <n>
   (Status trống)          <n>      # chỉ in khi > 0
   ```

Chỉ đếm số lượng — không liệt kê từng card.

---

## `--audit` — membership + reconcile + visibility check

**`Status` field trên board LÀ state authoritative** — không có bản copy thứ hai của state, nên
không có gì để "đối chiếu drift". Nhưng còn ba lớp bất thường mà routing không tự thấy: (1) issue
OPEN nhưng **không có trên board** → vô hình với routing (orchestrator chỉ đọc board để lấy queue);
(2) `Current state` trong AGENTFLOW-STATE body **lệch Status** (một transition hoàn thành nửa chừng,
hoặc con người vừa kéo card); (3) ticket unassigned đứng ở một state agent-owned ngoài Inbox mà
`/start` không scan tới (khả năng human kéo tắt), hoặc ticket **assigned mồ côi sau crash** — kể cả
ở Inbox / Refined / Ready for Human Review, vì `/start` chỉ pick ticket Inbox **unassigned**.
`--audit` phát hiện và liệt kê tất cả — chỉ đọc, không sửa gì.

1. **Board:** một `projects_list` method=`list_project_items` như trên (paginate, `field_names:
   ["Status"]`), giữ lại cho mỗi item: issue number, issue state, assignees (từ `content` của item),
   tên option Status. Một card **draft** (không có issue number/content) nằm ngoài state machine —
   liệt kê để human convert thành issue qua `/task`.
2. **Membership check:** `list_issues` với `owner`/`repo` (parse từ `project.repo` dạng
   `owner/repo`), `state: "open"` — KHÔNG filter label nào. Đối chiếu issue number với board items:
   issue open nào không có trên board → liệt kê.
3. **Reconcile check:** với mỗi board item có issue open, `issue_read` method=`get` lấy body, parse
   `Current state` trong block `<!-- AGENTFLOW-STATE v2 -->` (1+K call — chấp nhận được cho một lệnh
   chẩn đoán chạy tay). So với Status:
   - **Lệch** → liệt kê. Không cần sửa tay: agent pickup tiếp theo tự reconcile — **Status thắng**,
     viết lại `Current state` cho khớp Status (xem `project-board-protocol/SKILL.md` §"State section:
     upsert & reconcile").
   - Status **trống** → áp Missing-Status rule (reference §"Missing Status & membership"): case intake
     → coi như "Inbox" (bình thường, không phải lỗi); case ANOMALY → liệt kê — KHÔNG default về Inbox,
     human re-set đúng column trên board.
4. **Visibility / orphan check** (từ data step 1, không cần call thêm): xét mỗi board item có issue
   open theo cặp (assignee, Status). Các case "nghi orphan/crash" bên dưới chỉ áp khi không có
   terminal `/start` nào đang chạy (audit không tự kiểm được — human tự đối chiếu các terminal của
   mình):
   - **Unassigned + Status ∈ {Ready for Dev, In Progress, In QC}** — các state agent-owned mà
     `/start` không scan (orchestrator chỉ scan Inbox) → **vô hình với `/start`** (khả năng human
     kéo tắt hoặc state lệch) — liệt kê; hướng dẫn: kéo card về Inbox để re-enter pipeline (PMO gate
     DoR rồi tự chuyển).
   - **Assigned + Status ∈ {Ready for Dev, In Progress, In QC}** → **ticket đang dở, KHÔNG tự resume
     được** — liệt kê. Lưu ý: đây **không chỉ** là dấu hiệu crash. Case này sinh ra ở cả các đường
     **bình thường**: `/start` chạm safety cap 8-call, user turn kết thúc giữa pipeline, hoặc DEV
     `[DEV] Blocked` (giữ Status "In Progress" có chủ đích). Ở mọi case, `/start` sẽ **không bao giờ**
     nhặt lại nó vì loop chỉ scan `Inbox + unassigned`. Hướng dẫn phục hồi (giống nhau cho cả bốn
     nguyên nhân): **unassign + kéo card về Inbox** — PMO re-triage resume từ AGENTFLOW-STATE + open
     PR sẵn có (re-entry lane chuẩn), DEV sẽ amend chứ không build lại. Trước khi phục hồi, xác nhận
     không có terminal `/start` nào đang thật sự chạy ticket đó.
   - **Assigned + Status "Inbox"** → **nghi crash ngay sau claim** — `/start` filter unassigned nên
     bỏ qua ticket này vĩnh viễn — liệt kê; fix: **unassign là đủ** (card đã ở Inbox, không cần kéo),
     ticket re-enter unassigned-inbox queue.
   - **Assigned + Status ∈ {Refined, Ready for Human Review}** → **nghi crash trước bước unassign
     lúc break-out** (orchestrator unassign ở hai state này khi break out) — liệt kê; fix:
     **unassign trước**, rồi kéo card về Inbox nếu muốn resume.
5. In:

   ```
   PROJECT: <repo>

   ✓ mọi open issue đều có trên board, body khớp Status
   ```

   Có bất thường thì liệt kê từng dòng: `⚠ #57  open issue không có trên board — vô hình với /start: add card (hoặc /task với issue sẵn có) để đưa vào state machine`,
   `⚠ #42  body Current state "In QC" ≠ Status "Inbox" (agent pickup sẽ tự reconcile — Status wins)`,
   `⚠ #61  Status trống, body Current state "In QC" — ANOMALY: human re-set column`,
   `⚠ #33  unassigned, Status "Ready for Dev" — vô hình với /start (khả năng human kéo tắt hoặc state lệch): kéo card về Inbox để re-enter pipeline`,
   `⚠ #48  assigned, Status "In Progress" — ticket đang dở (cap/turn-end/blocked/crash), /start không tự nhặt lại: nếu không có terminal nào đang chạy → unassign + kéo card về Inbox`,
   `⚠ #29  assigned, Status "Inbox" — nghi crash sau claim: /start chỉ pick Inbox unassigned — unassign là đủ (không cần kéo card)`,
   `⚠ #52  assigned, Status "Refined" — nghi crash trước unassign lúc break-out: unassign trước, rồi kéo về Inbox nếu muốn resume`.

---

## `--metrics` — flow metrics (throughput, cycle time, rework, escalation, aging)

**Nguồn dữ liệu, và vì sao là nó.** Projects v2 **không có history API** — Status change không tạo
timeline event — nên không thể đọc ngược "ticket nằm ở column nào lúc nào" từ board. Nhưng protocol
đã bắt **mọi transition phải kèm một comment có prefix** (skill: `project-board-protocol` — "transition
không có comment là transition mất audit trail"), và GitHub gắn `created_at` chính xác tới giây cho
từng comment. Vậy **các transition comment CHÍNH LÀ event log của pipeline**, và Status sống trên board
cho biết hiện tại ticket đang ở đâu.

> Dùng comment, **không** dùng `Event log` trong `AGENTFLOW-STATE`: event log chỉ có độ phân giải theo
> ngày, do agent tự soạn bằng prose nên format có thể trôi, và bị prune. Comment thì immutable,
> timestamped, và prefix là discriminator đã chuẩn hoá.

**Giới hạn phải nói thẳng khi in kết quả** (đừng hứa con số chính xác hơn thực tế):
- Độ phân giải chỉ tới mức **có comment** — nếu một agent bỏ sót comment, đoạn đó vô hình.
- Ticket tạo **trước** khi bật metrics vẫn tính được, vì comment là lịch sử có sẵn — nhưng ticket đã
  bị xoá comment thì mất.
- Đây là **reconstruction best-effort**, không phải per-status timing chính xác.

### Quy trình

1. **Window.** Mặc định `--since 30d`. Parse `--since <N>d` nếu user truyền.
2. **Board pass** — một lượt `projects_list` method=`list_project_items` như phần đầu (paginate,
   `field_names: ["Status"]`). Giữ cho mỗi item: issue number, state, Status hiện tại, assignees.
3. **Chọn tập ticket cần đọc comment (giới hạn chi phí — đây là bước tốn call nhất).** CHỈ đọc
   comment của ticket **liên quan tới window**: mọi item có Status ≠ `Done`, cộng các item `Done`
   mà issue `closed_at` nằm trong window. Bỏ qua phần còn lại. In rõ `N ticket scanned` để user biết
   phạm vi. Nếu tập này > ~60 ticket, cảnh báo một dòng về số call rồi hỏi có tiếp không.
4. **Comment pass** — với mỗi ticket đã chọn: `issue_read` method=`get_comments`. Với mỗi comment lấy
   `created_at` + prefix. Phân loại theo prefix (bỏ qua comment không prefix — untrusted, và không
   phải transition):

   | Prefix quan sát được | Ý nghĩa mốc thời gian |
   |---|---|
   | `[PMO]` **đầu tiên** | ticket bắt đầu được refine — mốc `t_start` |
   | `[DEV] Picked up` / `[DEV] Opened PR` | DEV bắt đầu / handoff sang QC |
   | `[QC] ❌` | một lần rework (đếm) |
   | `[QC] ❌ infra:` | **KHÔNG** tính là rework (lỗi môi trường — qc.md step 4) |
   | `[QC] ✅` | pass — mốc `t_qc_pass` |
   | `[SYSTEM] auto-escalated` | một lần escalation lên human (đếm) |
   | `[SYSTEM] merged PR` | mốc `t_done` |
   | `[DEV→PMO ?]` / `[QC→PMO ?]` | một lần clarification bounce (đếm) |

5. **Tính** (mỗi metric nêu rõ mẫu số):

   - **Throughput** — số ticket có `[SYSTEM] merged PR` (fallback: issue `closed_at`) trong window.
   - **Cycle time** — `t_done − t_start` cho từng ticket Done trong window; in **median** và **p90**
     (median chống outlier tốt hơn mean cho mẫu nhỏ). Ticket không đủ hai mốc thì loại và ghi rõ số bị loại.
   - **Time-to-first-PR** — `[DEV] Opened PR` đầu tiên `− t_start`, median.
   - **Rework rate** — tổng `[QC] ❌` (không tính `infra:`) ÷ số ticket đã đi qua QC; kèm
     **first-pass yield** = % ticket đạt `[QC] ✅` mà **không** có `[QC] ❌` nào trước đó. Đây là
     chỉ số chất lượng quan trọng nhất — nó đo DEV có làm đúng ngay từ đầu không.
   - **Escalation rate** — % ticket có ≥1 `[SYSTEM] auto-escalated`.
   - **DoR bounce rate** — % ticket từng rơi vào `Refined` (suy từ `[PMO]` mang câu hỏi đánh số,
     `[DEV→PMO ?]`, `[QC→PMO ?]`, hoặc `[SYSTEM] auto-escalated`). Cao = spec vào pipeline còn mỏng.
   - **WIP hiện tại** — đếm live theo column cho `Ready for Dev` / `In Progress` / `In QC`.
   - **Aging** — với ticket đang **park** (`Refined`, `Ready for Human Review`), tính `now − created_at`
     của comment mới nhất. **Liệt kê từng cái quá 3 ngày** — đây là phần hành động được nhất của
     cả lệnh: nó chỉ đúng ticket đang chặn dòng chảy.

6. **In:**

   ```
   <project.name> — <project.summary>
   PROJECT: <repo>   window: last <N>d   scanned: <K> tickets

   FLOW
     Throughput (merged)        <n>
     Cycle time  median / p90   <Xd Yh> / <Xd Yh>      (<m> ticket đủ mốc, <e> bị loại)
     Time to first PR (median)  <Xh>

   QUALITY
     First-pass yield           <n>%   (<a>/<b> ticket qua QC không lần ❌ nào)
     Rework rate                <x.x> ❌/ticket        (infra failures không tính)
     Escalation rate            <n>%   (<a>/<b>)
     DoR bounce rate            <n>%   (<a>/<b>)

   WIP  (live)
     Ready for Dev <n> · In Progress <n> · In QC <n>

   AGING  (đang chờ người > 3d)
     #42  Ready for Human Review  6d   PR #57 chờ merge
     #38  Refined                 4d   chờ trả lời [PMO] về scope export

   Nguồn: transition comment (timestamp GitHub) + Status trên board. Projects v2 không có history
   API, nên đây là reconstruction best-effort — độ phân giải tới mức có comment.
   ```

Không có ticket nào đủ dữ liệu → in `chưa đủ dữ liệu trong window — thử /status --metrics --since 90d`.
`--metrics` **chỉ đọc**, không sửa gì; có thể kết hợp với `--audit` (chạy lần lượt, dùng chung lượt
board pass ở bước 2).
