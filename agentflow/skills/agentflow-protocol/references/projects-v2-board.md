# GitHub Projects v2 board — setup, queue, anomalies

> Reference của skill `agentflow-protocol`. Đọc `../SKILL.md` trước.
>
> **Ai cần file này:** `/agentflow:init` (tạo/link board), `/agentflow:start` (queue + `status_map`),
> `/agentflow:status` (queue + anomalies), và một DEV/QC chạy **standalone** (tự tìm ticket).
> **DEV/QC trong orchestrated run KHÔNG cần đọc file này** — hai shape call chúng dùng
> (`update_project_item`, `get_project_item`) nằm ở `../SKILL.md` §2, và `item_id` đã có sẵn trong
> spawn prompt. Đừng load nó "cho chắc": đó là ~2.5k token trên mỗi lần spawn.

**Quy tắc nền:** `Status` field trên board **LÀ** state authoritative. Không mirror, không bản sao thứ
hai — label không mang state. Mọi actor đọc và ghi state qua đúng các tool `projects_*` dưới đây.
Status write fail là **pipeline dừng có chủ đích** (fail-stop).

## Projects v2 được điều khiển thế nào

Hoàn toàn qua **`projects` toolset của `github` MCP server chính thức** — KHÔNG `gh api graphql`,
KHÔNG `PVT_` node id. Ba tool:

1. **`projects_get`** — read đơn lẻ (`get_project` / `get_project_item` / `get_project_field`)
2. **`projects_list`** — read dạng list (`list_project_fields` / `list_project_items`)
3. **`projects_write`** — write (`create_project` / `add_project_item` / `update_project_item` / `delete_project_item`)

Chúng key theo **owner + owner_type + project number** (owner suy từ `git remote`, `owner_type` từ
`board.owner_type` trong `agentflow.yaml`). **Không bao giờ hardcode node id.** Bất đối xứng quan
trọng giữa read và write:

- **WRITE** (`update_project_item`) resolve item theo (`item_owner` + `item_repo` + `issue_number`)
  và field + option **by name** — tất cả server-side, không cần discover id nào.
- **READ đơn lẻ** (`get_project_item`) cần **`item_id` numeric** — KHÔNG resolve theo issue number.
  `item_id` đến từ mỗi row của `list_project_items` (orchestrator pass xuống spawn prompt của
  sub-agent); fallback khi không có: một lượt `list_project_items` + match `content.number`.

Một carve-out thủ công duy nhất: **tạo/sửa single-select `Status` field và các option của nó** — bước
UI một lần lúc init. Runtime (transition / queue / verify) thì 100% MCP.

> **Lý do chính xác, để không ai "sửa" nó sai đường.** GraphQL API *có* làm được
> (`createProjectV2Field` / `updateProjectV2Field` nhận `singleSelectOptions: [{name, color,
> description}]`), nhưng `projects_write` không expose method tương ứng. `gh api graphql` **về mặt kỹ
> thuật chạy được** — `GITHUB_TOKEN` nằm trong env của session nên `gh` tự nhận đúng identity đó — và
> chính vì vậy carve-out này phải được giữ **bằng chủ ý, không phải vì bất khả thi**: mở đường CLI cho
> một bước là mở một API surface thứ hai chạy song song với MCP, với tập lỗi và tập quyền riêng. Muốn
> tự động hoá bước này thì làm nó **chỉ ở init**, có consent tường minh; đó là một design change, không
> phải một cải tiến lặng lẽ. Runtime (transition / queue / verify) thì **không có ngoại lệ nào**.

`projects` và `labels` là toolset **opt-in**: `github` MCP server phải chạy với header
`X-MCP-Toolsets: context,issues,pull_requests,users,labels,projects` trong `.mcp.json` (mặc định
KHÔNG bật hai cái này). Thiếu → các tool `projects_*` không tồn tại và **toàn bộ state machine chết**,
không có fallback.

## Resolve board

```
projects_get method=get_project
  owner: <OWNER từ git remote>
  owner_type: <board.owner_type>
  project_number: <board.number>
```

Không resolve được → dừng và báo user. Không board là không có state machine.

## Tạo board (dùng bởi /agentflow:init)

1. **Tạo project rỗng (chỉ title) qua MCP:**

```
projects_write method=create_project
  owner: <OWNER>   owner_type: <org|user>   title: <tên repo>
```

Lưu **number** trả về vào `board.number`.

2. **Status field 6 option — CARVE-OUT thủ công.** Project mới đi kèm `Status` mặc định
   `Todo / In Progress / Done`. AgentFlow cần **đúng sáu** option, đúng tên, đúng thứ tự:

   `Inbox` · `Ready for Dev` · `In Progress` · `In QC` · `Ready for Review` · `Done`

   Hướng dẫn user mở board trong GitHub Projects UI → sửa field `Status` cho khớp. Các tên này là
   **wire value load-bearing** (resolve by-name). **Bảng copy-paste canonical (tên + color +
   description mỗi option) nằm ở `commands/init.md` Step 6** — dùng đúng bảng đó, đừng soạn lại; agent
   không đọc description, nhưng người trong team thì có, và đó là thứ giữ họ khỏi kéo card vào cột
   agent đang giữ. Rồi validate:

```
projects_list method=list_project_fields
  owner: <OWNER>   owner_type: <org|user>   project_number: <board.number>
```

   Assert `Status` (single-select) có đủ 6 option đúng tên; thiếu → liệt kê tên còn thiếu, yêu cầu
   user thêm trong UI, validate lại. **Thừa option** (vd `Todo` sót lại) → bảo user xoá, nếu không
   card có thể rơi vào một state ngoài state machine.

3. **Built-in workflows — thủ công-UI (không API nào config được).** Project settings → Workflows:
   - **Item added to project** → Status: `Inbox`
   - **Item reopened** → Status: `Inbox`
   - **Item closed** → Status: `Done`

   Đây là automation miễn phí phủ các cạnh mà agent không chứng kiến (người tự add card, tự
   close/reopen issue). Race với agent write vô hại vì intake cũng ghi cùng value `Inbox`
   (same-value). Nhưng **không verify được workflow đã bật hay chưa**, nên `/agentflow:task` vẫn ghi
   Status=`Inbox` explicit — không bao giờ dựa vào workflow.

## Link board có sẵn

Validate, không mutate dữ liệu của user: resolve theo number → đọc `Status` field qua
`list_project_fields` → xác nhận đủ 6 option → thiếu thì **KHÔNG âm thầm ghi đè**, liệt kê và hướng
dẫn user thêm trong UI → hướng dẫn bật built-in workflows như trên.

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
  owner: <OWNER>   owner_type: <org|user>   project_number: <board.number>
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

`/agentflow:start` dùng bảng này làm routing table duy nhất — đọc ở đây, đừng hardcode bảng khác. Sáu tên
column là hằng số plugin (`../SKILL.md` §1).

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

Claim là GitHub **assignee** (sống trên issue, không phụ thuộc board):

- `/agentflow:start` scan ticket **OPEN + unassigned + không mang `blocked` + Status ∈ {`Inbox`,
  `Ready for Dev`, `In QC`}**, rồi self-assign ngay (`get_me` một lần/session lấy login; `issue_write`
  với `assignees = current ∪ {my_login}` — full-set nên phải đọc current trước), rồi **đọc lại** để xác
  nhận Status chưa đổi và ticket giờ đã assign cho mình. Race window đẩy nó đi rồi → skip, lấy ticket
  kế tiếp.
- **Assignee phải được nhả mỗi khi orchestrator dừng**: tới `Done`, break out ở `Ready for Review` /
  `Inbox +blocked`, hoặc chạm safety cap giữa chừng. Ticket còn assignee mà không terminal nào chạy là
  **ticket mồ côi** — vô hình với queue cho tới khi `/agentflow:status --audit` phát hiện.
- **Shared identity:** mọi terminal mở trên **cùng một clone** dùng chung `GITHUB_TOKEN` nên assignee
  de-dupe được nhưng không phân biệt được terminal nào; tranh chấp CHỈ tồn tại ở bước claim. Biến sống
  theo repo (`env` của `.claude/settings.local.json`), nên muốn tách identity thì **clone thêm một bản
  và đặt token khác** — không cần máy/user profile riêng. **Đừng thêm distributed lock.**

## Scopes

Board bắt buộc và mang state authoritative, nên `project` scope luôn cần — `/agentflow:start` dừng lúc boot nếu
thiếu.

- Org board: `GITHUB_TOKEN` cần `project` **và** `read:org`.
- User board: `GITHUB_TOKEN` cần `project`.
- Read-only (list queue / fields) tối thiểu `read:project`; mọi transition + create-board cần
  `project`. **Khuyến nghị classic PAT** — fine-grained PAT chưa được verify cho user-owned board.
