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
git rev-parse --is-inside-work-tree     # must be a git repo
git remote get-url origin               # must resolve to a GitHub remote
gh auth status                          # must be authenticated
```

- Không phải git repo → "Chạy `git init` và thêm một GitHub `origin` remote trước."
- Không có `origin` → "Thêm remote: `git remote add origin git@github.com:OWNER/REPO.git`."
- `gh` chưa authenticate → "Chạy `gh auth login` (cùng account với token của bạn) rồi thử lại."

Các MCP server `github` và `figma` là các server **HTTP** (hosted GitHub remote; official Figma
server) — không cần install Node/`npx`. Server `figma` tùy chọn đăng nhập qua OAuth
(`/mcp` → figma → Authenticate) sau khi plugin load.

## 2. Xác định project

Suy ra `OWNER/REPO`, default branch, và owner từ remote và `gh`:

```bash
gh repo view --json nameWithOwner,defaultBranchRef,owner,description \
  -q '{repo: .nameWithOwner, branch: .defaultBranchRef.name, owner: .owner.login, type: .owner.type, desc: .description}'
```

- `OWNER/REPO` ← `nameWithOwner`; split theo `/` để lấy `OWNER` và `REPO`.
- `DEFAULT_BRANCH` ← `defaultBranchRef.name`.
- `PROJECT_OWNER` ← `owner.login`; `PROJECT_OWNER_TYPE` ← `Organization` → `org`, ngược lại `user`.
- `PROJECT_NAME` ← `REPO` trừ khi user đưa tên thân thiện hơn.
- `PROJECT_SUMMARY` ← một one-liner ngắn trả lời "project này là gì?". Seed nó từ
  `description` của repo (hoặc liếc qua README), rồi **hỏi user để xác nhận hoặc chỉnh**.
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
  `auth: { token_env: GITHUB_TOKEN, scopes: ["repo","read:org"], cli: "gh auth login" }`,
  `mcp: { server: "github", requires_env: ["GITHUB_TOKEN"] }`.
- **github_project** (REQUIRED) — hỏi: *tạo board mới* hoặc *link board có sẵn theo
  id/number* (không được skip — board là bắt buộc). Luôn `enabled: true` cho Step 7. Cần
  scope `project` trên `GITHUB_TOKEN`: verify nó và, nếu thiếu, bảo user chạy
  `gh auth refresh -s project` rồi **stop**.
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
surface key + path + commands cho mỗi phần detect được; user xác nhận, chỉnh, hoặc **đổi tên** từng cái.

```bash
ls package.json go.mod pom.xml build.gradle build.gradle.kts requirements.txt \
   pyproject.toml Gemfile Cargo.toml pubspec.yaml composer.json 2>/dev/null
ls -d android ios web frontend backend server api admin mobile app 2>/dev/null
```

Map marker sang gợi ý (minh họa, không đầy đủ — thích ứng theo cái bạn tìm thấy; surface KEY do
user chọn, VD `backend`, `web`, `api`, `admin`, `mobile`):

| Marker                                   | Key gợi ý     | Commands gợi ý (xác nhận với user)                   |
|------------------------------------------|---------------|------------------------------------------------------|
| `package.json` (web deps)                | web/frontend  | `npm ci` / `npm run lint` / `npm test` / `npm run build` |
| `go.mod`                                 | backend/api   | `go mod download` / `go vet ./...` / `go test ./...` / `go build ./...` |
| `pom.xml`, `build.gradle`                | backend       | `mvn -q install -DskipTests` / `mvn checkstyle:check` / `mvn test` / `mvn package` |
| `requirements.txt`, `pyproject.toml`     | backend/api   | `pip install -e .` / `ruff check` / `pytest` / `python -m build` |
| `Gemfile`                                | backend       | `bundle install` / `rubocop` / `rspec` |
| `Cargo.toml`                             | backend       | `cargo fetch` / `cargo clippy` / `cargo test` / `cargo build` |
| `pubspec.yaml`, `android/`, `ios/`       | mobile        | `flutter pub get` / `flutter analyze` / `flutter test` / `flutter build` |
| `composer.json`                          | backend       | `composer install` / `phpcs` / `phpunit` |

Quy tắc:
- Chỉ ghi **CÁC surface thực sự tồn tại** vào config. Không có bộ cố định — một surface hoặc nhiều.
- Một **repo single-app** dùng một surface map tới `path: "."`.
- Để trống một command bất kỳ bằng `""` để skip (VD chưa có `integration`/`e2e`).
- `coverage_command` phải in RA MỘT số 0–100 lên stdout, hoặc `""` để skip; set `coverage_threshold`
  theo từng surface (hoặc `0` để defer sang `agents.qc.coverage_threshold`).
- Các **tier** của QC (`quick` ⊆ `full` ⊆ `regression`) là danh sách command-*type*, không phải shell
  command — các shell command bạn thu thập ở đây là cái mà các tier đó invoke cho mỗi surface bị đụng.
  Để nguyên định nghĩa tier ở template default trừ khi user yêu cầu khác.

Với mỗi surface key `<s>` đã xác nhận, set `surfaces.<s>.label: "component/<s>"`. Map
`labels.component` sau đó được **sinh cho khớp** — một `component/<surface>` cho mỗi surface đã
khai báo (Step 6 / Step 8).

```yaml
# example: a backend-only repo declares exactly one surface
surfaces:
  api:
    path: "."
    label: "component/api"
    commands: { install: "go mod download", lint: "go vet ./...", test: "go test ./...", integration: "", e2e: "", build: "go build ./..." }
    coverage_command: ""
    coverage_threshold: 0
    forbidden_paths: []
```

## 6. Tạo labels

Tạo mọi AgentFlow label một cách idempotent. Luôn: **7** `flow:*`, **3** `type/*`,
`rework`, `human-changes` — CỘNG **một `component/<surface>` cho mỗi surface
khai báo ở Step 5** (các component label là động). Ý nghĩa nằm trong skill: **project-board-protocol**.
Dùng `--force` để lần chạy lại update color/description thay vì báo lỗi:

```bash
# flow:* (state machine — exactly one per active issue) — blue family
gh label create "flow:inbox"                  --color 1D76DB --description "AgentFlow: triage + DoR gate"       --force
gh label create "flow:ready-for-dev"          --color 1D76DB --description "AgentFlow: DEV queue"              --force
gh label create "flow:in-progress"            --color 1D76DB --description "AgentFlow: DEV coding (in-flight; claim held)" --force
gh label create "flow:in-qc"                  --color 1D76DB --description "AgentFlow: QC reviewing"           --force
gh label create "flow:refined"                --color D93F0B --description "AgentFlow: human-intervention parking (owner: human)" --force
gh label create "flow:ready-for-human-review" --color 1D76DB --description "AgentFlow: human review/merge"     --force
gh label create "flow:done"                   --color 1D76DB --description "AgentFlow: terminal"               --force

# type/* — green family
gh label create "type/feature"     --color 0E8A16 --description "AgentFlow: new capability"  --force
gh label create "type/improvement" --color 0E8A16 --description "AgentFlow: enhancement"     --force
gh label create "type/bug"         --color 0E8A16 --description "AgentFlow: defect"          --force

# component/<surface> — ONE per declared surface (loop over the Step 5 keys) — purple family
for s in <surface keys from Step 5>; do
  gh label create "component/$s" --color 5319E7 --description "AgentFlow: $s surface" --force
done

# aux signals — amber / red
gh label create "rework"              --color FBCA04 --description "AgentFlow: QC-rejection rework on flow:ready-for-dev → DEV đọc QC rejection mới nhất trước" --force
gh label create "human-changes"       --color D93F0B --description "AgentFlow: human Request-changes review on PR → DEV rework" --force
```

**Không** tạo `component/*` label cho surface mà repo không có — chúng phải mirror chính xác các
key `surfaces:` đã khai báo.

## 7. Board (bắt buộc)

Điều khiển mọi chi tiết GitHub Projects v2 từ skill: **project-board-protocol** (phần GitHub Projects v2
board của nó). Board là **required** — nó là inbox queue của orchestrator + mirror mà con người
thấy được; label `flow:*` vẫn authoritative cho routing.

- **create** hoặc **link** (đã chọn ở Step 4) → skill đó tạo/link board, mirror các label
  `flow:*` sang một Status field (CHỈ HUMAN MIRROR — labels vẫn authoritative), và trả về
  **node id** của board (`PVT_…`). Lưu nó ở `board.id` và set
  `connections.github_project.enabled: true`.

`board.id` luôn là một `PVT_…` thật và `connections.github_project.enabled` luôn `true` —
giữ chúng **in sync**.

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
| `{{PROJECT_ID}}`                            | board node id từ Step 7 (luôn là `PVT_…` thật, không bao giờ rỗng)|
| `surfaces:` block                           | một block cho mỗi surface **detect được** (Step 5): `path`, `label`, sáu `commands`, `coverage_command`, `coverage_threshold`, `forbidden_paths`. Xóa hoàn toàn surface example/placeholder của template. |
| `labels.component`                          | một `<surface>: "component/<surface>"` cho mỗi surface đã khai báo |
| `skills:`                                   | registry ở Step 8, hoặc `{}`                                 |
| `{{COVERAGE_THRESHOLD}}`                    | fallback `agents.qc.coverage_threshold` (VD `0` để disable)  |

Giữ nguyên các comment đã curate và tier default từ template. Đừng bịa ra key mà
template không có. Xác nhận `{{PROJECT_ID}}` là một board id `PVT_…` thật (board là bắt buộc), và rằng
mọi `surfaces.<s>.label` có một entry `labels.component.<s>` khớp và một label `component/<s>` đã tạo.

## 10. Sinh README

Ghi `README.agentflow.md` vào repo root từ `templates/README.project.md` (thay các value riêng
của project, còn lại copy nguyên văn). Đây là quick reference theo từng repo, trỏ user tới
`/start`, `/task`, `/status`, và việc chạy lại `/agentflow-init`.

## 11. Verify (smoke check nhẹ)

```bash
# yaml parses
python3 -c "import yaml; yaml.safe_load(open('.claude/agentflow.yaml'))" && echo "yaml: ok"
# labels exist: 7 flow:*, 3 type/*, one component/* per surface, rework, human-changes
gh label list --json name -q '.[].name' | grep -E '^(flow:|type/|component/|rework|human-changes)' | sort
```

- Nếu một board đã được tạo/link, xác nhận nó resolve được (giao cho skill: **project-board-protocol**
  làm lookup) và rằng `board.id` khớp với `connections.github_project.enabled`.
- Kiểm tra label end-to-end **tùy chọn** — **hỏi user trước**: tạo một issue bỏ đi, thêm
  `flow:inbox`, đổi nó sang `flow:refined`, rồi close. Dọn dẹp sau khi xong; không bao giờ để lại
  test artifact mà không nói cho user.

```bash
# only with user consent
gh issue create --title "AgentFlow setup check" --body "temporary — safe to close" --label "flow:inbox"
# ...swap label flow:inbox → flow:refined to prove transitions, then:
gh issue close <n> --comment "AgentFlow verification complete."
```

## 12. Tóm tắt

In ra một report gọn:

```
AgentFlow initialized on <OWNER/REPO> (v0.1.0)

Project     : <name> — <summary>
Connections : github ✓   github_project on PVT_…   figma <on (OAuth) | off>
Env         : GITHUB_TOKEN set ✓   FIGMA_TOKEN <set | absent>
Surfaces    : <key>=<path> [, <key>=<path> …]   (only the surfaces that exist)
              command coverage per surface: lint/test/integration/e2e/build
Labels      : <12 + N> created/updated (flow:* ·7, type/* ·3, component/* ·N, rework ·1, human-changes ·1)
Board       : <PVT_…>
Skills      : <scaffolded role-prefixed stubs, or none>
Files       : .claude/agentflow.yaml, README.agentflow.md, [.claude/skills/<role>-* …]

Next: run /start to enter team mode, then /task <description> to file your first item.
```

---

**Re-runs:** an toàn bất cứ lúc nào. Re-detect surfaces, re-link hoặc tạo lại board, đăng ký skill mới,
hoặc refresh connections/env — mỗi bước tái dùng các value `.claude/agentflow.yaml` hiện có làm
default và hỏi trước khi ghi đè. Labels và board (nếu có) được reconcile một cách idempotent.
