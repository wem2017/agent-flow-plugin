# AgentFlow

Một Claude Code plugin biến một coding agent đơn lẻ thành một team nhỏ, có trách nhiệm rõ ràng. Ba agent — **PMO (Product Owner + Product Manager)**, **Developer (DEV)**, và **Quality Control (QC)** — phối hợp trên GitHub repo của bạn, để bạn chỉ phải làm hai việc bằng tay: **mô tả công việc** và **review/merge cái PR cuối cùng**.

AgentFlow **tech-stack-agnostic**. Bạn cài plugin **một lần** và chạy nó theo từng repo; mỗi repo có `.claude/agentflow.yaml` riêng — single source of truth mô tả connections, secrets, surfaces, skills, labels, và rule của agent. Các agent và bốn core skill **chỉ** đọc file này. Điểm nổi bật của **v0.5.0**:

- **Bốn core skill tập trung** — `setup-agentflow`, `project-board-protocol`, `git-flow-working`, `figma-design`. Hướng dẫn onboarding/setup, wire protocol, git flow, và Figma handoff đi kèm plugin và load on demand.
- **Project skill mở rộng theo prefix của role** — thả skill của riêng bạn vào `.claude/skills/` đặt tên `dev-*` / `qc-*` / `pmo-*`; agent tương ứng sẽ nhận chúng. Đăng ký chúng trong `skills:` để có cái nhìn tổng quan, hoặc dựa vào auto-discovery theo prefix.
- **Connections được đặc tả đầy đủ** — mỗi `connections.<name>` gói secret (`auth.token_env`), scopes, và MCP server (`mcp.server` + `mcp.requires_env`) lại một chỗ.
- **Dynamic surfaces** — `surfaces:` là một **open map**. Chỉ khai báo những phần bạn thực sự có (một hoặc nhiều, phối hợp tùy ý); label `component/<surface>` được sinh ra tương ứng, và QC là surface-aware.

Không có message bus và không có external service nào nằm trong vòng lặp. Các agent giao tiếp hoàn toàn qua GitHub primitives:

- **`Status` field trên Projects v2 board** — state authoritative (việc cần làm tiếp theo); happy path `Inbox → Ready for Dev → In Progress → In QC → Ready for Human Review → Done` (các lane rework / escalation / human PR-feedback: xem "Pipeline hoạt động ra sao").
- **Issue comments** với prefix bắt buộc (`[PMO]`, `[DEV]`, `[QC] ✅`, …) — phần hội thoại, và là **audit trail duy nhất** của transition (Status change không tạo issue-timeline event).
- **Một section `AGENTFLOW-STATE` trong issue body** — bộ nhớ của các agent giữa các lần chạy.

GitHub Projects v2 board là **bắt buộc** — Status field của nó mang state, và board đồng thời là inbox queue của orchestrator. **Label không mang state**: label chỉ còn classification `type/*`, `component/<surface>`, và aux `rework`. Mọi agent (PMO/DEV/QC lẫn orchestrator) đọc và ghi state qua các tool `projects_*` — mỗi agent tự thực hiện transition của chính nó. Figma là **tùy chọn** — chỉ DEV dùng trong lúc làm UI khi connection `figma` được enable.

---

## Yêu cầu

AgentFlow điều khiển GitHub qua **một** đường credential duy nhất — **GitHub MCP server**, được cấp quyền bằng `GITHUB_TOKEN`; **local `git`** lo version control trên working tree qua remote sẵn có của repo:

| Đường | Dùng cho | Cách authenticate |
|------|----------|----------------------|
| **GitHub MCP server** (official `github/github-mcp-server` — mặc định là hosted remote tại `https://api.githubcopilot.com/mcp/`) | mọi GitHub-API op: tạo/đọc/liệt kê issue, branch, PR, PR review, comment, đổi label classification, merge PR, và board (đọc/ghi Status ở runtime; tạo/link board + label lúc init) | biến env `GITHUB_TOKEN`, gửi dưới dạng header `Authorization: Bearer` |
| **local `git`** (qua `Bash`) | VCS trên working tree: tạo branch, commit, push, checkout PR head, rebase | remote + credential có sẵn của repo (không phải một credential riêng) |
| **Figma MCP server** *(tùy chọn)* (official Figma MCP tại `https://mcp.figma.com/mcp`) | kéo frame spec/token trong lúc làm UI (skill: `figma-design`) | **OAuth** — đăng nhập qua `/mcp` (không cần token) |

Đảm bảo bạn có:

1. **Một `GITHUB_TOKEN` trong `.env`**, được source vào shell dùng để khởi động Claude Code. `.mcp.json` gửi nó tới GitHub MCP server, và bật hai toolset opt-in `projects` + `labels` qua header `X-MCP-Toolsets` (board được resolve theo **project number** lưu ở `board.number`):

   ```bash
   cp .env.example .env            # then fill in GITHUB_TOKEN=...
   set -a; source .env; set +a     # export it into the shell that launches Claude Code
   ```

   Official **Figma** MCP server authenticate bằng **OAuth**, không phải token — sau khi cài, chạy `/mcp` → `figma` → **Authenticate**.

   > **Tùy chọn MCP server.** Wiring GitHub mặc định là server **hosted remote** (không cần cài, giữ PAT của bạn ở phía bạn). Để chạy nó **local** thay vào đó, đổi block `github` trong `.mcp.json` sang Docker image `ghcr.io/github/github-mcp-server` (`-e GITHUB_PERSONAL_ACCESS_TOKEN -e GITHUB_TOOLSETS=context,issues,pull_requests,users,labels,projects`), pin vào một release tag. `projects` + `labels` là bắt buộc vì AgentFlow điều khiển board và label qua MCP; `context` + `users` cấp `get_me` (own login cho claim/assignee).

2. **Token scopes** — GitHub token cần:
   - `repo` — đọc/ghi code, issues, PRs.
   - `read:org` — để resolve project thuộc sở hữu của org.
   - `project` — GitHub Projects v2 board (`connections.github_project.enabled: true`) là bắt buộc, nên scope này luôn cần.

   > **Lưu ý bảo mật:** Dùng **classic PAT** (scopes: `repo`, `project`, + `read:org` cho org board) — fine-grained PAT chưa được verify cho Projects v2 user-owned board; board-write smoke test của init là nơi phát hiện token sai loại. Một classic PAT với `repo` cấp quyền write rộng tới *mọi* repo mà token vươn tới được, và cả ba agent dùng chung một token này — coi token là secret: chúng được tham chiếu qua `${GITHUB_TOKEN}` / `${FIGMA_TOKEN}`, không bao giờ hardcode hay echo, nên đừng commit chúng.

3. **Một git repo với GitHub remote** — `git remote get-url origin` phải resolve được, và `git` có sẵn trong PATH. AgentFlow không hoạt động trên repo không phải GitHub.

### Biến môi trường

| Tên | Bắt buộc | Dùng bởi | Mô tả |
|------|----------|---------|-------------|
| `GITHUB_TOKEN` | **Có** | connection `github`, `github_project` | GitHub **classic PAT** (fine-grained chưa được verify cho Projects v2 user-owned board). Scopes: `repo`, `read:org`, `project`. |
| `FIGMA_TOKEN` | Không | connection `figma` | Figma personal access token (Figma → Settings → Personal access tokens). |

Secrets được khai báo bằng **tên** trong `.claude/agentflow.yaml` dưới `env:` (với `used_by` cross-link mỗi biến tới các connection tiêu thụ nó). **Giá trị** nằm trong file `.env`: copy `.env.example` → `.env`, điền vào, và `source` nó trước khi khởi động Claude Code (`.env` không bao giờ được commit — chỉ `.env.example` mới commit). `/agentflow-init` xác minh mọi biến `required: true` đều có mặt và từ chối hoàn tất nếu thiếu một cái. Đừng bao giờ đặt giá trị vào trong yaml.

---

## Cài đặt

Plugin phân phối qua marketplace `agent-flow-plugins` — khai báo ở `.claude-plugin/marketplace.json` tại root repo, với plugin nằm ở `./agentflow`. Cài được bằng hai đường: slash command trong session, hoặc `claude` CLI ngoài terminal.

**Trong Claude Code (slash command):**

```bash
claude plugin marketplace add /path/to/Plugins        # thư mục chứa .claude-plugin/marketplace.json
claude plugin install agentflow@agent-flow-plugins     # --scope user (mặc định) | project | local
```

`--scope user` (mặc định) cài **một bản dùng chung cho mọi repo trên máy** — đúng tinh thần "cài một lần, chạy theo từng repo". Dùng `--scope project` nếu chỉ muốn bật cho một repo (ghi vào `.claude/settings.json`, chia sẻ với team qua git).

Sau đó **restart Claude Code** (hoặc reload plugins) để các MCP server, agent, command, skill, và hook được đăng ký. Kiểm tra nhanh:

```bash
claude plugin list                                   # xác nhận đã enabled
claude plugin details agentflow@agent-flow-plugins   # xem inventory (agents/skills/MCP) + token cost
```

---

## Phát triển & cập nhật plugin

Toàn bộ quy trình dev/release plugin (directory source vs cache snapshot, bump version, vòng lặp update, phân phối cho team) nằm trong [`CONTRIBUTING.md`](CONTRIBUTING.md).

---

## Bắt đầu nhanh

```text
/agentflow-init   # one-time setup for THIS repo (connections, env, surfaces, skills, labels, board, config)
/task add a CSV export button to the reports page    # file work → it lands on the board
/start            # board-driven: claim unassigned Inbox tickets and drive each end-to-end (PMO → DEV → QC)
```

**`/start` là board-driven** — nó poll GitHub Project board của repo này, claim từng ticket "Inbox" rồi điều khiển ticket đó end-to-end qua **PMO → DEV → QC** (cơ chế claim + parallel terminals: xem "Ghi chú & giới hạn"), chỉ break ngược lại cho bạn khi ticket rơi vào lane can thiệp của con người "Refined", một DEV card bị block, hoặc một PR đã sẵn sàng để merge. **`/start` không intake công việc**; công việc mới vào qua **`/task <description>`** hoặc bằng cách thả một card lên board.

---

## Connections

Một **connection** là một external service mà project này liên kết tới. Block `connections.*` trong `.claude/agentflow.yaml` là registry duy nhất mà các agent và skill đọc để biết **được phép nói chuyện với cái gì và như thế nào**. Mỗi connection tự đặc tả đầy đủ wiring của nó ở một chỗ:

```yaml
connections:
  github:
    enabled: true
    repo: "owner/repo"
    auth:
      token_env: "GITHUB_TOKEN"          # secret name (value lives in your shell/.env)
      scopes: ["repo", "read:org"]       # "project" qua github_project.auth.scopes (board là bắt buộc)
    mcp:
      server: "github"                   # → .mcp.json mcpServers.github
      requires_env: ["GITHUB_TOKEN"]     # server won't start without this
```

Một connection **chỉ dùng được khi `enabled: true` AND mọi biến trong yêu cầu `auth`/`mcp` của nó đều có mặt.** Bỏ hẳn block `mcp` cho một service không có MCP server. Connections mang tính cộng dồn — tắt một cái bằng `enabled: false`.

Chuỗi từ secret tới service được nêu tường minh:

```
env: (name only)  →  connections.<svc>.auth          →  .mcp.json wiring                    →  MCP server
GITHUB_TOKEN      →  github.auth.token_env: GITHUB_TOKEN →  github (http): Authorization: Bearer ${GITHUB_TOKEN}  →  github MCP
(no token)        →  figma.auth.method: oauth          →  figma (http): OAuth via /mcp        →  figma  MCP
```

Các connection built-in:

| Connection | Mục đích | Key config | Gating |
|------------|---------|------------|--------|
| `github` | Issues, branches, PRs, comments — nền tảng mà toàn bộ pipeline chạy trên đó. | `repo`, `auth.token_env`, `mcp.server` | Bắt buộc (`enabled: true` + `GITHUB_TOKEN`). |
| `github_project` | **Bắt buộc** Projects v2 board — nơi `Status` field sống, và là inbox queue của orchestrator. Dùng `github` MCP server (toolset `projects`, key theo owner + project number; không có server riêng). | `owner`, `owner_type`, `auth.scopes` | Bắt buộc (`project` scope); xem skill `project-board-protocol`. |
| `figma` | Nguồn design tùy chọn cho DEV trong lúc làm UI. | `auth.method: oauth`, `mcp.server`, `files` | Official server đăng nhập qua **OAuth** (`/mcp` → Authenticate); `FIGMA_TOKEN` kiểu cũ chỉ cho REST fallback. Xem skill `figma-design`. |

Thêm cái của riêng bạn cũng theo pattern đó: khai báo secret dưới `env:`, copy một block `connections.<name>` (`enabled`, `auth.{token_env,scopes}`, một `mcp.{server,requires_env}` tùy chọn nếu nó có server, cộng metadata của service), và wire bất kỳ MCP server mới nào vào `.mcp.json`. Agent **gate before use**, và degrade gracefully nếu connection không dùng được. Toàn bộ contract của registry — đọc connections, map sang env + MCP, gate-before-use, secret hygiene, và cách thêm một service — nằm trong skill `setup-agentflow`.

---

## Surfaces

Một **surface** là một phần build được của project, và `surfaces:` là một **dynamic, open map** — bạn chỉ khai báo những surface bạn thực sự có, và bạn tự chọn tên key (`backend`, `web`, `api`, `admin`, `mobile`, … hoặc chỉ `"."` cho repo một surface). AgentFlow không bao giờ giả định bộ ba backend/frontend/mobile đều có mặt — DEV và QC lặp qua bất kỳ surface nào tồn tại, và tự khám phá cách build/lint/test cho mỗi surface theo convention của chính repo (`package.json` scripts, `Makefile`, `pubspec`, `go.mod`, CI config…).

```yaml
surfaces:
  backend:                  # the key is yours — could be "api", "web", "mobile", "." …
    path: "api/"            # "." for a single-surface repo
    label: "component/backend"
    forbidden_paths: []
```

Mỗi surface map tới một **label `component/<surface>`**, được init sinh ra khớp với các surface key (một cái cho mỗi surface đã khai báo). PMO gắn tag cho issue với các surface mà nó chạm tới; DEV và QC sau đó **chỉ** build/lint/test **những surface đó** — đây chính là điều làm QC trở nên **surface-aware**:

- **QC tier** không phải config — nó là một **gợi ý ngữ nghĩa về độ sâu test**, ý nghĩa cố định trong plugin: `quick` = lint + unit test; `full` = thêm integration; `regression` = thêm e2e (cộng dồn: `quick ⊆ full ⊆ regression`). PMO chọn tier theo blast radius; QC map nó sang bất kỳ category test nào mà repo thực sự có.
- Để chạy một tier cho một issue: với **mỗi surface** issue chạm tới, QC chạy các category test mà tier ngụ ý theo convention của repo. Tất cả phải pass. QC đánh giá độ đầy đủ của test bằng cách inspect, không có ngưỡng coverage.

---

## Skills

### Core skills (đi kèm plugin)

Agent load các skill này on demand; mỗi cái là một `SKILL.md` dưới `skills/<name>/`. Không cần đăng ký.

| Skill | Dùng để làm gì |
|-------|----------------|
| `setup-agentflow` | Skill onboarding / meta. Single source of truth `agentflow.yaml`, đặc tả connection đầy đủ (token + MCP server + scopes), block `env:`, dynamic surfaces, registry project-skill + convention role-prefix, cách `/agentflow-init` bootstrap, và secret hygiene. |
| `project-board-protocol` | GitHub wire protocol: Status trên board, classification label (`type/*`, `component/*`, aux `rework`), comment prefix, Definition of Ready/Done, section state trong issue body, rework loop, human PR-feedback re-entry, và trust rule — board mechanics (resolve/create, queue, Status write, built-in workflows) nằm trong `reference/projects-v2-board.md`. Đọc trước khi chạm vào bất kỳ board artifact nào. |
| `git-flow-working` | Branching tech-agnostic, Conventional Commits, PR convention, và an toàn rebase/merge. |
| `figma-design` | Kéo frame spec/token qua `figma` MCP server (với REST fallback) cho việc handoff từ design sang implementation. |

### Project skills (mở rộng theo từng repo)

Một project có thể thêm skill **của riêng nó** mà chỉ repo đó cần. Đặt tên chúng `<role>-<area>` để đúng agent nhận chúng, và thả vào `.claude/skills/`:

| Prefix | Được load bởi | Ví dụ |
|--------|-----------|---------|
| `dev-*` | DEV | `dev-mobile-development` — convention state & navigation của mobile |
| `qc-*` | QC | `qc-automation-test` — viết E2E suite |
| `pmo-*` | PMO | `pmo-discovery` — checklist discovery & story-mapping |

Chúng vừa được **đăng ký** vừa được **auto-discover**:

- **Đăng ký** trong `agentflow.yaml` dưới `skills:` dưới dạng map — `<name>: { role, surfaces?, description? }`. Registry này là single source of truth / cái nhìn tổng quan và cho phép bạn scope một skill vào những surface cụ thể.

  ```yaml
  skills:
    dev-mobile-development: { role: dev, surfaces: ["mobile"], description: "Mobile state & navigation conventions" }
    qc-automation-test:     { role: qc,  surfaces: ["web", "mobile"], description: "E2E suite authoring" }
    pmo-discovery:          { role: pmo, description: "Discovery & story-mapping checklist" }
  ```

- **Auto-discover** — một agent cũng load bất kỳ `.claude/skills/<its-role>-*` nào có mặt kể cả khi nó không được liệt kê.

Một agent load các role-prefixed skill của role nó mà liên quan tới (các) surface issue hiện tại chạm tới (khớp một entry `surfaces` trong registry với các label `component/*` của issue; một skill không có `surfaces` — hoặc không nằm trong registry — thì luôn liên quan). `/agentflow-init` có thể scaffold các starter stub và điền registry `skills:` giúp bạn.

---

## Commands

| Command | Nó làm gì |
|---------|--------------|
| `/agentflow-init` | Bootstrap một lần **theo từng repo**: cấu hình `connections.*`, xác minh secret `env:`, khai báo các `surfaces.*` bạn có (`path` + `label` + `forbidden_paths`), scaffold/đăng ký project skill, tạo label classification `type/*` + `component/<surface>` + aux `rework` (không có label state), tạo/link Projects v2 board **bắt buộc** (Status field 7 option + built-in workflows: bước UI thủ công được hướng dẫn, init validate lại), sinh `.claude/agentflow.yaml` và `README.agentflow.md`, và chạy một verification ticket end-to-end. Chạy lại trên repo v0.3.x để migrate (xem "Migration"). |
| `/start` | Vào board-driven team mode; session claim các ticket Status "Inbox" chưa được assign (kể cả ticket được con người kéo card về "Inbox" sau khi review PR) rồi điều khiển mỗi cái end-to-end qua các agent (hỗ trợ terminal song song; poll liên tục opt-in qua skill `/loop`). **Không intake công việc.** |
| `/task <description>` | Lập một work item mới từ một mô tả tự do (PMO sở hữu việc intake) và thêm nó vào board với Status "Inbox". |
| `/review-refined` | Phiên review tương tác giữa con người ↔ agent cho một ticket "Refined" đang bị block: thu thập info/quyết định còn thiếu, chỉnh lại ticket, rồi đưa Status về "Inbox" để dòng chảy tiếp tục (PMO re-triage). |
| `/status` | In số lượng open-issue theo từng Status column cho repo này; `--audit` chạy membership + reconcile + visibility/orphan check. |
| `/improve [bài học]` | Capture một bài học từ usage thực tế (trống → tự mine session tìm friction point) và fold nó vào đúng file tri thức trong plugin **SOURCE** — minimal edit có duyệt diff, bump version + CHANGELOG, chạy release loop để version sau hoạt động chính xác hơn. `--no-release` để dồn nhiều cải tiến vào một lần release; `--release` để xả backlog đã tích mà không cần bài học mới. |

---

## Pipeline hoạt động ra sao

```
happy path:
  Inbox → Ready for Dev → In Progress → In QC → Ready for Human Review → Done

QC ❌ rework loop (fail ≤ 2):
  In QC ──❌──▶ Ready for Dev  (+ aux label rework)  ──▶ … ──▶ In QC

escalation & human-intervention lane (owner: human):
  In QC ──❌ (fail > 2)──▶ Refined
  Inbox ──(PMO can't reach DoR: missing info)──▶ Refined
  In Progress/Ready for Dev ──(DEV missing spec/Figma)──▶ Refined
  In QC ──(QC: AC genuinely ambiguous)──▶ Refined
       Refined ──(human adds info via /review-refined, HOẶC kéo card)──▶ Inbox  (re-enters, PMO re-triages)

human PR-review feedback (con người chủ động):
  Ready for Human Review ──(human để feedback inline trên PR, rồi KÉO CARD về Inbox)──▶ Inbox  (re-enter, PMO re-triage đọc PR feedback)
```

- **PMO** biến message của bạn thành một issue chỉn chu ngay tại "Inbox", gắn label `type/*` và `component/<surface>`, gate nó qua một **Definition of Ready**, viết một implementation plan **`## For DEV`** cho từng agent và một focus verification **`## For QC`** vào issue body (planning bằng cách mô tả, không phải bằng cách dispatch — nó không bao giờ assign hay điều khiển các agent khác). DoR pass → Status "Ready for Dev"; nếu cần con người bổ sung info thì park sang "Refined" kèm một vòng câu hỏi `[PMO]`. PMO không tự trả lời câu hỏi làm rõ của DEV/QC — mọi info-gap đều để con người xử lý ở "Refined", và PMO re-triage khi ticket quay lại "Inbox". (Không bao giờ viết code hay merge — hard rule.)
- **DEV** implement một issue trên một **branch đặt tên theo type** (`agent/dev/<kind>/<issue#>-<slug>`, `kind` lấy từ label `type/*`: feature→feat, bug→fix, improvement→chore) và mở/cập nhật một PR, giữ trong phạm vi acceptance criteria và không bao giờ chạm `forbidden_paths` (tập global built-in — xem "Cấu hình" — hợp với `forbidden_paths` riêng của từng surface được chạm tới). Với mỗi surface được chạm tới, DEV chạy lint/analyze + test liên quan theo convention của repo; **lint/analyze phải green** trước khi handoff. (Không bao giờ merge — hard rule.)
- **QC** đọc implementation diff đối chiếu với AC, **viết automation test** — thêm các test identifier mà suite cần và viết các test flow map tới AC, rồi commit (`test(...)`) và push chúng lên chính branch PR hiện có của DEV — chạy các category test mà **QC tier** của issue ngụ ý (giờ bao gồm cả các test đó) theo convention của repo đối với các surface được chạm tới ở local, và ký duyệt (`[QC] ✅`, sẵn sàng merge) hoặc từ chối (`[QC] ❌`). Mỗi lần từ chối (còn trong ngưỡng **2** lần fail liên tiếp) route ticket ngược về "Ready for Dev" kèm aux label `rework` để DEV sửa; sau khi vượt ngưỡng, lần ❌ kế tiếp escalate lên "Refined" — lane can thiệp của con người. (Chỉ đụng test file/test ID trên branch PR — không bao giờ đổi implementation logic, không bao giờ merge.)
- **Bạn** review và merge — hoặc để lại **feedback inline trực tiếp trên code của PR** rồi **kéo card về "Inbox"** (agent/orchestrator không thao tác bước chuyển này; ticket đã được unassign ở "Ready for Human Review" nên bạn chỉ cần kéo card): pipeline chạy lại từ PMO — PMO đọc feedback của bạn trên PR, fold vào spec/AC rồi re-gate DoR; DEV **amend chính PR/branch hiện có** (không build lại từ đầu), QC re-gate trước khi nó quay lại cho bạn. Orchestrator không bao giờ merge nếu không có chỉ thị tường minh của bạn.

Role boundary là behavioral contract trong prompt từng agent — PMO không sửa code, chỉ DEV mở branch/PR và push feature code, QC chỉ đụng test file/test ID trên PR branch; giới hạn `tools:` trong frontmatter theo capability mỗi role là lớp siết bổ sung khi được cấu hình. Cả ba agent load được core skill và role-prefixed skill của chúng, và mỗi agent tự thực hiện Status transition của chính nó theo write order của protocol. Toàn bộ wire protocol — comment prefix, DoR/DoD, state section trong issue body, và trust rule — là skill `project-board-protocol`.

---

## Cấu hình

Mọi setting nằm trong **`.claude/agentflow.yaml`** (sinh ra bởi `/agentflow-init`; template là schema có thẩm quyền). Những thứ bạn hay tinh chỉnh:

- **`connections.*`** — bật/tắt và cấu hình `github`, `github_project`, `figma`, hay service của riêng bạn. Xem skill `setup-agentflow`.
- **`env:`** — danh sách các secret `{ name, required, used_by, description }` mà các connection cần. **Chỉ tên**, không bao giờ giá trị.
- **`surfaces.<key>`** — `path`, `label`, `forbidden_paths`. Open map: thêm, đổi tên, hay xóa surface tùy ý — chỉ khai báo cái bạn có. DEV/QC build/lint/test surface theo convention của chính repo, không phải command khai báo trong config.
- **`skills.<name>`** — registry của các project skill, `{ role, surfaces?, description? }`. Single source of truth cho việc mỗi role load thêm skill nào.
- **Built-in plugin defaults (không nằm trong config).** Branch prefix (`agent/dev/`), tập forbidden_paths global áp cho **mọi** surface (`infra/**`, `.github/workflows/**`, `**/*.pem`, `**/.env` — hợp với `forbidden_paths` riêng của từng surface, enforce bằng prompt + một QC review check), ngưỡng escalate rework (**2** lần fail liên tiếp), và ý nghĩa QC tier (`quick`/`full`/`regression` = độ sâu test) là các hằng số cố định trong plugin.
- **`board.number` / `board.columns`** — project number của Projects v2 board (một số không rỗng; board là bắt buộc — MCP projects tools key theo owner + number, không phải node id) và bảy tên column của Status field. `board.columns` chính là **state enum authoritative**; các option name là wire value được resolve by-name, nên đổi tên một option trong UI là break routing (init validate qua `list_project_fields`, nhưng MCP không tạo/sửa được single-select Status field — đó là bước UI một lần lúc init). Đi cùng `connections.github_project.enabled` (luôn `true`; init giữ chúng đồng bộ).

`README.agentflow.md` (cũng được sinh vào target repo) là quick reference hàng ngày cho người dùng của repo đó.

---

## Ghi chú & giới hạn

- **Mặc định synchronous; continuous là opt-in.** Mặc định, chính việc break-out ở terminal *là* notification — không có kênh bên ngoài nào (Telegram/Zalo/v.v.). Bạn có thể chạy `/start` không cần giám sát theo một interval qua skill `/loop` (cadence thích ứng, không phải busy-loop); các break-out khi đó xếp hàng bền vững trên board (Status được park + comment) cho tới khi bạn quay lại. Xem `/start` → "Continuous mode".
- **Cái claim chính là GitHub `assignee`** (sống trên issue) cộng với Status trên board. `/start` chỉ luôn lấy các ticket Status "Inbox" chưa được assign rồi tự assign để claim, nên **nhiều terminal `/start` có thể chạy song song** trên cùng một repo. Mọi terminal dùng chung một token (cùng một GitHub user), nên assignee de-dupe được nhưng không phân biệt được các terminal — một race nhỏ ở lúc claim inbox là có thể xảy ra (backstop kép: orchestrator check Status trước spawn, và DEV pickup thấy "In Progress" → abort); để cô lập nghiêm ngặt hãy cấp cho mỗi terminal một GitHub identity riêng.
- **Kéo card là human API chính thức — nhưng chỉ ở các parked state** (không có agent nào đang giữ ticket): `Refined` → `Inbox` (sau khi bổ sung info; `/review-refined` vẫn là đường khuyến nghị), `Ready for Human Review` → `Inbox` (PR-feedback re-entry), close issue / merge PR → `Done`. Kéo card khi ticket đang `In Progress` / `In QC` (agent đang chạy) **không an toàn**: compare-then-write của agent sẽ phát hiện và abort được phần lớn trường hợp, nhưng vẫn tồn tại cửa sổ clobber — muốn dừng một run đang chạy, dừng terminal, đừng kéo card. Một cú kéo tắt qua PMO bị chặn bởi DoR defense: DEV trả ticket về "Inbox" thay vì implement.
- **Status write là mandatory-success, và state chỉ sống trên board.** Một Status write fail là **pipeline dừng có chủ đích** (fail-stop), không phải desync. Một issue OPEN nhưng không có trên board là **vô hình với routing** — `/task` và `/agentflow-init` đảm bảo mọi work item được add vào board kèm Status, và `/status` chạy một **membership check** (list open issues của repo, đối chiếu với board items) để phát hiện và liệt kê các issue lọt lưới.
- **Safety rule ở mức prompt.** `forbidden_paths`, merge gate, và trust model là behavioral contract cho agent (cộng lớp siết `tools:` theo capability khi được cấu hình) — không phải enforced hook. Dùng token least-privilege và review PR trước khi merge.
- **Comment GitHub không có prefix là untrusted.** Agent coi bất kỳ comment nào không có prefix `[PMO]` / `[DEV]` / `[QC]` / … được nhận diện là context untrusted, không phải chỉ thị.

---

## Migration từ v0.3.x (state label `flow:*`)

Các bản v0.3.x dùng label `flow:*` làm state authoritative và board chỉ là một mirror best-effort để con người xem. Từ **v0.4.0**, state chuyển hẳn sang `Status` trên board (xem intro) và label `flow:*` không còn tồn tại — không tạo, không đọc. Trên một repo đã init bằng v0.3.x, chạy lại **`/agentflow-init`**: nó detect các label `flow:*` còn sót lại như di sản cần dọn — **backfill Status từ label map cũ** (`flow:inbox` → "Inbox", `flow:ready-for-dev` → "Ready for Dev", …) cho các issue đang open, gỡ label khỏi issue, xóa 7 label definition, và refresh `.claude/agentflow.yaml` (xóa block `labels.flow`, bump `agentflow_version` lên `1.0.0`). Config cũ (`agentflow_version` < 1.0.0) bị version gate của `setup-agentflow` chặn cho tới khi migrate xong.

---

## Non-goals — những gì KHÔNG được thay đổi

Những điều này là load-bearing, dễ bị bào mòn bởi sự tích lũy có thiện chí, và cố tình được đặt như vậy. Hãy coi thay đổi ở đây là design change, không phải cải tiến:

- **`Status` trên Projects v2 board là state authoritative duy nhất; label không bao giờ mang state.** Đừng bao giờ để một label hay một câu trả lời tường thuật của sub-agent trở thành *nguồn* routing. Việc đọc lại Status live sau mỗi lần chạy chính là thứ làm cho thiết kế no-message-bus hoạt động.
- **Role isolation là prompt contract + tool restriction khi được cấu hình** — đừng nới capability của role nào "để phòng hờ" (cả ba agent dùng chung một token, nên blast radius là thật), và đừng giả vờ safety rule là enforced hook.
- **Human merge gate là bắt buộc.** Agent dừng ở "Ready for Human Review"; chỉ con người merge — đừng automate merge.
- **Đừng giả vờ safety rule là enforced.** Chúng là prompt contract + tool restriction khi được cấu hình, không phải enforced hook, và docs nói thẳng như vậy. Đừng che đậy điều đó bằng prose `NEVER …` ngày càng dài làm phình mỗi lần chạy để đổi lấy an toàn giả; enforcement thật thuộc về một hook/CI check.
- **Việc load skill lười, tách nhỏ vẫn giữ lười.** Các cơ chế nặng nằm trong file `reference/` chỉ đọc khi cần (`projects-v2-board.md`). Đừng front-load cơ chế board vào mỗi agent prompt.
- **Đừng làm phình section `AGENTFLOW-STATE` trong issue body.** Ba agent prose-edit nó và phải giữ tương thích format; mỗi field bắt buộc mới là một bề mặt drift mới. Ưu tiên ít field hơn, không phải nhiều hơn.
- **Optional connection degrade gracefully.** Một *optional* service bị disable/vắng mặt (ví dụ figma) được bỏ qua kèm một note, không bao giờ là một hard block. Đừng làm cứng optional connection thành precondition chặn cứng. (Connection `github` và board là ngoại lệ — cả hai đều bắt buộc.)
