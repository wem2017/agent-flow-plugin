# GitHub Projects v2 board (authoritative state store + orchestrator queue)

> Tài liệu tham khảo cho skill `project-board-protocol`. Đọc `../SKILL.md` trước — file này chứa phần
> board mechanics nặng, được tách ra để protocol chính gọn nhẹ.

**Quy tắc nền tảng:** **`Status` field trên board LÀ state authoritative** cho routing. Không có
mirror, không có bản copy thứ hai — label không mang state (chỉ classification: `type/*`,
`component/*`, aux `rework`). Mọi agent (PMO/DEV/QC lẫn orchestrator) đọc và ghi state qua đúng các
tool `projects_*` mô tả dưới đây. Một Status write fail là **pipeline dừng có chủ đích** (fail-stop),
không phải desync — không còn khái niệm "best-effort".

## How Projects v2 is driven

Projects v2 được điều khiển **hoàn toàn qua `projects` toolset của `github` MCP server chính thức** — KHÔNG
dùng `gh api graphql`, KHÔNG dùng `PVT_` GraphQL node id. Ba tool:

1. **`projects_get`** — reads đơn lẻ (methods `get_project` / `get_project_item` / `get_project_field`).
2. **`projects_list`** — reads dạng list (methods `list_project_fields` / `list_project_items`).
3. **`projects_write`** — writes (methods `create_project` / `add_project_item` / `update_project_item` /
   `delete_project_item`).

Chúng key theo **owner + owner_type + project number**, KHÔNG phải node id. **Không bao giờ hardcode
node id.** Bất đối xứng quan trọng giữa read và write:

- **WRITE** (`update_project_item`) resolve item theo (`item_owner` + `item_repo` + `issue_number`)
  và field + option theo **tên** — tất cả server-side, không cần discover id nào.
- **READ đơn lẻ** (`get_project_item`) cần **`item_id` numeric** — KHÔNG resolve theo issue number.
  `item_id` đến từ mỗi row của `list_project_items` (orchestrator pass nó xuống spawn prompt của
  sub-agent); fallback khi không có: một lượt `list_project_items` + match `content.number`.

Một ngoại lệ thủ công duy nhất ở tầng write: MCP **không tạo/sửa được** single-select **Status**
field và các option của nó — đó là bước UI một lần lúc init (xem [Tạo board](#create-a-board)).
Runtime (transition / queue / verify) thì 100% MCP.

`projects` toolset (và `labels`) là **opt-in**: `github` MCP server phải được chạy với chúng bật qua
header `X-MCP-Toolsets` trong `.mcp.json` (mặc định **không** bật hai toolset này). Nếu không bật, các
tool `projects_*` không tồn tại và **toàn bộ state machine không hoạt động** — không có đường fallback.
Cả orchestrator lẫn ba sub-agent đều cần chúng.

Config của connection: `connections.github_project` bật/tắt link (`enabled`, `owner`, `owner_type`,
`auth.token_env`, `auth.scopes`, `mcp.server`) còn `board.number` / `board.columns` mang **project
number** và bảy tên column — `board.columns` chính là **state enum authoritative**; các option name
là wire value được resolve by-name, nên đổi tên một option trong UI là break routing (init validate,
xem dưới). Một connection chỉ dùng được khi `enabled:true` VÀ mọi env var bắt buộc đều có mặt
(xem skill: `setup-agentflow`).

## Resolve the board

Board được key theo `connections.github_project.owner` + `owner_type` + `board.number` (Projects v2
project number — chính là phần `/projects/<N>` trong URL hướng tới con người). "Resolve" chỉ là xác
nhận board tồn tại và lấy metadata của nó:

```
projects_get method=get_project
  owner: <owner>
  owner_type: <org|user>
  project_number: <board.number>
```

Nếu nó không resolve được dưới `owner`/`owner_type`/`number`, dừng và báo cho user — không có board
là không có state machine.

## Create a board

Dùng bởi /agentflow-init khi user chọn tạo board. Ba bước: tạo project (chỉ title) qua MCP, rồi cho
**Status** field bảy option khớp `board.columns` (thủ công-UI), rồi bật **built-in workflows**
(thủ công-UI).

1. Tạo project Projects v2 rỗng (chỉ title):

```
projects_write method=create_project
  owner: <owner>
  owner_type: <org|user>
  title: <project.name>
```

Lưu **number** trả về vào `board.number` và set `connections.github_project.enabled: true`. (MCP key
board theo number — KHÔNG lưu node id.)

2. **Status field 7 option — CARVE-OUT thủ công (MCP không tạo được).** Một project mới đi kèm default
   `Status` field mang `Todo/In Progress/Done`. AgentFlow cần **bảy** option đúng bằng `board.columns`
   (Inbox, Ready for Dev, In Progress, In QC, Refined, Ready for Human Review, Done). Hướng dẫn user
   mở board trong **GitHub Projects UI** và sửa field `Status`: thêm/đổi tên option cho đủ đúng bảy
   tên trên, khớp `board.columns` **một-đối-một**. Các option name giờ là **load-bearing wire value**
   của state machine — validate kỹ:

```
projects_list method=list_project_fields
  owner: <owner>
  owner_type: <org|user>
  project_number: <board.number>
```

   Assert field `Status` (single-select) có đủ một option cho mỗi trong bảy value của `board.columns`;
   nếu thiếu, liệt kê các tên option còn thiếu và yêu cầu user thêm trong UI rồi validate lại.

3. **Built-in workflows — thủ công-UI (không API nào config được, kể cả GraphQL chỉ đọc).** Hướng dẫn
   user mở Project settings → Workflows và bật:
   - **Item added to project** → Status: `Inbox`
   - **Item reopened** → Status: `Inbox`
   - **Item closed** → Status: `Done`

   Đây là automation miễn phí phủ các cạnh mà agent không chứng kiến (con người tự add card, tự
   close/reopen issue). Race với agent write vô hại vì agent intake cũng ghi cùng value `Inbox`
   (same-value); tuy vậy vì không verify được workflow đã bật hay chưa, **/task và PMO intake vẫn
   ghi Status="Inbox" explicit** — không bao giờ dựa vào workflow.

## Link an existing board

Dùng bởi /agentflow-init khi user cung cấp board number. Validate, không mutate dữ liệu của user:

1. Resolve theo number — [Resolve the board](#resolve-the-board).

2. Đọc `Status` field của nó qua `list_project_fields` (block ở [Tạo board](#create-a-board)) và xác
   nhận có option tồn tại cho mỗi trong bảy value của `board.columns`.

3. Nếu thiếu column nào, KHÔNG âm thầm ghi đè board — liệt kê các tên option còn thiếu và hướng dẫn
   user thêm chúng trong GitHub Projects UI (MCP không tạo được single-select field).

4. Hướng dẫn bật built-in workflows như bước 3 của [Tạo board](#create-a-board).

## Status transition (the state write)

Cho một issue và column đích, transition là **một call** — `update_project_item` resolve **cả item
lẫn option server-side** — không cần `list_project_fields` trước, không cần `item_id`, không cache
field id. Map đích theo `board.columns.<key>` (vd key `in_qc` → "In QC"):

```
projects_write method=update_project_item
  owner: <owner>
  owner_type: <org|user>              # LUÔN pass
  project_number: <board.number>
  item_owner: <owner của issue>       # (item_owner + item_repo + issue_number) resolve item
  item_repo: <repo của issue>
  issue_number: <n>
  updated_field:
    name: "Status"                    # by-NAME shape — bắt buộc
    value: <board.columns.<key>>      # tên option, vd "In QC"
```

> **`updated_field` BẮT BUỘC dùng by-name shape.** Nó nhận hai shape, và chúng **loại trừ nhau**:
> by-id (`{id: <số>, value: <optionID>}`) và by-name (`{name, value}`). Với single-select,
> **chỉ by-name mới resolve option theo tên** — trên by-id shape, `value` được coi thẳng là option
> **ID**. Vậy `{id: <fieldId>, value: "In QC"}` **không bao giờ hoạt động**. by-name cũng chấp nhận
> một option id nếu bạn đưa, nên nó strictly dominate — không có lý do dùng by-id.
>
> Option không resolve được → **hard-error kèm danh sách candidate**. Đó là drift signal (ai đó đã
> đổi tên column) và giờ nó block ROUTING — dừng, báo human, không đoán.
>
> **Item chưa có trên board** → `add_project_item` (idempotent, trả item có sẵn nếu đã tồn tại) rồi
> retry. Status write là **mandatory-success**: fail thì DỪNG run và báo lỗi — không "log rồi tiếp
> tục". Theo write order của SKILL.md, nó luôn là bước cuối (commit point) sau body + comment + aux
> label, và luôn đi sau **compare-then-write** (re-read Status, abort nếu con người đã đổi giữa run).
>
> Vì Status change không để lại timeline event, `add_project_item` khi tạo ticket mới phải đi kèm
> Status="Inbox" explicit ngay sau đó — một item nằm trên board với Status trống là trạng thái hợp lệ
> duy nhất cho card do con người tự thêm (xem Missing Status).

## Read one item's Status

`projects_get` method=`get_project_item` cần **`item_id` numeric** (không resolve theo issue number):

```
projects_get method=get_project_item
  owner: <owner>
  owner_type: <org|user>
  project_number: <board.number>
  item_id: <id>                        # từ list_project_items, hoặc do orchestrator pass xuống
  field_names: ["Status"]
```

Sub-agent trong orchestrated run nhận `item_id` + Status hiện tại ngay trong spawn prompt — dùng
`get_project_item` để verify/compare-then-write. Standalone run không có `item_id`: một lượt
[List actionable board items](#list-actionable-board-items) + match `content.number` với issue của bạn.

## List actionable board items

Orchestrator đọc **toàn bộ** board trong một lần để build **inbox queue** — và vì Status là
authoritative, cái nó đọc chính là state, không cần đối chiếu thêm gì. Paginate qua mọi item
(`per_page` ≤ 50, `after` cursor) và lấy, cho mỗi item: **item_id**, **number** của issue, **state**
của issue (bỏ qua closed), **assignees** (cho filter claim unassigned-inbox), **labels** (aux:
`rework`, `type/*`, `component/*`), và tên option **Status** hiện tại.

Truyền `field_names: ["Status"]` để mỗi item trả về value của Status field; `content` của mỗi item
cho **number / state / labels / assignees** của issue:

```
projects_list method=list_project_items
  owner: <owner>
  owner_type: <org|user>
  project_number: <board.number>
  per_page: 50
  after: <endCursor|null>
  field_names: ["Status"]
# loop khi còn trang tiếp theo, truyền endCursor làm cursor kế tiếp
```

> `field_names` được **resolve server-side** sang field id — không cần `list_project_fields`. Nó
> **loại trừ** `fields` (chỉ nhận numeric field id): truyền một cái, không bao giờ cả hai.
> **CRITICAL — luôn truyền `field_names`:** thiếu nó, mỗi item chỉ trả về title và Status sẽ **vắng
> mặt** (read bug), không phân biệt được với Status trống thật (một state có nghĩa — xem Missing
> Status).
>
> `list_project_items` còn nhận param **`query`** (server-side, cú pháp filter bar của Projects:
> `status:"In QC"`, `is:open`, `no:status`, `-status:Done`) — được phép dùng như **optimization** để
> giảm số trang, với caveat: option đổi tên làm filter **silently trả rỗng** (khác với write by-name
> hard-error). Baseline canonical vẫn là full paginate + filter client-side; nếu dùng `query`, coi
> "kết quả rỗng bất thường" là tín hiệu phải fallback full paginate.

List trả về **tất cả** board item; orchestrator áp filter *inbox-claim* ở client-side:
issue `state == open`, **Status = "Inbox"** (hoặc Status trống → xem Missing Status), và
**không có assignee** (chưa được claim). Nó claim một cái bằng cách tự assign cho mình, rồi drive
ticket đó end-to-end theo Status sống. Một card **draft** (không có issue number/content) nằm ngoài
state machine — surface nó cho human để convert thành issue qua `/task`.

## Missing Status & membership (các trạng thái bất thường)

Thay cho quy ước cũ "không có state → coi như inbox", phân biệt ba trường hợp:

1. **Item trên board, Status trống, body KHÔNG có `AGENTFLOW-STATE`** → intake mới (con người tự add
   card, workflow "Item added" chưa bật) → coi như "Inbox": orchestrator claim rồi PMO triage như
   thường (PMO sẽ ghi Status="Inbox" explicit khi bắt đầu).
2. **Item trên board, Status trống, body CÓ `AGENTFLOW-STATE` với `Current state` ≠ Inbox** →
   **ANOMALY** (option bị xóa / state bị mất): KHÔNG BAO GIỜ default về Inbox — post
   `[SYSTEM] status lost (body says "<Current state>") — human please re-set the column`, skip
   ticket, surface cho human. Đây là lý do body `Current state` vẫn load-bearing: nó là bằng chứng
   phục hồi duy nhất. Status trống + body CÓ `AGENTFLOW-STATE` với `Current state` = Inbox → xử lý
   như case 1 (intake): coi như Inbox.
3. **Issue OPEN nhưng không có trên board** → vô hình với routing. `/status` chạy một **membership
   check** (list open issues của repo, đối chiếu với board items) để phát hiện và liệt kê — human
   add card (hoặc `/task` với issue sẵn có) để đưa nó vào state machine.

## Board-driven mode

Board-driven là mode **duy nhất** — board bắt buộc và `/start` yêu cầu nó lúc boot. Orchestrator đọc
queue qua [List actionable board items](#list-actionable-board-items) và **tin Status** — không có
nguồn state thứ hai để đối chiếu. Sub-agent PMO/DEV/QC tự thực hiện transition của mình qua
`update_project_item` (xem SKILL.md, Write order); orchestrator đọc lại Status sau mỗi sub-agent run
(qua `get_project_item` với `item_id` nó đã có) để quyết định bước tiếp theo trong chain.

## Canonical status_map (routing table)

`/start` dùng bảng canonical bên dưới làm routing table duy nhất — đọc nó ở đây, đừng hardcode
một bảng khác. Các chuỗi `column` khớp với `board.columns` canonical; nếu một repo đổi tên một
column, map theo **`<key>`** (ví dụ `in_qc`), không theo chuỗi hiển thị.

```yaml
status_map:
  inbox:                  { column: "Inbox",                  owner: "pmo",   action: "claim (self-assign) → triage + refine to DoR; DoR pass → Ready for Dev, else (needs human info) → Refined" }
  ready_for_dev:          { column: "Ready for Dev",          owner: "dev",   action: "if an open PR linked to the issue exists → amend it (reuse branch); else implement on a type-named branch, open PR. If `rework` aux label present → read latest QC rejection first. If body lacks `## For DEV` + numbered AC → DoR defense: back to Inbox" }
  in_progress:            { column: "In Progress",            owner: "dev",   action: "active coding (claim held) — NOT re-spawnable; break out if paused/blocked" }
  in_qc:                  { column: "In QC",                  owner: "qc",    action: "author tests + run tier; ✅ → Ready for Human Review, ❌ → rework label + Ready for Dev (fail ≤ 2 consecutive) else Refined (escalate)" }
  refined:                { column: "Refined",                owner: "human", action: "BLOCKED — human supplies missing info/decision (via /review-refined, or drags the card back to Inbox after adding info)" }
  ready_for_human_review: { column: "Ready for Human Review", owner: "human", action: "human reviews / merges (QC ✅, merge-ready); to request changes, human leaves PR feedback and DRAGS the card back to Inbox (agent never does this)" }
  done:                   { column: "Done",                   owner: "human", action: "terminal" }
```

> **`in_progress`, `refined`, `ready_for_human_review` là break-out state:** orchestrator không route
> chúng đi tiếp, và ở `refined` / `ready_for_human_review` nó **unassign** ticket. Chi tiết lane trong
> `../SKILL.md` ("Rework loop và escalation", "Human PR-review feedback", "Clarification loop").

## Scopes

Board là **bắt buộc** và mang state authoritative, nên `project` scope luôn được yêu cầu — `/start`
dừng lúc boot nếu thiếu `project`. Sub-agent dùng chung `GITHUB_TOKEN` nên cùng scope.

- Org board: `GITHUB_TOKEN` cần `project` **và** `read:org`.
- User board: `GITHUB_TOKEN` cần `project`.
- Reads-only (list queue / list fields) cần tối thiểu `read:project`; mọi transition + create-board
  cần `project` (đã bao `read:project`). Khuyến nghị classic PAT — fine-grained PAT chưa được verify
  cho user-owned board.
