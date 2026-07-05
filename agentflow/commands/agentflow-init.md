---
description: Bootstrap AgentFlow trong repo hiện tại — resolve project + summary, wire connections (full auth/MCP spec), detect các surface đang tồn tại, tạo các label flow:*/type/*/component/*, một board bắt buộc, tùy chọn scaffold project skills có role-prefix, rồi ghi .claude/agentflow.yaml + README.agentflow.md.
argument-hint: (không có args — chạy một setup wizard tương tác)
---

Bạn đang bootstrap **AgentFlow** trong repository HIỆN TẠI của user. Đây là setup một
lần, nhưng nó **idempotent và chạy lại được** — user chạy lại để re-detect surfaces,
thêm board sau, đăng ký skill mới, hoặc refresh env/connections. Không bao giờ hủy một
`.claude/agentflow.yaml` đã sửa tay mà không cảnh báo; nếu đã có, đọc nó, coi các value của nó
là default cho mỗi bước bên dưới, và xác nhận trước khi ghi đè.

File `.claude/agentflow.yaml` được sinh ra là **the single source of truth** của project —
connections, secrets, surfaces, skills, labels và board đều nằm ở đó. Đọc schema chuẩn
tại `templates/agentflow.yaml.template` trước khi ghi.

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
- `GITHUB_TOKEN` thiếu hoặc `get_me` probe fail → "Đặt một fine-grained PAT vào `.env` (`GITHUB_TOKEN=…`), `source` nó trước khi khởi động Claude Code, rồi thử lại."

Các MCP server `github` và `figma` là các server **HTTP** (hosted GitHub remote; official Figma
server) — không cần install Node/`npx`. Server `figma` tùy chọn đăng nhập qua OAuth
(`/mcp` → figma → Authenticate) sau khi plugin load.

## 2. Xác định project

Suy ra `OWNER/REPO`, default branch, và owner từ **local git** (MCP không có repo-read tool):

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

List `env:` trong `templates/agentflow.yaml.template` khai báo mọi secret theo NAME, kèm
`required` và `used_by`. Verify từng cái **present trong shell** — kiểm tra presence, không bao giờ giá trị:

```bash
[ -n "${GITHUB_TOKEN:-}" ] && echo "GITHUB_TOKEN: set" || echo "GITHUB_TOKEN: MISSING"
[ -n "${FIGMA_TOKEN:-}" ]  && echo "FIGMA_TOKEN: set"  || echo "FIGMA_TOKEN: absent"
```

- **`GITHUB_TOKEN` (required):** nếu chưa set → bảo user đặt nó vào `.env`
  (`cp .env.example .env`, điền `GITHUB_TOKEN=…` bằng một fine-grained PAT, scopes `repo` + `read:org`
  + `project`), `source` nó trước khi khởi động Claude Code, rồi chạy lại. **Stop.**
- **`FIGMA_TOKEN` (optional, legacy only):** official Figma MCP server dùng **OAuth** (không token),
  nên cái này không bắt buộc. Để trống trừ khi chạy legacy Framelink/REST fallback; ghi chú và tiếp tục.

Không bao giờ print, log, hay interpolate giá trị token. Chỉ tham chiếu biến dưới dạng `${GITHUB_TOKEN}` /
`${FIGMA_TOKEN}`. Xem skill: **setup-agentflow** để biết env name map tới connections và MCP server ra sao.

## 4. Connections wizard

Mỗi connection được **khai báo đầy đủ tại một chỗ** — `auth` (token_env + scopes/cli|docs) và,
khi service có MCP server, `mcp` (server key trong `.mcp.json` + `requires_env`). Một
connection chỉ dùng được khi `enabled: true` VÀ mọi var trong requirements auth/mcp của nó đều
present. Xác nhận từng cái:

- **github** — luôn `enabled: true`. `repo` ← `OWNER/REPO`.
  `auth: { token_env: GITHUB_TOKEN, scopes: ["repo","read:org"], docs: "fine-grained PAT trong .env" }`,
  `mcp: { server: "github", requires_env: ["GITHUB_TOKEN"] }`.
- **github_project** (REQUIRED) — hỏi: *tạo board mới* hoặc *link board có sẵn theo
  **number*** (không được skip — board là bắt buộc). Luôn `enabled: true` cho Step 7. Cần
  scope `project` trên `GITHUB_TOKEN`: nếu các board op (Step 7) fail vì thiếu quyền, bảo user
  thêm scope `project` vào fine-grained PAT rồi cập nhật `.env` và **stop**.
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
báo và hoặc disable nó hoặc dừng. Bảo user rằng họ có thể copy một connection block trong yaml để thêm
service khác sau này (xem skill: **setup-agentflow**).

## 5. Phát hiện surface động

AgentFlow **tech-stack agnostic** và surfaces là một **OPEN MAP** — CHỈ khai báo những phần
repo này thực sự có. **KHÔNG** giả định bộ ba backend/frontend/mobile: một repo có thể chỉ
backend, chỉ frontend, chỉ mobile, hoặc bất kỳ mix nào. Scan tìm marker, rồi **ĐỀ XUẤT** một
surface key + path cho mỗi phần detect được; user xác nhận, chỉnh, hoặc **đổi tên** từng cái.

```bash
ls package.json go.mod pom.xml build.gradle build.gradle.kts requirements.txt \
   pyproject.toml Gemfile Cargo.toml pubspec.yaml composer.json 2>/dev/null
ls -d android ios web frontend backend server api admin mobile app 2>/dev/null
```

Map marker sang gợi ý (minh họa, không đầy đủ — thích ứng theo cái bạn tìm thấy; surface KEY do
user chọn, VD `backend`, `web`, `api`, `admin`, `mobile`):

| Marker                                   | Key gợi ý     |
|------------------------------------------|---------------|
| `package.json` (web deps)                | web/frontend  |
| `go.mod`                                 | backend/api   |
| `pom.xml`, `build.gradle`                | backend       |
| `requirements.txt`, `pyproject.toml`     | backend/api   |
| `Gemfile`                                | backend       |
| `Cargo.toml`                             | backend       |
| `pubspec.yaml`, `android/`, `ios/`       | mobile        |
| `composer.json`                          | backend       |

Quy tắc:
- Chỉ ghi **CÁC surface thực sự tồn tại** vào config. Không có bộ cố định — một surface hoặc nhiều.
- Một **repo single-app** dùng một surface map tới `path: "."`.
- Surface **KHÔNG** khai báo build/lint/test command hay coverage nữa. DEV và QC tự khám phá cách
  build/lint/test mỗi surface bị đụng theo convention của repo (`package.json` scripts, `Makefile`,
  `pubspec`, `go.mod`, CI config…) và tự phán đoán — marker ở trên chỉ để chốt surface key + path.

Với mỗi surface key `<s>` đã xác nhận, set `surfaces.<s>.label: "component/<s>"`. Map
`labels.component` sau đó được **sinh cho khớp** — một `component/<surface>` cho mỗi surface đã
khai báo (Step 6 / Step 8).

```yaml
# example: a backend-only repo declares exactly one surface
surfaces:
  api:
    path: "."
    label: "component/api"
    forbidden_paths: []
```

## 6. Tạo labels

Tạo mọi AgentFlow label một cách idempotent. Luôn: **7** `flow:*`, **3** `type/*`,
`rework` — CỘNG **một `component/<surface>` cho mỗi surface
khai báo ở Step 5** (các component label là động). Ý nghĩa nằm trong skill: **project-board-protocol**.
Với mỗi label, gọi `label_write` method=`create` (idempotent). Trên lần chạy lại, dùng
method=`update` để re-apply color/description thay vì báo lỗi (params: `name` / `color` / `description`):

```
# flow:* (state machine — exactly one per active issue) — blue family
label_write  name="flow:inbox"                  color=1D76DB  description="AgentFlow: triage + DoR gate"
label_write  name="flow:ready-for-dev"          color=1D76DB  description="AgentFlow: DEV queue"
label_write  name="flow:in-progress"            color=1D76DB  description="AgentFlow: DEV coding (in-flight; claim held)"
label_write  name="flow:in-qc"                  color=1D76DB  description="AgentFlow: QC reviewing"
label_write  name="flow:refined"                color=D93F0B  description="AgentFlow: human-intervention parking (owner: human)"
label_write  name="flow:ready-for-human-review" color=1D76DB  description="AgentFlow: human review/merge"
label_write  name="flow:done"                   color=1D76DB  description="AgentFlow: terminal"

# type/* — green family
label_write  name="type/feature"     color=0E8A16  description="AgentFlow: new capability"
label_write  name="type/improvement" color=0E8A16  description="AgentFlow: enhancement"
label_write  name="type/bug"         color=0E8A16  description="AgentFlow: defect"

# component/<surface> — ONE per declared surface (loop over the Step 5 keys) — purple family
for s in <surface keys from Step 5>: label_write name="component/$s" color=5319E7 description="AgentFlow: $s surface"

# aux signal — amber
label_write  name="rework"              color=FBCA04  description="AgentFlow: QC-rejection rework on flow:ready-for-dev → DEV đọc QC rejection mới nhất trước"
```

(Feedback PR review của con người **không** dùng aux label: con người tự chuyển ticket về
`flow:inbox` và PMO re-triage đọc PR feedback — xem skill: **project-board-protocol**.)

**Không** tạo `component/*` label cho surface mà repo không có — chúng phải mirror chính xác các
key `surfaces:` đã khai báo.

## 7. Board (bắt buộc)

Điều khiển mọi chi tiết GitHub Projects v2 từ skill: **project-board-protocol** (phần GitHub Projects v2
board của nó). Board là **required** — nó là inbox queue của orchestrator + mirror mà con người
thấy được; label `flow:*` vẫn authoritative cho routing.

- **create** hoặc **link** (đã chọn ở Step 4):
  - *create*: gọi `projects_write` method=`create_project` (owner, owner_type, title) → tạo
    board **rỗng** (chỉ có title). Lưu project **number** vào `board.number`.
  - *link*: resolve board có sẵn theo number qua `projects_get` method=`get_project`.
- **Status field (7 option) — bước thủ công một lần:** MCP KHÔNG tạo được single-select
  field. Hướng dẫn user mở board trong GitHub UI → thêm một **Status** field với đúng **7**
  option khớp `board.columns` (mirror các label `flow:*`). Sau đó **validate** qua
  `projects_list` method=`list_project_fields` — assert Status field có đủ 7 option đúng tên
  (NEVER dùng `gh api graphql`).
- Mirror các label `flow:*` sang Status field là **CHỈ HUMAN MIRROR** — labels vẫn authoritative.
- Set `connections.github_project.enabled: true`.

`board.number` luôn là một project number thật và `connections.github_project.enabled` luôn
`true` — giữ chúng **in sync**.

## 8. Scaffold project skills (opt-in)

Đề nghị tạo các skill stub khởi đầu có **role-prefix** dưới `.claude/skills/`, đặt tên
`<role>-<area>` để đúng agent nhặt được: `dev-*` → DEV, `qc-*` → QC, `pmo-*` → PMO.
**Luôn scaffold `qc-automation-test` mặc định** — skill authoring của QC, mà nó load để thêm
các test ID mà suite cần và author các test flow trên PR branch — và đăng ký nó trong `skills:`.
Đề xuất phần còn lại khớp với các surface đã detect, VD `dev-<surface>-development` cho mỗi surface và
`pmo-discovery`. **Hỏi trước khi tạo các stub đề nghị.** Với mỗi stub được chấp nhận, ghi một
`SKILL.md` với YAML frontmatter (`name` = tên directory) + một description ngắn + một TODO body:

```markdown
---
name: dev-api-development
description: API surface conventions for DEV — TODO: fill in.
---

# dev-api-development

TODO: document this project's API conventions, patterns, and gotchas DEV should follow.
```

Rồi **register** từng cái vào map `skills:` trong yaml với `{ role, surfaces?, description? }` — registry
này là the single source of truth / tổng quan. Các agent cũng tự auto-discover bất kỳ
`.claude/skills/<their-role>-*` kể cả khi không liệt kê; một agent load các skill role-prefix liên quan
tới (các) surface mà issue hiện tại đụng (`surfaces` trong registry khớp với các label
`component/*` của issue; không liệt kê hoặc không có `surfaces` = luôn liên quan). Xem skill: **setup-agentflow**.

```yaml
skills:
  dev-api-development: { role: dev, surfaces: ["api"], description: "API surface conventions" }
  qc-automation-test:  { role: qc,  description: "E2E suite authoring" }
  pmo-discovery:       { role: pmo, description: "Discovery & story-mapping checklist" }
```

Liệt kê chính xác cái gì đã được tạo. Nếu user từ chối các stub đề nghị, `skills:` vẫn liệt kê `qc-automation-test`.

## 9. Sinh config

Ghi `.claude/agentflow.yaml` bằng cách copy `templates/agentflow.yaml.template` và thay
**mọi** placeholder, ghi các **dynamic surfaces**, **skills registry** (Step 8), và
**full connection spec** (Step 4). Đọc template để xác nhận đủ bộ; tính đến v0.1.0:

```bash
mkdir -p .claude
```

| Placeholder                                 | Giá trị                                                      |
|---------------------------------------------|--------------------------------------------------------------|
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
template không có. Xác nhận `{{BOARD_NUMBER}}` là một board number thật (board là bắt buộc), và rằng
mọi `surfaces.<s>.label` có một entry `labels.component.<s>` khớp và một label `component/<s>` đã tạo.

## 10. Sinh README

Ghi `README.agentflow.md` vào repo root từ `templates/README.project.md` (thay các value riêng
của project, còn lại copy nguyên văn). Đây là quick reference theo từng repo, trỏ user tới
`/start`, `/task`, `/status`, và việc chạy lại `/agentflow-init`.

## 11. Verify (smoke check nhẹ)

```bash
# yaml parses (giữ python)
python3 -c "import yaml; yaml.safe_load(open('.claude/agentflow.yaml'))" && echo "yaml: ok"
```

- **Labels exist:** gọi `list_label` và kiểm đủ **7** `flow:*`, **3** `type/*`, một `component/*`
  cho mỗi surface, và `rework`.
- Nếu một board đã được tạo/link, xác nhận nó resolve được qua `projects_get` method=`get_project`
  (theo `board.number`) và `projects_list` method=`list_project_fields` (đủ 7 option Status) —
  giao cho skill: **project-board-protocol** làm lookup — và rằng `board.number` khớp với
  `connections.github_project.enabled`.
- Kiểm tra label end-to-end **tùy chọn** — **hỏi user trước**: tạo một issue bỏ đi, thêm
  `flow:inbox`, đổi nó sang `flow:refined`, rồi close. Dọn dẹp sau khi xong; không bao giờ để lại
  test artifact mà không nói cho user.

```
# only with user consent
issue_write  method=create   title="AgentFlow setup check"  body="temporary — safe to close"  labels=["flow:inbox"]
# ...swap label flow:inbox → flow:refined để chứng minh transition (full-set):
issue_write  method=update   labels=["flow:refined"]        # (giữ mọi aux; ở đây issue chỉ có 1 flow label)
# ...rồi close + comment:
issue_write  method=update   state=closed
add_issue_comment  body="AgentFlow verification complete."
```

## 12. Tóm tắt

In ra một report gọn:

```
AgentFlow initialized on <OWNER/REPO> (v0.1.0)

Project     : <name> — <summary>
Connections : github ✓   github_project on board #<N>   figma <on (OAuth) | off>
Env         : GITHUB_TOKEN set ✓   FIGMA_TOKEN <set | absent>
Surfaces    : <key>=<path> [, <key>=<path> …]   (only the surfaces that exist)
Labels      : <11 + N> created/updated (flow:* ·7, type/* ·3, component/* ·N, rework ·1)
Board       : #<N>
Skills      : <scaffolded role-prefixed stubs, or none>
Files       : .claude/agentflow.yaml, README.agentflow.md, [.claude/skills/<role>-* …]

Next: run /start to enter team mode, then /task <description> to file your first item.
```

---

**Re-runs:** an toàn bất cứ lúc nào. Re-detect surfaces, re-link hoặc tạo lại board, đăng ký skill mới,
hoặc refresh connections/env — mỗi bước tái dùng các value `.claude/agentflow.yaml` hiện có làm
default và hỏi trước khi ghi đè. Labels và board (nếu có) được reconcile một cách idempotent.
