---
description: Hiển thị tổng quan pipeline AgentFlow của repo này — số board item theo từng Status column. Kèm `--audit` để chạy membership check (open issue không có trên board), reconcile check (body Current state lệch Status) và visibility/orphan check (ticket /start không thấy — kể cả assigned mồ côi sau crash).
argument-hint: "[--audit]"
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
   - **Assigned + Status ∈ {Ready for Dev, In Progress, In QC}** → **nghi orphan sau crash** — liệt
     kê; hướng dẫn phục hồi: unassign + kéo card về Inbox — PMO re-triage resume từ AGENTFLOW-STATE
     + open PR sẵn có (re-entry lane chuẩn), DEV sẽ amend chứ không build lại.
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
   `⚠ #48  assigned, Status "In Progress" — nếu không có terminal /start nào đang chạy: nghi orphan sau crash — unassign + kéo card về Inbox`,
   `⚠ #29  assigned, Status "Inbox" — nghi crash sau claim: /start chỉ pick Inbox unassigned — unassign là đủ (không cần kéo card)`,
   `⚠ #52  assigned, Status "Refined" — nghi crash trước unassign lúc break-out: unassign trước, rồi kéo về Inbox nếu muốn resume`.
