# GitHub Projects v2 board — setup, queue, anomalies

> Reference của skill `agentflow-protocol`. Đọc `../SKILL.md` trước.
>
> **Ai cần file này:** `/agentflow:start` (queue + `status_map`), `/agentflow:status` (queue + anomalies),
> và một DEV/QC chạy **standalone** (tự tìm ticket). Setup board thuộc `commands/init.md` Step 6.
> **DEV/QC trong orchestrated run KHÔNG cần đọc file này** — hai shape call chúng dùng
> (`update_project_item`, `get_project_item`) nằm ở `../SKILL.md` §2, và `item_id` đã có sẵn trong
> spawn prompt. Đừng load nó "cho chắc": đó là ~2.5k token trên mỗi lần spawn.

**Quy tắc nền:** `Status` field trên board **LÀ** state authoritative. Không mirror, không bản sao thứ
hai — label không mang state. Mọi actor đọc và ghi state qua đúng các tool `projects_*` dưới đây.
Status write fail là **pipeline dừng có chủ đích** (fail-stop).

## Projects v2 được điều khiển thế nào

Hoàn toàn qua **`projects` toolset của `github` MCP server chính thức** — KHÔNG `gh api graphql`,
KHÔNG `PVT_` node id (ngoại lệ duy nhất: setup board ở init, xem carve-out cuối mục này). Ba tool:

1. **`projects_get`** — read đơn lẻ (`get_project` / `get_project_item` / `get_project_field`)
2. **`projects_list`** — read dạng list (`list_project_fields` / `list_project_items`)
3. **`projects_write`** — write (`create_project` / `add_project_item` / `update_project_item` / `delete_project_item`)

Chúng key theo **owner + owner_type + project number** — cả ba parse từ `board.url` trong
`agentflow.yaml` (`../SKILL.md` §1). Board có thể thuộc owner khác repo, nên **đừng** suy owner của
board từ `git remote`. **Không bao giờ hardcode node id.** Bất đối xứng quan trọng giữa read và write:

- **WRITE** (`update_project_item`) resolve item theo (`item_owner` + `item_repo` + `issue_number`)
  và field + option **by name** — tất cả server-side, không cần discover id nào.
- **READ đơn lẻ** (`get_project_item`) cần **`item_id` numeric** — KHÔNG resolve theo issue number.
  `item_id` đến từ mỗi row của `list_project_items` (orchestrator pass xuống spawn prompt của
  sub-agent); fallback khi không có: một lượt `list_project_items` + match `content.number`.

Một carve-out duy nhất, **chỉ ở `/agentflow:init`**: setup board — `Status` field và các option của
nó, link board↔repo, short description, view layout. Runtime (transition / queue / verify) thì 100%
MCP. Xem `commands/init.md` Step 6 cho mutation cụ thể.

> **Ranh giới:** carve-out chỉ sống trong `commands/init.md` — setup, one-shot, có consent, và `gh` vắng thì
> fallback UI thủ công chứ không bao giờ fail init. **Board item write không có ngoại lệ nào**, ở init lẫn runtime.
> Thấy `gh api graphql` ở `agents/*.md` hoặc trong `SKILL.md` là bug, không phải tiền lệ. Lý do mở: `DESIGN-NOTES.md`.

`projects` và `labels` là toolset **opt-in**: `github` MCP server phải chạy với header
`X-MCP-Toolsets: context,issues,pull_requests,users,labels,projects` trong `.mcp.json` (mặc định
KHÔNG bật hai cái này). Thiếu → các tool `projects_*` không tồn tại và **toàn bộ state machine chết**,
không có fallback. Cùng triệu chứng, nguyên nhân thứ hai: classic PAT thiếu scope `project` thì server
ẩn `projects_write` (`../SKILL.md` §1) — kiểm cả hai trước khi kết luận.

## Resolve board

```
projects_get method=get_project
  owner / owner_type / project_number: parse từ `board.url` (`../SKILL.md` §1)
```

Không resolve được → dừng và báo user. Không board là không có state machine.

## Tạo / link board

**Canonical home DUY NHẤT: `commands/init.md` Step 6** — resolve owner canonical, tạo project, set 6 option
`Status` (tên là wire value load-bearing), link board↔repo, description, view layout, và ba built-in workflow.
One-shot ở init; **runtime không bao giờ chạm nó**. Đừng chép thủ tục đó về đây — một bản sao là một chỗ để drift.

Một hệ quả runtime: **card nằm ở option ngoài 6 tên hằng số là card ngoài state machine.** Thừa option
(vd `Todo` sót lại) → **rename** thành tên còn thiếu, đừng xoá: rename giữ card, xoá mất card.

## Status transition + đọc Status của một item

Hai shape call này là **runtime path của mọi agent**, nên chúng sống ở `../SKILL.md` §2 (*Transition =
một Status write*) — nơi DEV/QC đọc mà không phải load file này. **Đừng chép lại chúng ở đây**: một
shape sai ở một trong hai bản sao là pipeline dừng, và bản sao thứ hai chính là cách nó lệch.

Một hệ quả chỉ liên quan tới chỗ **tạo ticket mới** (`/agentflow:task`, `/agentflow:init` smoke test):
vì Status change không để lại timeline event, `add_project_item` **phải** đi kèm một Status write
explicit ngay sau đó — không bao giờ dựa vào built-in workflow để set giá trị đầu tiên.

## List board items (queue)

Orchestrator đọc **toàn bộ** board một lượt để build inbox queue. Paginate (`per_page` ≤ 50, `after`
cursor) và lấy cho mỗi item: `item_id`, issue `number`, issue `state`, `assignees`, `labels`, và tên
option `Status`.

```
projects_list method=list_project_items
  owner / owner_type / project_number: từ `board.url`
  per_page: 50
  after: <endCursor|null>
  field_names: ["Status"]
# loop khi còn trang tiếp theo
```

> `field_names` được resolve server-side sang field id — không cần `list_project_fields`. Nó **loại
> trừ** `fields` (chỉ nhận numeric id): truyền một cái, không bao giờ cả hai.
>
> **CRITICAL — luôn truyền `field_names`:** thiếu nó, mỗi item chỉ trả title và Status **vắng mặt**
> (read bug), không phân biệt được với Status trống thật — một state có nghĩa (xem Missing Status).
>
> Có param `query` (cú pháp filter bar của Projects: `status:"In QC"`, `is:open`, `no:status`) — được
> dùng như **optimization** để giảm số trang, với caveat: option đổi tên làm filter **silently trả
> rỗng** (khác với write by-name hard-error). Baseline canonical vẫn là full paginate + filter
> client-side; nếu dùng `query`, coi "kết quả rỗng bất thường" là tín hiệu phải fallback.

Filter claim ở client-side: issue `state == open` **và** không có assignee **và** không mang aux
`blocked` **và** Status ∈ {`Inbox`, `Ready for Dev`, `In QC`} (ba cột agent-actionable). `In Progress`
bị loại — đó là in-flight guard, không phải việc chờ nhặt. Thứ tự drain: `In QC` → `Ready for Dev` →
`Inbox` (việc đã bắt đầu trước việc mới, giữ WIP thấp). Card **draft** (không có issue
number/content) nằm ngoài state machine — surface cho người convert thành issue qua `/agentflow:task`.

## Missing Status & membership (trạng thái bất thường)

1. **Item trên board, Status trống, body KHÔNG có `AGENTFLOW-STATE`** → intake mới (người tự add
   card, workflow "Item added" chưa bật) → coi như `Inbox`; spec pass ghi Status=`Inbox` explicit
   khi bắt đầu.
2. **Item trên board, Status trống, body CÓ `AGENTFLOW-STATE` với `Current state` ≠ Inbox** →
   **ANOMALY** (option bị xoá / state bị mất): KHÔNG BAO GIỜ default về Inbox — post
   `[SYSTEM] status lost (body says "<Current state>") — human please re-set the column`, skip
   ticket, surface cho người. Đây là lý do body `Current state` vẫn load-bearing: nó là bằng chứng
   phục hồi duy nhất.
3. **Issue OPEN nhưng không có trên board** → vô hình với routing. `/agentflow:status --audit` chạy membership
   check (list open issues, đối chiếu board items) để phát hiện — người add card, hoặc `/agentflow:task #<n>`
   để đưa nó vào state machine.
4. **Issue CLOSED nhưng Status ∉ {`Done`}** → **lane thoát bị bỏ lỡ**, và là ca thường gặp nhất trong
   ba ca ở đây. Người review PR trên github.com rồi bấm Merge (thay vì gõ `merge #<n>` trong session)
   → PR có `Closes #<n>` nên issue tự close, nhưng Status **chỉ** về `Done` nếu built-in workflow
   *"Item closed"* đã bật — mà đó là bước UI **không verify được**. Chưa bật ⇒ card nằm mãi ở
   `Ready for Review` với issue đã đóng. Ticket đó vô hình cả hai đường: nó không nằm trong queue của
   `/agentflow:start` (cột người sở hữu), và `/agentflow:status` chỉ đếm issue OPEN cho năm state đầu
   nên nó **không hiện ở dòng nào**. `--audit` bắt ca này; fix là **kéo card sang `Done`** (hoặc bật
   workflow rồi close/reopen một lần).

## Canonical status_map (routing table)

`/agentflow:start` dùng bảng này làm routing table duy nhất — đọc ở đây, đừng hardcode bảng khác. Cột `owner`
suy từ bảng Ownership ở `../SKILL.md` §2 (canonical); ở đây chỉ thêm `action`.

```yaml
status_map:
  Inbox:            { owner: session, action: "spec pass (công thức: commands/task.md §Spec pass — interactive khi gọi từ /agentflow:task, autonomous khi /agentflow:start nhặt trong polling loop): shape/re-shape + gate DoR; pass → Ready for Dev, cần quyết định của người → ở lại Inbox +blocked" }
  Ready for Dev:    { owner: dev,     action: "có open PR link tới issue → amend nó (tái dùng branch); không thì implement trên branch mới + mở PR. Có aux `rework` → đọc QC rejection mới nhất TRƯỚC. Body thiếu `## For DEV` + AC đánh số → DoR defense: về Inbox +blocked" }
  In Progress:      { owner: dev,     action: "đang code (claim đang giữ) — KHÔNG re-spawnable; không đi tiếp được thì DEV tự đưa về Inbox +blocked" }
  In QC:            { owner: qc,      action: "author test + chạy tier; ✅ → Ready for Review · ❌ → +rework, Ready for Dev (consecutive_fail ≤ 2) · else escalate → Inbox +blocked" }
  Ready for Review: { owner: human,   action: "người review/merge (QC ✅, merge-ready); muốn sửa → để feedback trên PR rồi KÉO CARD về Inbox (agent không bao giờ tự làm)" }
  Done:             { owner: human,   action: "terminal" }
```

> **`Ready for Review` là break-out state; `Inbox +blocked` cũng vậy** — orchestrator không route
> chúng đi tiếp và **unassign** ticket ở cả hai. `Inbox` **không có** `blocked` thì orchestrator xử
> lý được ngay trong turn (spec pass tương tác). Rework loop và ngưỡng escalate: `../SKILL.md` §9.

## Lane của con người & claim

Bản đầy đủ của `../SKILL.md` §10 — phần dưới đây là những bước **orchestrator** phải thực hiện; DEV/QC
chỉ cần bảng tóm tắt ở SKILL.

### PR-feedback re-entry (Ready for Review → Inbox)

1. Người để **feedback inline trực tiếp trên code của PR**, rồi **kéo card về `Inbox`** (ticket đã
   unassign lúc break-out nên chỉ cần kéo). **Agent/session KHÔNG bao giờ tự làm bước chuyển này.**
2. Ticket re-enter unassigned-inbox queue như một ticket Inbox bình thường.
3. Spec pass ở `Inbox` (`commands/task.md` §Spec pass, đường C) — trigger là **sự tồn tại của một open PR link
   tới issue**, KHÔNG dựa vào `Current state`. Đọc feedback trên PR, lọc theo PR-feedback rule
   (`../SKILL.md` §11), fold vào Context/AC/Out of Scope + cập nhật `## For DEV` để DEV **amend chính
   PR đó**, reset `consecutive_fail` về 0, rồi re-gate DoR.
4. DEV amend PR sẵn có, QC re-gate, ticket quay lại `Ready for Review`. **Không bao giờ auto-merge.**

### Human drag — parked state được sanction

- `Ready for Review` → `Inbox`: PR-feedback re-entry ở trên.
- Close issue / merge PR → `Done`. Người merge PR trên github.com mà built-in workflow *"Item closed"*
  chưa bật thì phải kéo tay — `/agentflow:status` in ca này ở dòng `closed ≠ Done` (§Missing Status ca 4).
- Ticket `Inbox +blocked`: người sửa body/AC tay rồi để nguyên — spec pass kế tiếp tự normalize.
- Kéo card khi ticket đang `In Progress` / `In QC` **không an toàn**: compare-then-write bắt được phần
  lớn nhưng vẫn còn cửa sổ clobber. Muốn dừng một run đang chạy → dừng terminal, đừng kéo card.
- Kéo `Inbox` → `Ready for Dev` là **unsanctioned**; DoR defense của DEV đứng chắn.

### Claim & nhiều terminal song song

Thủ tục đầy đủ (self-assign, confirm, nhả claim, race window, shared identity) sống ở **`commands/start.md`** —
orchestrator là actor duy nhất thực thi nó. Ở đây chỉ cần biết: claim là GitHub **assignee**, queue lọc bỏ item đã
có assignee, và ticket còn assignee mà không terminal nào chạy là **ticket mồ côi** — `/agentflow:status --audit`
phát hiện.

## Scopes

Board bắt buộc và mang state authoritative, nên `project` scope luôn cần — `/agentflow:start` dừng lúc boot nếu
thiếu.

- Org board: `GITHUB_TOKEN` cần `project` **và** `read:org`.
- User board: `GITHUB_TOKEN` cần `project`.
- Read-only (list queue / fields) tối thiểu `read:project`; mọi transition + create-board cần
  `project`. **Khuyến nghị classic PAT** — fine-grained PAT chưa được verify cho user-owned board.
