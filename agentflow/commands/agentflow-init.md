---
description: Bootstrap AgentFlow trong repo hiện tại — resolve project + summary, wire connections (full auth/MCP spec), detect các surface đang tồn tại, tạo các classification label type/*/component/* + rework, một board bắt buộc với Status field authoritative (7 option + built-in workflows), tùy chọn scaffold project skills có role-prefix, rồi ghi .claude/agentflow.yaml + README.agentflow.md. Re-run trên repo v0.3.x sẽ backfill Status từ các label flow:* di sản rồi dọn chúng.
argument-hint: (không có args — chạy một setup wizard tương tác)
---

Bạn đang bootstrap **AgentFlow** trong repository HIỆN TẠI của user. Đây là setup một
lần, nhưng nó **idempotent và chạy lại được** — user chạy lại để re-detect surfaces,
thêm board sau, đăng ký skill mới, hoặc refresh env/connections. Không bao giờ hủy một
`.claude/agentflow.yaml` đã sửa tay mà không cảnh báo; nếu đã có, đọc nó, coi các value của nó
là default cho mỗi bước bên dưới, và xác nhận trước khi ghi đè.

Thực hiện các bước **theo thứ tự**. Nếu một precondition fail, nói cho user chính xác cần
fix gì rồi **stop** — đừng cố tiếp tục với một repo cấu hình dở dang. Không bao giờ echo giá trị secret.

---

## 1. Preconditions

Chạy các lệnh sau và dừng ở lần fail đầu tiên kèm hướng fix chính xác:

```bash
git rev-parse --is-inside-work-tree                                        # must be a git repo
git remote get-url origin                                                  # must resolve to a GitHub remote
[ -n "${GITHUB_TOKEN:-}" ] && echo "token: set" || echo "token: MISSING"   # must be present
```

Rồi **probe MCP** để xác nhận token hợp lệ: gọi `get_me` (context toolset). Trả về một `login` = authenticated; call fail = token sai/hết hạn/thiếu scope.

- Không phải git repo → "Chạy `git init` và thêm một GitHub `origin` remote trước."
- Không có `origin` → "Thêm remote: `git remote add origin git@github.com:OWNER/REPO.git`."
- `GITHUB_TOKEN` thiếu hoặc `get_me` probe fail → "Đặt một **classic PAT** (scopes: `repo`, `project`, + `read:org` cho org board) vào `.env` (`GITHUB_TOKEN=…`), `source` nó trước khi khởi động Claude Code, rồi thử lại — fine-grained PAT chưa được verify cho Projects v2 user-owned board."

## 2. Xác định project

Suy ra `OWNER/REPO`, default branch, và owner — suy từ **local git** (MCP không biết checkout hiện tại thuộc repo GitHub nào):

```bash
git remote get-url origin               # parse OWNER/REPO từ URL
git rev-parse --abbrev-ref origin/HEAD  # default branch (vd origin/main → main)
```

- `OWNER/REPO` ← parse từ `git remote get-url origin` (SSH `git@github.com:OWNER/REPO.git`
  hoặc HTTPS `https://github.com/OWNER/REPO.git`); split theo `/` để lấy `OWNER` và `REPO`.
- `DEFAULT_BRANCH` ← `git rev-parse --abbrev-ref origin/HEAD` (bỏ prefix `origin/`); nếu không
  resolve được (chưa có `origin/HEAD`), **hỏi user** default branch.
- `PROJECT_OWNER` ← phần `OWNER` của remote. `PROJECT_OWNER_TYPE` (`org`|`user`): lấy own login
  qua MCP `get_me` (field `login`, cache 1 lần/session); nếu `OWNER == get_me.login` → `user`,
  ngược lại **hỏi user xác nhận** `org`|`user` (MCP không có tool suy trực tiếp owner_type).
- `PROJECT_NAME` ← `REPO` trừ khi user đưa tên thân thiện hơn.
- `PROJECT_SUMMARY` ← một one-liner ngắn trả lời "project này là gì?". Seed nó từ
  README của repo (local), rồi **hỏi user để xác nhận hoặc chỉnh**.
  Cái này đi vào `project.summary` và hiển thị trong `/status` và các README.

## 3. Kiểm tra env (chỉ presence — KHÔNG BAO GIỜ giá trị)

Verify mọi secret khai báo ở `env:` trong `${CLAUDE_PLUGIN_ROOT}/templates/agentflow.yaml.template` đều **present trong shell**:

```bash
[ -n "${GITHUB_TOKEN:-}" ] && echo "GITHUB_TOKEN: set" || echo "GITHUB_TOKEN: MISSING"
[ -n "${FIGMA_TOKEN:-}" ]  && echo "FIGMA_TOKEN: set"  || echo "FIGMA_TOKEN: absent"
```

- **`GITHUB_TOKEN` (required):** nếu chưa set → bảo user đặt nó vào `.env`
  (`cp .env.example .env`, điền `GITHUB_TOKEN=…`). Dùng **classic PAT** (scopes: `repo`, `project`,
  + `read:org` cho org board) — fine-grained PAT chưa được verify cho Projects v2 user-owned board;
  board-write smoke test của init (Step 11) là nơi phát hiện token sai loại. `source` nó trước khi
  khởi động Claude Code, rồi chạy lại. **Stop.**
- **`FIGMA_TOKEN` (optional, legacy only):** official Figma MCP server dùng **OAuth** (không token),
  nên cái này không bắt buộc. Để trống trừ khi chạy legacy Framelink/REST fallback; ghi chú và tiếp tục.

Không bao giờ print, log, hay interpolate giá trị token. Chỉ tham chiếu biến dưới dạng `${GITHUB_TOKEN}` /
`${FIGMA_TOKEN}`. Xem skill: **setup-agentflow** để biết env name map tới connections và MCP server ra sao.

## 4. Connections wizard

Xác nhận từng cái:

- **github** — luôn `enabled: true`. `repo` ← `OWNER/REPO`.
  `auth: { token_env: GITHUB_TOKEN, scopes: ["repo","read:org"] }`,
  `mcp: { server: "github", requires_env: ["GITHUB_TOKEN"] }`.
- **github_project** (REQUIRED) — hỏi: *tạo board mới* hoặc *link board có sẵn theo
  **number*** (không được skip — board là bắt buộc). Luôn `enabled: true` cho Step 7. Cần
  scope `project` trên `GITHUB_TOKEN`: nếu các board op (Step 7) fail vì thiếu quyền, bảo user
  thêm scope `project` vào classic PAT rồi cập nhật `.env` và **stop**.
  `auth.scopes: ["project","read:org"]`, `mcp: { server: "github", requires_env: ["GITHUB_TOKEN"] }`,
  cùng `owner`/`owner_type` từ Step 2.
- **figma** — nguồn design tùy chọn qua **official Figma MCP server (OAuth — no token)**. Đề nghị nó
  bất kể `FIGMA_TOKEN`. Nếu bật, set `enabled: true`,
  `auth: { method: oauth, fallback_token_env: FIGMA_TOKEN, docs: "/mcp → figma → Authenticate" }`,
  `mcp: { server: "figma" }`, và seed `connections.figma.files` bằng các file key đã biết
  (VD `[{ name: "Design System", key: "AbC123xyz" }]`), ngược lại `[]`. Bảo user authenticate một lần qua
  `/mcp → figma → Authenticate`. Nếu họ từ chối → `enabled: false`.

**Validate** mỗi connection đã enabled: xác nhận mọi var trong `auth.token_env` + `mcp.requires_env`
của nó đều present (chỉ presence, từ Step 3). Nếu một connection đã enabled thiếu var bắt buộc, cảnh
báo và hoặc disable nó hoặc dừng.

## 5. Phát hiện surface động

AgentFlow **tech-stack agnostic** và surfaces là một **OPEN MAP** — CHỈ khai báo những phần
repo này thực sự có, không có bộ cố định (một surface hoặc nhiều; **KHÔNG** giả định bộ ba
backend/frontend/mobile). Scan tìm marker, rồi **ĐỀ XUẤT** một surface key + path cho mỗi
phần detect được; user xác nhận, chỉnh, hoặc **đổi tên** từng cái.

```bash
ls package.json go.mod pom.xml build.gradle build.gradle.kts requirements.txt \
   pyproject.toml Gemfile Cargo.toml pubspec.yaml composer.json 2>/dev/null
ls -d android ios web frontend backend server api admin mobile app 2>/dev/null
```

Map mỗi marker tìm được sang một key gợi ý — surface KEY cuối cùng do user chọn (VD `backend`,
`web`, `api`, `admin`, `mobile`).

Quy tắc:
- Một **repo single-app** dùng một surface map tới `path: "."`.
- Surface **KHÔNG** khai báo build/lint/test command hay coverage — marker ở trên chỉ để chốt
  surface key + path; DEV và QC tự khám phá cách build/lint/test mỗi surface bị đụng theo
  convention của repo.

Với mỗi surface key `<s>` đã xác nhận, set `surfaces.<s>.label: "component/<s>"`.

## 6. Tạo labels

Tạo mọi AgentFlow label một cách idempotent. **Label không mang state** — label chỉ còn
classification: `type/*` (feat/bug/…), `component/*` (surface bị đụng), và aux `rework`; state sống
trong **Status field trên board** (Step 7). Luôn: **3** `type/*`, `rework` — CỘNG **một
`component/<surface>` cho mỗi surface khai báo ở Step 5** (các component label là động). Ý nghĩa nằm
trong skill: **project-board-protocol**. Với mỗi label, gọi `label_write` method=`create` (idempotent).
Trên lần chạy lại, dùng method=`update` để re-apply color/description thay vì báo lỗi
(params: `name` / `color` / `description`):

```
# type/* — green family
label_write  name="type/feature"     color=0E8A16  description="AgentFlow: new capability"
label_write  name="type/improvement" color=0E8A16  description="AgentFlow: enhancement"
label_write  name="type/bug"         color=0E8A16  description="AgentFlow: defect"

# component/<surface> — ONE per declared surface (loop over the Step 5 keys) — purple family
for s in <surface keys from Step 5>: label_write name="component/$s" color=5319E7 description="AgentFlow: $s surface"

# aux signal — amber
label_write  name="rework"              color=FBCA04  description="AgentFlow: QC-rejection rework trên Status 'Ready for Dev' → DEV đọc QC rejection mới nhất trước"
```

**Re-run trên repo cũ (di sản v0.3.x):** nếu `list_label` còn trả về label `flow:*` — state label
của AgentFlow < 1.0.0 — thì KHÔNG tạo lại chúng; đánh dấu để chạy **Migration** ở Step 7 sau khi
board đã validate xong.

## 7. Board (bắt buộc)

Điều khiển mọi chi tiết GitHub Projects v2 từ skill: **project-board-protocol** (phần GitHub Projects v2
board của nó). Board là **required**.

- **create** hoặc **link** (đã chọn ở Step 4):
  - *create*: gọi `projects_write` method=`create_project` (owner, owner_type, title) → tạo
    board **rỗng** (chỉ có title). Lưu project **number** vào `board.number`.
  - *link*: resolve board có sẵn theo number qua `projects_get` method=`get_project`.
- **Status field (7 option) — bước thủ công một lần:** MCP KHÔNG tạo được single-select
  field. Hướng dẫn user mở board trong GitHub UI → sửa/thêm **Status** field với đúng **7**
  option khớp `board.columns` **một-đối-một**. `board.columns` chính là **state enum
  authoritative**; các option name là **load-bearing wire value** được resolve by-name, nên đổi
  tên một option trong UI là break routing. Sau đó **validate** qua `projects_list`
  method=`list_project_fields` — assert Status field có đủ 7 option đúng tên
  (NEVER dùng `gh api graphql`).
- **Built-in workflows — thủ công-UI (không API nào config được):** hướng dẫn user mở Project
  settings → Workflows và bật:
  - **Item added to project** → Status: `Inbox`
  - **Item reopened** → Status: `Inbox`
  - **Item closed** → Status: `Done`

  Rationale (cạnh nào được phủ, same-value race, vì sao `/task` và PMO intake vẫn ghi
  Status="Inbox" explicit): reference §Create a board bước 3 của skill **project-board-protocol**.
- **`Status` field trên board LÀ state authoritative** cho routing — không có mirror, không có
  bản copy thứ hai; label không mang state (chỉ classification).
- Set `connections.github_project.enabled: true`.

### Migration từ v0.3.x — dọn state label `flow:*` di sản (chỉ khi re-run)

Chỉ chạy khi Step 6 phát hiện label `flow:*` còn tồn tại (repo đã init với AgentFlow < 1.0.0, thời
label còn mang state). Xác nhận với user trước khi migrate. Board phải đã validate xong ở trên
(Status field đủ 7 option) — backfill ghi qua đúng authoritative path:

1. **Backfill Status cho issue OPEN:** với mỗi label trong map di sản dưới đây, `list_issues`
   state=open filter theo label đó; với mỗi issue tìm thấy: `projects_write` method=`add_project_item`
   (idempotent — trả item có sẵn nếu đã tồn tại) rồi method=`update_project_item` set Status = column
   tương ứng (by-name shape — recipe canonical ở skill: **project-board-protocol**):

   | Label di sản                  | → `board.columns.<key>`                        |
   |-------------------------------|------------------------------------------------|
   | `flow:inbox`                  | `inbox` (vd "Inbox")                           |
   | `flow:ready-for-dev`          | `ready_for_dev` (vd "Ready for Dev")           |
   | `flow:in-progress`            | `in_progress` (vd "In Progress")               |
   | `flow:in-qc`                  | `in_qc` (vd "In QC")                           |
   | `flow:refined`                | `refined` (vd "Refined")                       |
   | `flow:ready-for-human-review` | `ready_for_human_review` (vd "Ready for Human Review") |
   | `flow:done`                   | `done` (vd "Done")                             |

2. **Gỡ label `flow:*` khỏi issue** — CHỈ SAU khi Status của issue đó đã ghi thành công (Status
   trước, gỡ label sau: crash giữa chừng thì label thừa vô hại và đánh dấu chính xác các issue
   chưa backfill; gỡ trước mà crash là mất state). `issue_write` method=`update` với `labels` =
   set hiện tại trừ label `flow:*` (full-replacement — đọc set hiện tại trước).

3. **Xóa 7 label definition** — toolset `labels` của MCP không có delete, dùng `gh` qua Bash.
   Check `command -v gh` trước (`gh` đọc `GITHUB_TOKEN` từ env — không cần auth thêm); nếu `gh`
   vắng mặt → fallback: hướng dẫn user xóa 7 label `flow:*` trong GitHub UI (Issues → Labels)
   rồi chạy lại verify (Step 11):

   ```bash
   command -v gh   # vắng mặt → xóa 7 label flow:* trong GitHub UI rồi chạy lại verify
   for l in inbox ready-for-dev in-progress in-qc refined ready-for-human-review done; do
     gh label delete "flow:$l" --yes
   done
   ```

   Issue CLOSED bỏ qua backfill (terminal — không cần routing); bước này tự gỡ label khỏi chúng
   khi xóa definition.

4. **Refresh yaml:** Step 9 ghi lại config theo template mới — block `labels.flow` di sản biến mất.

## 8. Scaffold project skills (opt-in)

Đề nghị tạo các skill stub khởi đầu có **role-prefix** dưới `.claude/skills/`, đặt tên
`<role>-<area>` để đúng agent nhặt được: `dev-*` → DEV, `qc-*` → QC, `pmo-*` → PMO.
**Luôn scaffold `qc-automation-test` mặc định** — skill authoring của QC, mà nó load để thêm
các test ID mà suite cần và author các test flow trên PR branch — và đăng ký nó trong `skills:`.
Đề xuất phần còn lại khớp với các surface đã detect, VD `dev-<surface>-development` cho mỗi surface và
`pmo-discovery`. **Hỏi trước khi tạo các stub đề nghị.** Với mỗi stub được chấp nhận, ghi một
`SKILL.md` với YAML frontmatter (`name` = tên directory) + một description ngắn + một TODO body.

Rồi **register** từng cái vào map `skills:` trong yaml với `{ role, surfaces?, description? }`. Một agent
load các skill role-prefix liên quan tới (các) surface mà issue hiện tại đụng (`surfaces` trong registry
khớp với các label `component/*` của issue; không liệt kê hoặc không có `surfaces` = luôn liên quan).
Xem skill: **setup-agentflow**.

Liệt kê chính xác cái gì đã được tạo. Nếu user từ chối các stub đề nghị, `skills:` vẫn liệt kê `qc-automation-test`.

## 9. Sinh config

Ghi `.claude/agentflow.yaml` bằng cách copy `${CLAUDE_PLUGIN_ROOT}/templates/agentflow.yaml.template`
và thay **mọi** placeholder, ghi các **dynamic surfaces**, **skills registry** (Step 8), và
**full connection spec** (Step 4). Đọc template để xác nhận đủ bộ — không đọc được template →
STOP, không tự dựng yaml từ trí nhớ:

```bash
mkdir -p .claude
```

| Placeholder                                 | Giá trị                                                      |
|---------------------------------------------|--------------------------------------------------------------|
| `agentflow_version`                         | KHÔNG phải placeholder — template pin sẵn `1.0.0` (config-format/protocol version); copy nguyên văn, KHÔNG substitute từ `plugin.json` |
| `{{PROJECT_NAME}}`                          | tên project (default = REPO)                                 |
| `{{PROJECT_SUMMARY}}`                       | one-liner đã xác nhận từ Step 2                              |
| `{{OWNER}}` / `{{REPO}}`                     | từ Step 2 (`project.repo` và `connections.github.repo`)      |
| `{{DEFAULT_BRANCH}}`                        | default branch từ Step 2                                     |
| `{{PROJECT_OWNER}}` / `{{PROJECT_OWNER_TYPE}}` | owner login / `org`\|`user`                               |
| `{{FIGMA_ENABLED}}`                         | `true` nếu user bật figma (OAuth — không cần token)          |
| `{{BOARD_NUMBER}}`                          | board project number từ Step 7 (một integer thật, không bao giờ rỗng)|
| `surfaces:` block                           | một block cho mỗi surface **detect được** (Step 5): `path`, `label`, `forbidden_paths`. Xóa hoàn toàn surface example/placeholder của template. |
| `labels.component`                          | một `<surface>: "component/<surface>"` cho mỗi surface đã khai báo |
| `skills:`                                   | registry ở Step 8, hoặc `{}`                                 |

Giữ nguyên các comment đã curate từ template. Đừng bịa ra key mà
template không có. Xác nhận mọi `surfaces.<s>.label` có một entry `labels.component.<s>` khớp và
một label `component/<s>` đã tạo.

## 10. Sinh README

Ghi `README.agentflow.md` vào repo root từ `${CLAUDE_PLUGIN_ROOT}/templates/README.project.md`:
substitute 3 placeholder `{{PROJECT_NAME}}`, `{{PROJECT_SUMMARY}}` (Step 2), `{{BOARD_NUMBER}}`
(Step 7) khi copy, còn lại copy nguyên văn. Đây là quick reference theo từng repo, trỏ user tới
`/start`, `/task`, `/status`, và việc chạy lại `/agentflow-init`.

## 11. Verify (BẮT BUỘC — đây là nơi bắt payload lỗi)

```bash
# yaml parses (giữ python)
python3 -c "import yaml; yaml.safe_load(open('.claude/agentflow.yaml'))" && echo "yaml: ok"
```

- **Labels exist:** gọi `list_label` và kiểm đủ **3** `type/*`, một `component/*`
  cho mỗi surface, và `rework` — và **không còn** label `flow:*` nào (còn → Migration ở Step 7
  chưa chạy hoặc chưa xong).
- **Board resolve:** `projects_get` method=`get_project` (theo `board.number`) + `projects_list`
  method=`list_project_fields` (đủ 7 option Status) — giao cho skill: **project-board-protocol** làm
  lookup — và `board.number` khớp `connections.github_project.enabled`.

### Board write smoke test — bắt buộc, KHÔNG hỏi consent

Board resolve được **không** chứng minh AgentFlow ghi được vào nó. Read-only check bỏ sót cả một class
lỗi payload — và Status write giờ là **authoritative path, mandatory-success** (fail-stop): một
`updated_field` sai shape sẽ dừng pipeline ngay ở ticket thật đầu tiên. Chạy trọn vòng dưới đây trên
một issue bỏ đi để bắt lỗi đó ngay lúc init — nó **phải** xanh trước khi init báo thành công. Đây là
lần duy nhất trong đời một repo mà authoritative write path được kiểm chứng end-to-end trước khi có
ticket thật phụ thuộc vào nó.

```
# 1. issue tạm
issue_write method=create title="AgentFlow setup check" body="temporary — safe to close"
#   → #<n>

# 2. add lên board  → item_id
projects_write method=add_project_item
  owner=<owner> owner_type=<org|user> project_number=<board.number>
  item_type=issue item_owner=<owner> item_repo=<repo> issue_number=<n>

# 3. set Status=Inbox — BY-NAME shape (recipe canonical: skill project-board-protocol)
projects_write method=update_project_item
  owner=<owner> owner_type=<org|user> project_number=<board.number>
  item_owner=<owner> item_repo=<repo> issue_number=<n>
  updated_field={ name: "Status", value: "<board.columns.inbox>" }

# 4. READ-BACK — thiếu bước này thì bước 3 không chứng minh được gì
projects_get method=get_project_item item_id=<item_id> field_names=["Status"]
#   → assert Status == "<board.columns.inbox>"

# 5. transition Inbox → Refined, read-back lần nữa
projects_write method=update_project_item ... updated_field={ name: "Status", value: "<board.columns.refined>" }
projects_get   method=get_project_item item_id=<item_id> field_names=["Status"]
#   → assert Status == "<board.columns.refined>"

# 6. dọn dẹp (chạy KỂ CẢ khi 4/5 fail — dọn trước, báo lỗi sau)
projects_write method=delete_project_item owner=<owner> project_number=<board.number> item_id=<item_id>
issue_write    method=update state=closed
```

**Bước 4/5 fail → STOP**, và báo user đúng nguyên nhân:

| Triệu chứng | Nguyên nhân | Fix |
|---|---|---|
| `option_not_found` (kèm candidates) | Tên option Status trên board không khớp `board.columns` | Sửa trong GitHub UI cho khớp **một-đối-một**, chạy lại `/agentflow-init` |
| Lỗi khác về `updated_field` | Sai shape — by-id shape không resolve được option theo tên | Dùng **by-name** shape; recipe canonical ở skill: **project-board-protocol**. Không tự chế shape khác. |
| Status read-back rỗng/vắng | Thiếu `field_names:["Status"]` ở call read | Luôn truyền `field_names` |

## 12. Tóm tắt

In ra một report gọn:

```
AgentFlow initialized on <OWNER/REPO> (protocol v<agentflow_version từ template, vd 1.0.0>)

Project     : <name> — <summary>
Connections : github ✓   github_project on board #<N>   figma <on (OAuth) | off>
Env         : GITHUB_TOKEN set ✓   FIGMA_TOKEN <set | absent>
Surfaces    : <key>=<path> [, <key>=<path> …]   (only the surfaces that exist)
Labels      : <4 + N> created/updated (type/* ·3, component/* ·N, rework ·1)
Board       : #<N> — Status field 7 option (state authoritative), built-in workflows đã hướng dẫn bật
Migration   : <chỉ khi re-run repo v0.3.x: X issue backfill Status, 7 label flow:* đã xóa>
Skills      : <scaffolded role-prefixed stubs, or none>
Files       : .claude/agentflow.yaml, README.agentflow.md, [.claude/skills/<role>-* …]

Next: run /start to enter team mode, then /task <description> to file your first item.
```
