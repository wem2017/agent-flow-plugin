# GitHub Projects v2 board (inbox queue + human mirror)

> Tài liệu tham khảo cho skill `project-board-protocol`. Đọc `../SKILL.md` trước — file này chứa phần
> board mechanics nặng, hiếm khi cần, được tách ra để protocol chính gọn nhẹ.

**Quy tắc duy nhất override mọi thứ bên dưới:** `flow:*` **LABEL is authoritative** cho việc
routing. Board Projects v2 là **inbox queue + mirror cho người xem** của orchestrator.
Các sub-agent (PMO/DEV/QC) quyết định làm gì tiếp theo bằng cách đọc label `flow:*` của issue — chúng **không bao giờ**
đọc board column để ra quyết định. Việc ghi mirror là **best-effort và có thể trễ**. Nếu một lần ghi mirror
fail, log lại và tiếp tục; pipeline không bị ảnh hưởng.

## Nội dung

- [Cách Projects v2 được điều khiển (GraphQL vs official MCP `projects` toolset)](#how-projects-v2-is-driven)
- [Resolve board](#resolve-the-board)
- [Tạo board (init: `github_project=create`)](#create-a-board)
- [Link một board có sẵn](#link-an-existing-board)
- [Mirror một flow:* label → column](#mirror-a-flow-label--column)
- [Liệt kê các board item actionable (orchestrator queue)](#list-actionable-board-items)
- [Bổ sung cho board-driven mode](#board-driven-mode-amendment)
- [Canonical status_map (board-driven mode)](#canonical-status_map-board-driven-mode)
- [Scopes](#scopes)
- [Các script helper](#helper-scripts)

## How Projects v2 is driven

Projects v2 **không có `gh`-CLI REST path** — `gh issue edit` đổi được label nhưng **không thể** di chuyển một
card. Có hai cơ chế; chọn **một** cho mỗi install và giữ nhất quán:

1. **`gh api graphql`** (default — cái mà các snippet bên dưới dùng). Làm được mọi thứ: resolve
   board node id, **tạo** project và single-select Status field của nó, thêm item, và
   set Status. Việc tạo project + Status **field** là **GraphQL-only** — MCP server không tạo được
   field 7 option.
2. **`projects` toolset của `github` MCP server chính thức** (optional, chỉ ở mức item). Khi
   server chạy với `projects` toolset được bật, nó expose `projects_list` / `projects_get`
   (reads) và `projects_write` (methods `add_project_item` / `update_project_item` /
   `delete_project_item`). Nó key theo **owner + project number**, không phải `PVT_` node id, và nó
   **không thể** tạo Status field. Nếu một project dùng nó cho per-item mirror, lưu
   **cả** project number lẫn `PVT_` node id dưới `board:`.

**Default khuyến nghị: giữ một cơ chế duy nhất — `gh api graphql` — cho cả bootstrap lẫn mirror.** Nó
tránh việc phải nối node-id-vs-number và không cần opt-in toolset nào. Đường `projects_write` của MCP là
một lựa chọn thay thế có tài liệu, không phải bắt buộc. (Việc bootstrap Status field thì luôn nằm trên GraphQL
bất kể thế nào.)

Config của connection: `connections.github_project` bật/tắt link (`enabled`, `owner`, `owner_type`,
`auth.token_env`, `auth.scopes`, `mcp.server`) còn `board.id` / `board.columns` mang node id
và bảy tên column. Một connection chỉ dùng được khi `enabled:true` VÀ mọi env
var bắt buộc đều có mặt (xem skill: `setup-agentflow`).

## Resolve the board

Một board có **node id** dạng `PVT_xxx`. Resolve nó từ
`connections.github_project.owner` + `owner_type` và **number** của board (hoặc chạy
`scripts/resolve-board.sh <owner> <owner_type> <number>`):

```bash
# owner_type: org
gh api graphql -f query='
  query($login:String!, $number:Int!){
    organization(login:$login){ projectV2(number:$number){ id title } }
  }' -F login="<owner>" -F number=<N>

# owner_type: user
gh api graphql -f query='
  query($login:String!, $number:Int!){
    user(login:$login){ projectV2(number:$number){ id title } }
  }' -F login="<owner>" -F number=<N>
```

`id` trả về (`PVT_…`) chính là thứ đặt vào `board.id`. Một project **number** hướng tới con người (URL
`/projects/<N>`) map tới đúng một node id qua query bên trên; lưu node id, không lưu
number, để các lần gọi sau bỏ qua bước lookup.

## Create a board

Dùng bởi /agentflow-init khi user chọn tạo board. Hai bước: tạo project, rồi
cho **Status** field của nó các option khớp với `board.columns`.

1. Tạo project Projects v2 dưới owner node id đã resolve:

```bash
# get the owner node id first
gh api graphql -f query='query($l:String!){ organization(login:$l){ id } }' -F l="<owner>"

gh api graphql -f query='
  mutation($owner:ID!, $title:String!){
    createProjectV2(input:{ ownerId:$owner, title:$title }){
      projectV2{ id number }
    }
  }' -F owner="<ownerNodeId>" -F title="<project.name>"
```

Lưu `projectV2.id` trả về vào `board.id` và set `connections.github_project.enabled: true`.

2. Tìm hoặc tạo single-select **Status** field. Một project mới đi kèm default `Status`
   field mang `Todo/In Progress/Done`. AgentFlow cần **bảy** option trong `board.columns`
   (Inbox, Ready for Dev, In Progress, In QC, Refined, Ready for Human Review,
   Done). Tạo lại field với đúng các option đó, theo thứ tự:

```bash
gh api graphql -f query='
  mutation($project:ID!){
    createProjectV2Field(input:{
      projectId:$project,
      dataType: SINGLE_SELECT,
      name: "Status",
      singleSelectOptions: [
        { name: "Inbox",                  color: GRAY,   description: "" },
        { name: "Ready for Dev",          color: BLUE,   description: "" },
        { name: "In Progress",            color: YELLOW, description: "" },
        { name: "In QC",                  color: ORANGE, description: "" },
        { name: "Refined",                color: RED,    description: "needs human — provide info, then move to Inbox" },
        { name: "Ready for Human Review", color: PINK,   description: "" },
        { name: "Done",                   color: GREEN,  description: "" }
      ]
    }){ projectV2Field { ... on ProjectV2SingleSelectField { id options { id name } } } }
  }' -F project="<board.id>"
```

Các chuỗi `name` của option PHẢI bằng các value dưới `board.columns` một-đối-một — chính string
match đó là cách một `flow:*` label được map tới một option về sau. (`singleSelectOptions` yêu cầu
`name`, `color`, và `description` trên mỗi option.)

## Link an existing board

Dùng bởi /agentflow-init khi user cung cấp board number/id. Validate, không mutate
dữ liệu của user:

1. Resolve id (xem Resolve the board, ở trên). Nếu nó không resolve được dưới `owner`/`owner_type`,
   dừng và báo cho user.
2. Đọc `Status` field của nó và xác nhận có option tồn tại cho mỗi trong bảy value của `board.columns`:

```bash
gh api graphql -f query='
  query($id:ID!){ node(id:$id){ ... on ProjectV2 {
    field(name:"Status"){ ... on ProjectV2SingleSelectField { id options { id name } } }
  }}}' -F id="<board.id>"
```

3. Nếu thiếu column nào, KHÔNG âm thầm ghi đè board — liệt kê các tên option còn thiếu và
   hướng dẫn user thêm chúng (hoặc để init tạo lại field).

## Mirror a flow:* label → column

Cho một issue và `flow:*` label hiện tại của nó, mirror nó sang board (hoặc chạy
`scripts/mirror-label-to-board.sh`). Map `labels.flow.<key>` → `board.columns.<key>` **một-đối-một**
(cùng `<key>`: ví dụ `flow:in-qc` → key `in_qc` → `board.columns.in_qc` = "In QC"). Cần ba id:
**item id** (card của issue), Status **field id**, và **option id** đích.

```bash
# 1. add the issue to the project (idempotent; returns the existing item if present)
gh api graphql -f query='
  mutation($project:ID!, $content:ID!){
    addProjectV2ItemById(input:{ projectId:$project, contentId:$content }){
      item { id }
    }
  }' -F project="<board.id>" -F content="<issueNodeId>"

# 2. set its Status to the option whose name == board.columns.<key>
gh api graphql -f query='
  mutation($project:ID!, $item:ID!, $field:ID!, $option:String!){
    updateProjectV2ItemFieldValue(input:{
      projectId:$project, itemId:$item, fieldId:$field,
      value:{ singleSelectOptionId:$option }
    }){ projectV2Item { id } }
  }' -F project="<board.id>" -F item="<itemId>" \
     -F field="<statusFieldId>" -F option="<optionId>"
```

Resolve `<issueNodeId>` bằng `gh issue view <n> --json id` (hoặc GitHub MCP). Lấy
`<statusFieldId>` và `<optionId>` cho column đích từ query `Status` field bên trên,
match theo `name` của option. Mirror này chạy **sau** khi swap label, không bao giờ thay cho nó; khi
có bất kỳ lỗi nào, log lại và đi tiếp.

## List actionable board items

Orchestrator đọc **toàn bộ** board trong một lần để build **inbox queue** của nó. Đây là query
duy nhất đọc board state như một *queue*. Paginate qua mọi item và lấy, cho mỗi item: **number** của
issue, **item id** (dùng lại trực tiếp trong `updateProjectV2ItemFieldValue` của mirror,
bỏ qua vòng round-trip `addProjectV2ItemById`), **labels** sống của issue (`flow:*` authoritative),
**state** của issue (bỏ qua `CLOSED`), **assignees** của issue (cho filter claim unassigned-inbox),
và tên option **Status** hiện tại.

```bash
gh api graphql -f query='
  query($project:ID!, $cursor:String){
    node(id:$project){ ... on ProjectV2 {
      items(first:50, after:$cursor){
        pageInfo{ hasNextPage endCursor }
        nodes{
          id
          fieldValueByName(name:"Status"){
            ... on ProjectV2ItemFieldSingleSelectValue { name optionId }
          }
          content{
            ... on Issue {
              number
              state
              url
              repository{ nameWithOwner }
              labels(first:20){ nodes{ name } }
              assignees(first:5){ nodes{ login } }
            }
            ... on DraftIssue { title }   # draft cards have no issue → not routable
          }
        }
      }
    }}}' -F project="<board.id>" -F cursor="<endCursor|null>"
# loop while .data.node.items.pageInfo.hasNextPage, passing endCursor as the next cursor
```

List trả về **tất cả** board item; orchestrator áp filter *inbox-claim* ở client-side:
issue `state == OPEN`, mang `flow:inbox` (hoặc chưa có `flow:*` label → coi như inbox), và
**không có assignee** (chưa được claim). Nó claim một cái bằng cách tự assign cho mình, rồi drive ticket đó end-to-end dựa trên
label sống của nó. Một card **draft** (không có `content.number`) nằm ngoài label state machine — surface
nó cho human để convert thành issue qua `/task`.

## Board-driven mode amendment

Board-driven giờ là mode **duy nhất** — board là bắt buộc và `/start` yêu cầu nó. Protocol mặc định
(trong `../SKILL.md`) giữ `flow:*` **label authoritative** và coi board là
**inbox queue + mirror cho người xem** của orchestrator. **Orchestrator** (`/start`) đọc
board để lấy **inbox queue** của nó qua query list bên trên — nó chỉ scan các card `flow:inbox`
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
  ready_for_dev:          { column: "Ready for Dev",          flow_label: "flow:ready-for-dev",          owner: "dev",   action: "implement on a type-named branch, open PR (rework if `rework`/`human-changes` aux present — read latest QC rejection / mirrored PR feedback first)" }
  in_progress:            { column: "In Progress",            flow_label: "flow:in-progress",            owner: "dev",   action: "active coding (claim held) — NOT re-spawnable; break out if paused/blocked" }
  in_qc:                  { column: "In QC",                  flow_label: "flow:in-qc",                  owner: "qc",    action: "author tests + run tier; ✅ → ready-for-human-review, ❌ → ready-for-dev+rework (fail ≤ max_rework_returns) else refined (escalate)" }
  refined:                { column: "Refined",                flow_label: "flow:refined",                owner: "human", action: "BLOCKED — human supplies missing info/decision (via /review-refined), then re-labels to flow:inbox to resume" }
  ready_for_human_review: { column: "Ready for Human Review", flow_label: "flow:ready-for-human-review", owner: "human", action: "human reviews / merges (QC ✅, merge-ready)" }
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
> **`ready_for_human_review` được re-scan, không chỉ park.** `owner` của nó là `human`, nhưng giữa các
> lần poll human có thể để lại một PR review **"Request changes"** thay vì merge. Orchestrator
> re-scan các ticket `flow:ready-for-human-review` của nó để tìm một review **Request changes** mới
> từ trusted-maintainer (mới hơn lần cuối ticket vào state đó) và, khi trúng,
> route ticket về lại DEV (`flow:ready-for-dev` + `human-changes`, reset `consecutive_fail`).
> Đây là Status duy nhất mà orchestrator đọc vượt ra ngoài inbox queue. Aux label giữ
> `status_map` không đổi (`flow:ready-for-dev` vẫn → owner `dev`). Xem `commands/start.md`
> ("Human-review rework") và skill `project-board-protocol` ("Human-review rework").

## Scopes

Board là **bắt buộc**, nên `project` scope luôn được yêu cầu — `/start` đọc board để
build inbox queue và dừng lúc boot nếu thiếu `project`.

- Org board: `GITHUB_TOKEN` cần `project` **và** `read:org`.
- User board: `GITHUB_TOKEN` cần `project`.
- Nếu dùng MCP `projects` toolset optional cho mirror, `github` MCP server phải được chạy
  với toolset đó bật (mặc định **không** bật); nếu không, các tool `projects_*` âm thầm
  không tồn tại và mirror fallback về GraphQL.

## Helper scripts

Hai thao tác deterministic được đóng gói thành script để agent chạy chúng thay vì gõ lại
GraphQL mong manh (low-freedom rule, xem Anthropic skill best-practices):

- `scripts/resolve-board.sh <owner> <owner_type> <number>` → in ra `PVT_…` node id.
- `scripts/mirror-label-to-board.sh <board_id> <issue_node_id> <status_field_id> <option_id>` →
  thêm issue vào board và set Status option của nó (hai mutation bên trên).

Cả hai là wrapper mỏng bọc quanh `gh api graphql`; đọc chúng trước lần dùng đầu tiên để xác nhận chúng khớp với
`board.columns` của bạn.
