# GitHub Projects v2 board (inbox queue + human mirror)

> Tài liệu tham khảo cho skill `project-board-protocol`. Đọc `../SKILL.md` trước — file này chứa phần
> board mechanics nặng, hiếm khi cần, được tách ra để protocol chính gọn nhẹ.

**Quy tắc duy nhất override mọi thứ bên dưới:** `flow:*` **LABEL is authoritative** cho việc
routing. Board Projects v2 là **inbox queue + mirror cho người xem** của orchestrator.
Các sub-agent (PMO/DEV/QC) quyết định làm gì tiếp theo bằng cách đọc label `flow:*` của issue — chúng **không bao giờ**
đọc board column để ra quyết định. Việc ghi mirror là **best-effort và có thể trễ**. Nếu một lần ghi mirror
fail, log lại và tiếp tục; pipeline không bị ảnh hưởng.

## Nội dung

- [Cách Projects v2 được điều khiển (MCP `projects` toolset)](#how-projects-v2-is-driven)
- [Resolve board](#resolve-the-board)
- [Tạo board (init: `github_project=create`)](#create-a-board)
- [Link một board có sẵn](#link-an-existing-board)
- [Mirror một flow:* label → column](#mirror-a-flow-label--column)
- [Liệt kê các board item actionable (orchestrator queue)](#list-actionable-board-items)
- [Bổ sung cho board-driven mode](#board-driven-mode-amendment)
- [Canonical status_map (board-driven mode)](#canonical-status_map-board-driven-mode)
- [Scopes](#scopes)

## How Projects v2 is driven

Projects v2 được điều khiển **hoàn toàn qua `projects` toolset của `github` MCP server chính thức** — KHÔNG
dùng `gh api graphql`, KHÔNG dùng `PVT_` GraphQL node id. Ba tool:

1. **`projects_get`** — reads đơn lẻ (method `get_project`).
2. **`projects_list`** — reads dạng list (methods `list_project_fields` / `list_project_items`).
3. **`projects_write`** — writes (methods `create_project` / `add_project_item` / `update_project_item` /
   `delete_project_item`).

Chúng key theo **owner + owner_type + project number**, KHÔNG phải node id. Các **numeric field id +
option id** không được hardcode — chúng được **discover lúc runtime** qua `list_project_fields` rồi
truyền lại cho item ops. Một ngoại lệ duy nhất: MCP **không tạo được** single-select **Status** field
7 option — đó là bước thủ công một lần trong GitHub UI lúc init (xem [Tạo board](#create-a-board)).
Runtime (mirror / list queue) thì 100% MCP.

`projects` toolset là **opt-in**: `github` MCP server phải được chạy với nó bật qua header
`X-MCP-Toolsets` trong `.mcp.json` (mặc định không có `projects`). Nếu không bật, các tool `projects_*`
không tồn tại và board không hoạt động (xem [Scopes](#scopes)).

Config của connection: `connections.github_project` bật/tắt link (`enabled`, `owner`, `owner_type`,
`auth.token_env`, `auth.scopes`, `mcp.server`) còn `board.number` / `board.columns` mang **project
number** và bảy tên column. Một connection chỉ dùng được khi `enabled:true` VÀ mọi env
var bắt buộc đều có mặt (xem skill: `setup-agentflow`).

## Resolve the board

Board được key theo `connections.github_project.owner` + `owner_type` + `board.number` (Projects v2
project number — chính là phần `/projects/<N>` trong URL hướng tới con người). KHÔNG còn `PVT_` node
id nào để lưu; MCP projects tools nhận thẳng owner/owner_type/number. "Resolve" giờ chỉ là xác nhận
board tồn tại và lấy metadata của nó:

```
projects_get method=get_project
  owner: <owner>
  owner_type: <org|user>
  project_number: <board.number>
```

Nếu nó không resolve được dưới `owner`/`owner_type`/`number`, dừng và báo cho user.

## Create a board

Dùng bởi /agentflow-init khi user chọn tạo board. Hai bước: tạo project (chỉ title) qua MCP, rồi cho
**Status** field bảy option khớp `board.columns` — bước 2 là **thủ công-UI** vì MCP không tạo được
single-select field.

1. Tạo project Projects v2 rỗng (chỉ title):

```
projects_write method=create_project
  owner: <owner>
  owner_type: <org|user>
  title: <project.name>
```

Lưu **number** trả về vào `board.number` và set `connections.github_project.enabled: true`. (MCP key
board theo number — KHÔNG lưu node id.)

2. **Status field 7 option — CARVE-OUT thủ công (MCP không tạo được).** `projects` toolset chỉ có
   `create_project` (empty) + item ops; nó **không** create hay edit single-select field. Một project
   mới đi kèm default `Status` field mang `Todo/In Progress/Done`. AgentFlow cần **bảy** option đúng
   bằng `board.columns` (Inbox, Ready for Dev, In Progress, In QC, Refined, Ready for Human Review,
   Done). Hướng dẫn user mở board trong **GitHub Projects UI** và sửa field `Status`: thêm/đổi tên
   option cho đủ đúng bảy tên trên, khớp `board.columns` **một-đối-một** — chính string match đó là
   cách một `flow:*` label được map tới một option về sau.

   Rồi init **validate** qua MCP (chỉ đọc, không mutate):

```
projects_list method=list_project_fields
  owner: <owner>
  owner_type: <org|user>
  project_number: <board.number>
```

   Assert field `Status` (single-select) có đủ một option cho mỗi trong bảy value của `board.columns`;
   nếu thiếu, liệt kê các tên option còn thiếu và yêu cầu user thêm trong UI rồi validate lại. Đây là
   bước thủ công **một lần** — MCP không hỗ trợ tạo single-select field, đây KHÔNG phải `gh`.

## Link an existing board

Dùng bởi /agentflow-init khi user cung cấp board number. Validate, không mutate dữ liệu của user:

1. Resolve theo number (xem [Resolve the board](#resolve-the-board)). Nếu nó không resolve được dưới
   `owner`/`owner_type`, dừng và báo cho user:

```
projects_get method=get_project
  owner: <owner>
  owner_type: <org|user>
  project_number: <board.number>
```

2. Đọc `Status` field của nó qua `list_project_fields` và xác nhận có option tồn tại cho mỗi trong bảy
   value của `board.columns`:

```
projects_list method=list_project_fields
  owner: <owner>
  owner_type: <org|user>
  project_number: <board.number>
```

3. Nếu thiếu column nào, KHÔNG âm thầm ghi đè board — liệt kê các tên option còn thiếu và hướng dẫn
   user thêm chúng trong GitHub Projects UI (MCP không tạo được single-select field).

## Mirror a flow:* label → column

Cho một issue và `flow:*` label hiện tại của nó, mirror nó sang board. Map `labels.flow.<key>` →
`board.columns.<key>` **một-đối-một** (cùng `<key>`: ví dụ `flow:in-qc` → key `in_qc` →
`board.columns.in_qc` = "In QC").

Trước tiên **discover** Status field id + option ids qua `list_project_fields` (trả `id` của field +
`options:[{id,name}]`), match option đích theo **name == `board.columns.<key>`**:

```
projects_list method=list_project_fields
  owner: <owner>
  owner_type: <org|user>
  project_number: <board.number>
```

Rồi hai bước:

```
# 1. add issue vào project (idempotent; trả item có sẵn nếu đã tồn tại)
projects_write method=add_project_item
  owner: <owner>
  owner_type: <org|user>
  project_number: <board.number>
  item_type: issue
  item_owner: <owner của issue>
  item_repo: <repo của issue>
  issue_number: <n>
# → trả về item id

# 2. set Status = option có name == board.columns.<key>
projects_write method=update_project_item
  owner: <owner>
  project_number: <board.number>
  item_id: <itemId từ bước 1>
  updated_field:
    id: <statusFieldId>       # discover qua list_project_fields
    value: <optionName>       # tên option, khớp board.columns.<key>
```

> **Note — name-vs-id + best-effort.** `updated_field.value` ở đây pass **tên** option (plain string
> khớp `board.columns.<key>`). Format name-vs-id cần một **live-test lần chạy đầu**: nếu
> `update_project_item` fail vì value format, thử pass option **id** (từ `list_project_fields`) thay vì
> name. Mirror là **best-effort** — mọi lỗi chỉ **log rồi tiếp tục**, không bao giờ block pipeline. Nó
> chạy **sau** khi swap label, không bao giờ thay cho nó.

## List actionable board items

Orchestrator đọc **toàn bộ** board trong một lần để build **inbox queue** của nó. Đây là read board
state duy nhất coi board như một *queue*. Paginate qua mọi item (`per_page` ≤ 50, `after` cursor) và
lấy, cho mỗi item: **number** của issue, **item id** (dùng lại trực tiếp trong `update_project_item`
của mirror, bỏ qua round-trip `add_project_item`), **labels** sống của issue (`flow:*` authoritative),
**state** của issue (bỏ qua closed), **assignees** của issue (cho filter claim unassigned-inbox),
và tên option **Status** hiện tại.

Truyền `fields:[<statusFieldId>]` (discover qua `list_project_fields`) để mỗi item trả về value của
Status field; `content` của mỗi item cho **number / state / labels / assignees** của issue:

```
projects_list method=list_project_items
  owner: <owner>
  owner_type: <org|user>
  project_number: <board.number>
  per_page: 50
  after: <endCursor|null>
  fields: [<statusFieldId>]
# loop khi còn trang tiếp theo, truyền endCursor làm cursor kế tiếp
```

List trả về **tất cả** board item; orchestrator áp filter *inbox-claim* ở client-side:
issue `state == open`, mang `flow:inbox` (hoặc chưa có `flow:*` label → coi như inbox), và
**không có assignee** (chưa được claim). Nó claim một cái bằng cách tự assign cho mình, rồi drive ticket đó end-to-end dựa trên
label sống của nó. Một card **draft** (không có issue number/content) nằm ngoài label state machine — surface
nó cho human để convert thành issue qua `/task`.

## Board-driven mode amendment

Board-driven giờ là mode **duy nhất** — board là bắt buộc và `/start` yêu cầu nó. Protocol mặc định
(trong `../SKILL.md`) giữ `flow:*` **label authoritative** và coi board là
**inbox queue + mirror cho người xem** của orchestrator. **Orchestrator** (`/start`) đọc
board để lấy **inbox queue** của nó qua list-items call bên trên — nó chỉ scan các card `flow:inbox`
chưa được assign, claim một cái, rồi drive ticket đó end-to-end. Nó là reader *duy nhất* được phép đọc column,
và ngay cả nó cũng không *tin* column cho state — với mỗi item nó đọc lại label `flow:*` sống
của issue và route theo **label** (label thắng khi có bất kỳ drift nào), rồi re-mirror Status cho khớp.
Các sub-agent PMO/DEV/QC vẫn **không bao giờ** đọc hay ghi board; mọi lần ghi board đều nằm ở tầng
orchestrator (`/start`, `/task`). Board là inbox queue + mirror; label mới là sự thật.

## Canonical status_map (board-driven mode)

`/start` dùng bảng canonical bên dưới làm routing table duy nhất — đọc nó ở đây, đừng hardcode
một bảng khác. Các chuỗi `column` khớp với `board.columns` canonical; nếu một repo đổi tên một
column, map theo **`<key>`** (ví dụ `in_qc`), không theo chuỗi hiển thị.

```yaml
status_map:
  inbox:                  { column: "Inbox",                  flow_label: "flow:inbox",                  owner: "pmo", action: "claim (self-assign) → triage + refine to DoR; DoR pass → ready-for-dev, else (needs human info) → refined" }
  ready_for_dev:          { column: "Ready for Dev",          flow_label: "flow:ready-for-dev",          owner: "dev",   action: "if an open PR linked to the issue exists → amend it (reuse branch); else implement on a type-named branch, open PR. If `rework` aux present → read latest QC rejection first" }
  in_progress:            { column: "In Progress",            flow_label: "flow:in-progress",            owner: "dev",   action: "active coding (claim held) — NOT re-spawnable; break out if paused/blocked" }
  in_qc:                  { column: "In QC",                  flow_label: "flow:in-qc",                  owner: "qc",    action: "author tests + run tier; ✅ → ready-for-human-review, ❌ → ready-for-dev+rework (fail ≤ 2 consecutive) else refined (escalate)" }
  refined:                { column: "Refined",                flow_label: "flow:refined",                owner: "human", action: "BLOCKED — human supplies missing info/decision (via /review-refined), then re-labels to flow:inbox to resume" }
  ready_for_human_review: { column: "Ready for Human Review", flow_label: "flow:ready-for-human-review", owner: "human", action: "human reviews / merges (QC ✅, merge-ready); to request changes, human leaves PR feedback and MANUALLY moves the ticket to flow:inbox (agent never does this)" }
  done:                   { column: "Done",                   flow_label: "flow:done",                   owner: "human", action: "terminal" }
```

> **`in_progress` là một case đặc biệt.** `owner` của nó là `dev` (công việc thuộc về DEV), nhưng card
> đang **in-flight (claim đang được giữ)** — orchestrator **không bao giờ được re-spawn DEV** trên nó. Một card
> nằm ở `flow:in-progress` giữa các lần poll nghĩa là DEV đã pause hoặc bị block → **break out cho human**,
> đừng route nó đi tiếp. Xem `commands/start.md` (polling loop, quyết định "next step").

> **`refined` là human-intervention parking (owner: human).** Nó là một break-out/park giống
> `ready_for_human_review`: mọi info-gap (PMO không đạt được DoR, DEV thiếu spec/Figma, QC gặp AC
> mơ hồ, hoặc 2-strike escalation của QC) đều rơi vào đây. Khi break out về `flow:refined`,
> orchestrator **unassign** ticket để nó có thể re-enter inbox queue. Con người dùng
> `/review-refined` (hoặc sửa label tay) để bổ sung info/quyết định rồi **re-label về `flow:inbox`**;
> PMO re-triage cái ticket đó và `consecutive_fail` reset. Xem `commands/review-refined.md` và
> `commands/start.md` (break-out + unassign).
>
> **`ready_for_human_review` là break-out/park thuần (KHÔNG re-scan).** `owner` của nó là `human`.
> Con người review/merge PR — hoặc, để yêu cầu thay đổi, để feedback inline trên PR rồi **tự tay
> chuyển ticket về `flow:inbox`** (agent/orchestrator không bao giờ tự làm; không có re-scan
> "Request changes", không đọc `reviewDecision`). Khi break-out ở state này orchestrator **unassign**
> ticket, nên con người chỉ cần đổi 1 label là ticket re-enter unassigned-inbox queue. PMO re-triage
> cái ticket đó, **đọc PR feedback trực tiếp**, fold vào AC, rồi drive tiếp qua DEV (amend PR sẵn có)
> → QC → human review. Orchestrator **không** đọc Status nào vượt ra ngoài inbox queue. Xem
> `commands/start.md` và skill `project-board-protocol` ("Human PR-review feedback").

## Scopes

Board là **bắt buộc**, nên `project` scope luôn được yêu cầu — `/start` đọc board để
build inbox queue và dừng lúc boot nếu thiếu `project`.

- Org board: `GITHUB_TOKEN` cần `project` **và** `read:org`.
- User board: `GITHUB_TOKEN` cần `project`.
- Reads-only (list queue / list fields) cần tối thiểu `read:project`; các write của mirror + create-board
  cần `project` (đã bao `read:project`).
- `projects` toolset (và `labels`) là **opt-in** — `github` MCP server phải được chạy với chúng bật qua
  header `X-MCP-Toolsets` trong `.mcp.json` (mặc định **không** bật hai toolset này). Nếu không bật,
  các tool `projects_*` không tồn tại và board không hoạt động — không còn đường fallback nào (GraphQL
  đã bị bỏ hoàn toàn).
