# AgentFlow

Một Claude Code plugin biến một coding agent đơn lẻ thành một team nhỏ, có trách nhiệm rõ ràng. Ba agent — **PMO (Product Owner + Product Manager)**, **Developer (DEV)**, và **Quality Control (QC)** — phối hợp trên GitHub repo của bạn, để bạn chỉ phải làm hai việc bằng tay: **mô tả công việc** và **review/merge cái PR cuối cùng**.

AgentFlow **tech-stack-agnostic**. Bạn cài plugin **một lần** và chạy nó theo từng repo; mỗi repo có `.claude/agentflow.yaml` riêng — single source of truth mô tả toàn bộ project chỉ trong một cái nhìn. Không có gì trong plugin giả định trước ngôn ngữ, framework, hay cấu trúc thư mục — bạn tự cung cấp các command. Điểm nổi bật của **v0.1.0**:

- **Bốn core skill tập trung** — `setup-agentflow`, `project-board-protocol`, `git-flow-working`, `figma-design`. Hướng dẫn onboarding/setup, wire protocol, git flow, và Figma handoff đi kèm plugin và load on demand.
- **Project skill mở rộng theo prefix của role** — thả skill của riêng bạn vào `.claude/skills/` đặt tên `dev-*` / `qc-*` / `pmo-*`; agent tương ứng sẽ nhận chúng. Đăng ký chúng trong `skills:` để có cái nhìn tổng quan, hoặc dựa vào auto-discovery theo prefix.
- **Connections được đặc tả đầy đủ** — mỗi `connections.<name>` gói secret (`auth.token_env`), scopes, và MCP server (`mcp.server` + `mcp.requires_env`) lại một chỗ. Một connection chỉ dùng được khi `enabled: true` **và** mọi biến bắt buộc đều có mặt.
- **Single source of truth** — `.claude/agentflow.yaml` mô tả connections, secrets, surfaces, skills, labels, và rule của agent. Các agent và bốn core skill **chỉ** đọc file này.
- **Dynamic surfaces** — `surfaces:` là một **open map**. Chỉ khai báo những phần bạn thực sự có (một hoặc nhiều, phối hợp tùy ý); label `component/<surface>` được sinh ra tương ứng, và QC là surface-aware.

Không có message bus và không có external service nào nằm trong vòng lặp. Các agent giao tiếp hoàn toàn qua GitHub primitives:

- **Label `flow:*`** trên mỗi issue — state machine có thẩm quyền (happy path `inbox → ready-for-dev → in-progress → in-qc → ready-for-human-review → done`; QC ❌ route ngược về `ready-for-dev` kèm aux label `rework`, và sau `max_rework_returns` (=2) lần rework thì escalate lên `refined` — lane can thiệp của con người; còn feedback của con người khi review PR được xử lý bằng cách chuyển ticket về `inbox` để pipeline chạy lại).
- **Issue comments** với prefix bắt buộc (`[PMO]`, `[DEV]`, `[QC] ✅`, …) — phần hội thoại.
- **Một sticky `AGENTFLOW-STATE` comment** — bộ nhớ của các agent giữa các lần chạy.

Một GitHub Projects v2 board là **bắt buộc** — nó vừa là inbox queue của orchestrator **vừa** là mirror để con người nhìn thấy các label; agent không bao giờ đọc hay di chuyển board column để routing (label `flow:*` vẫn giữ thẩm quyền). Figma là **tùy chọn** — chỉ DEV dùng trong lúc làm UI khi connection `figma` được enable.

---

## Chạy được trên mọi project

Cài plugin một lần, dùng cho nhiều repo. Mỗi repo tự mô tả chính nó trong **`.claude/agentflow.yaml`** (sinh ra bởi `/agentflow-init`):

| Vấn đề | Nằm ở đâu | Giả định về tech-stack |
|---------|----------------|------------------------|
| Build/test commands | `surfaces.<name>.commands.*` | Không — bạn tự viết shell command |
| Nói chuyện với service nào | `connections.*` | Không — mỗi cái nêu token env + MCP server |
| Secrets | `env:` (chỉ tên) | Không |
| Know-how riêng của project | `.claude/skills/<role>-*` + `skills:` registry | Không — bạn tự viết skill |
| State / routing | `flow:*` labels | Không |

Chuyển sang repo khác và chạy lại `/agentflow-init`: một Go monorepo, một React app, một Flutter client, hay cả ba trong một polyrepo đều dùng **cùng một plugin** với **config khác nhau**. Cài một lần → chạy trên nhiều project, không bị lock-in vào tech-stack, mở rộng theo từng project qua skill đặt prefix theo role. Không hề có stack lock-in.

---

## Yêu cầu

AgentFlow điều khiển GitHub qua **hai** đường credential, và **cả hai phải được authenticate bằng cùng một tài khoản với cùng scope**:

| Đường | Dùng cho | Cách authenticate |
|------|----------|----------------------|
| **`gh` CLI** (qua `Bash`) | đổi label, đọc/liệt kê issue, merge PR, tạo board/label lúc init | `gh auth login` |
| **GitHub MCP server** (official `github/github-mcp-server` — mặc định là hosted remote tại `https://api.githubcopilot.com/mcp/`) | tạo issue, branch, PR, PR review, comment, push file | biến env `GITHUB_TOKEN`, gửi dưới dạng header `Authorization: Bearer` |
| **Figma MCP server** *(tùy chọn)* (official Figma MCP tại `https://mcp.figma.com/mcp`) | kéo frame spec/token trong lúc làm UI (skill: `figma-design`) | **OAuth** — đăng nhập qua `/mcp` (không cần token) |

Đảm bảo bạn có:

1. **`gh` CLI đã cài và đã authenticate** — kiểm tra bằng `gh auth status`.
2. **Một `GITHUB_TOKEN` trong `.env`**, được source vào shell dùng để khởi động Claude Code. `.mcp.json` gửi nó tới GitHub MCP server dưới dạng header `Authorization: Bearer ${GITHUB_TOKEN}`:

   ```bash
   cp .env.example .env            # then fill in GITHUB_TOKEN=...
   set -a; source .env; set +a     # export it into the shell that launches Claude Code
   ```

   Official **Figma** MCP server authenticate bằng **OAuth**, không phải token — sau khi cài, chạy `/mcp` → `figma` → **Authenticate**. (PAT `FIGMA_TOKEN` kiểu cũ chỉ cần cho Framelink/REST fallback tùy chọn trong skill `figma-design`.)

   > **Tùy chọn MCP server.** Wiring GitHub mặc định là server **hosted remote** (không cần cài, giữ PAT của bạn ở phía bạn). Để chạy nó **local** thay vào đó, đổi block `github` trong `.mcp.json` sang Docker image `ghcr.io/github/github-mcp-server` (`-e GITHUB_PERSONAL_ACCESS_TOKEN -e GITHUB_TOOLSETS=repos,issues,pull_requests`), pin vào một release tag. Chỉ thêm `projects` vào `GITHUB_TOOLSETS` nếu bạn điều khiển board qua MCP thay vì `gh api graphql`.

4. **Token scopes** — GitHub token (và login của `gh`) cần:
   - `repo` — đọc/ghi code, issues, PRs.
   - `read:org` — để resolve project thuộc sở hữu của org.
   - `project` — GitHub Projects v2 board (`connections.github_project.enabled: true`) là bắt buộc, nên scope này luôn cần.

   > **Lưu ý bảo mật:** một classic PAT với `repo` cấp quyền write rộng tới *mọi* repo mà token vươn tới được, và cả ba agent dùng chung một token này. Nên ưu tiên **fine-grained token** giới hạn đúng repo mục tiêu, và coi token là secret — chúng được tham chiếu qua `${GITHUB_TOKEN}` / `${FIGMA_TOKEN}`, không bao giờ hardcode hay echo, nên đừng commit chúng.

5. **Một git repo với GitHub remote** — `git remote get-url origin` phải resolve được. AgentFlow không hoạt động trên repo không phải GitHub.

### Biến môi trường

| Tên | Bắt buộc | Dùng bởi | Mô tả |
|------|----------|---------|-------------|
| `GITHUB_TOKEN` | **Có** | connection `github`, `github_project` | GitHub PAT (ưu tiên fine-grained). Scopes: `repo`, `read:org`, `project`. |
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

Marketplace ở đây là **`directory` source** trỏ vào chính repo này, nên nó **đọc thẳng working tree** — sửa file trong `agentflow/` là bản nguồn đã đổi ngay, **không cần commit git**. Nhưng lúc `install`/`update`, Claude Code **copy một snapshot** vào cache (`~/.claude/plugins/cache/agent-flow-plugins/agentflow/<version>/`), khoá theo **`version`**. Hai hệ quả:

- Sửa source **không tự** lan sang bản đang chạy — phải update thủ công.
- `claude plugin update` **gated theo `version`**: nếu không đổi `version` trong `plugin.json`, nó báo *"already at latest"* và **không refresh** cache.

> **Quy tắc vàng:** mỗi lần có thay đổi muốn phát hành, **bump `version` trong `agentflow/.claude-plugin/plugin.json`** trước khi update. Không bump = update là no-op.

**Vòng lặp cập nhật (dev trên máy này):**

```bash
# 1. sửa code trong agentflow/…
# 2. bump version trong agentflow/.claude-plugin/plugin.json   (vd 0.1.0 → 0.1.1)
claude plugin validate ./agentflow                    # (khuyến nghị) validate manifest trước
claude plugin marketplace update agent-flow-plugins   # đọc lại source, nhận version mới
claude plugin update agentflow@agent-flow-plugins      # kéo version mới vào cache
# 3. restart Claude Code để load
```

Vì cài ở **user scope**, một lần update là **mọi project trên máy đều nhận** — không cần lặp lại từng repo.

**Mẹo dev nhanh:** đang lặp liên tục và ngại bump version mỗi lần thì `claude plugin uninstall agentflow@agent-flow-plugins` rồi `install` lại — ép copy snapshot mới kể cả cùng version. Bump version vẫn là cách chuẩn cho release thật.

**Phân phối cho team / máy khác.** `directory` source chỉ chạy trên máy bạn (đường dẫn local). Muốn người khác nhận được update, chuyển sang **`github` source**:

1. Push repo marketplace này lên GitHub.
2. Mỗi release: bump `version`, commit, rồi `claude plugin tag ./agentflow` tạo git tag `agentflow--v<version>` (lệnh này verify `plugin.json` khớp với entry trong `marketplace.json`).
3. Teammate: `claude plugin marketplace add <owner/repo>` một lần; sau đó mỗi lần cập nhật chạy `claude plugin marketplace update agent-flow-plugins` + `claude plugin update agentflow@agent-flow-plugins` + restart.

---

## Bắt đầu nhanh

```text
/agentflow-init   # one-time setup for THIS repo (connections, env, surfaces, skills, labels, board, config)
/task add a CSV export button to the reports page    # file work → it lands on the board
/start            # board-driven: claim unassigned flow:inbox tickets and drive each end-to-end (PMO → DEV → QC)
```

**`/start` là board-driven** — nó poll GitHub Project board của repo này, chỉ xét **các ticket `flow:inbox` chưa được assign** cho công việc mới (bao gồm cả ticket được con người chuyển ngược về `flow:inbox` sau khi review PR — pipeline chạy lại và đọc feedback của con người trên PR), **claim** một cái bằng cách tự assign, và điều khiển ticket đó end-to-end qua **PMO → DEV → QC**, chỉ break ngược lại cho bạn khi ticket rơi vào lane can thiệp của con người `flow:refined` (thiếu info/quyết định, hoặc escalate sau khi vượt ngưỡng `max_rework_returns`), một DEV card bị block, hoặc một PR đã sẵn sàng để merge. Con người xử lý một ticket `flow:refined` bằng `/review-refined` rồi đưa nó về `flow:inbox`. Nhiều terminal `/start` có thể chạy song song trên cùng một repo — GitHub **assignee** chính là cái claim (lưu ý: mọi terminal dùng chung một token, nên để cô lập nghiêm ngặt hãy cấp cho mỗi terminal một GitHub identity riêng). **`/start` không intake công việc**; công việc mới vào qua **`/task <description>`** hoặc bằng cách thả một card lên board. Bạn vẫn làm hai việc bằng tay: **mô tả công việc** (`/task` / một board card) và **review/merge PR**.

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
      scopes: ["repo", "read:org", "project"]  # project: the board is required
      cli: "gh auth login"               # companion path used for label/PR ops
    mcp:
      server: "github"                   # → .mcp.json mcpServers.github
      requires_env: ["GITHUB_TOKEN"]     # server won't start without this
```

Một connection **chỉ dùng được khi `enabled: true` AND mọi biến trong yêu cầu `auth`/`mcp` của nó đều có mặt.** Bỏ hẳn block `mcp` cho một service không có MCP server. Connections mang tính cộng dồn — tắt một cái bằng `enabled: false`, hoặc copy một block để thêm cái của riêng bạn.

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
| `github_project` | **Bắt buộc** Projects v2 board — inbox queue của orchestrator cộng với một mirror để **con người** thấy các label `flow:*` trên một Status field. Dùng `github` MCP server + `gh` (không có server riêng). | `owner`, `owner_type`, `auth.scopes` | Bắt buộc (`project` scope); xem skill `project-board-protocol`. |
| `figma` | Nguồn design tùy chọn cho DEV trong lúc làm UI. | `auth.method: oauth`, `mcp.server`, `files` | Official server đăng nhập qua **OAuth** (`/mcp` → Authenticate); `FIGMA_TOKEN` kiểu cũ chỉ cho REST fallback. Xem skill `figma-design`. |

Thêm cái của riêng bạn cũng theo pattern đó: khai báo secret dưới `env:`, copy một block `connections.<name>` (`enabled`, `auth.{token_env,scopes}`, một `mcp.{server,requires_env}` tùy chọn nếu nó có server, cộng metadata của service), và wire bất kỳ MCP server mới nào vào `.mcp.json`. Agent **gate before use**: một skill kiểm tra `enabled` và rằng mọi biến env bắt buộc đều có mặt trước khi chạm vào service, và degrade gracefully nếu không. Toàn bộ contract của registry — đọc connections, map sang env + MCP, gate-before-use, secret hygiene, và cách thêm một service — nằm trong skill `setup-agentflow`.

---

## Surfaces

Một **surface** là một phần build được của project, và `surfaces:` là một **dynamic, open map** — bạn chỉ khai báo những surface bạn thực sự có, và bạn tự chọn tên key (`backend`, `web`, `api`, `admin`, `mobile`, … hoặc chỉ `"."` cho repo một surface). **Có project chỉ có backend; có project chỉ là mobile app; có project trộn nhiều thứ.** AgentFlow không bao giờ giả định bộ ba backend/frontend/mobile đều có mặt — DEV và QC lặp qua bất kỳ surface nào tồn tại. Bạn cung cấp shell command; không có gì được suy ra từ framework.

```yaml
surfaces:
  backend:                  # the key is yours — could be "api", "web", "mobile", "." …
    path: "api/"            # "." for a single-surface repo
    label: "component/backend"
    commands:
      install:     "go mod download"
      lint:        "golangci-lint run"
      test:        "go test ./..."
      integration: "go test -tags=integration ./..."
      e2e:         ""           # "" = skip this command type
      build:       "go build ./..."
    coverage_command:   "go test -cover ./... | …"
    coverage_threshold: 70
    forbidden_paths: []
```

Mỗi surface map tới một **label `component/<surface>`**, được init sinh ra khớp với các surface key (một cái cho mỗi surface đã khai báo). PMO gắn tag cho issue với các surface mà nó chạm tới; DEV và QC sau đó **chỉ** chạy command của **những surface đó**. Đây chính là điều làm QC trở nên **surface-aware**:

- Một **QC tier** là một **list các command-type**, không phải list shell command:
  - `quick` = `["lint","test"]`
  - `full` = `["lint","test","integration"]`
  - `regression` = `["lint","test","integration","e2e"]` (cộng dồn: `quick ⊆ full ⊆ regression`)
- Để chạy một tier cho một issue: với **mỗi surface** issue chạm tới, chạy `commands.<type>` của surface đó cho **mỗi type** trong tier, theo thứ tự. Tất cả phải exit `0`; một command rỗng (`""`) thì bị bỏ qua. Coverage dùng `coverage_command` / `coverage_threshold` của surface được chạm tới, fallback về `agents.qc.coverage_threshold`.

---

## Skills

### Core skills (đi kèm plugin)

Agent load các skill này on demand; mỗi cái là một `SKILL.md` dưới `skills/<name>/`. Không cần đăng ký.

| Skill | Dùng để làm gì |
|-------|----------------|
| `setup-agentflow` | Skill onboarding / meta. Single source of truth `agentflow.yaml`, đặc tả connection đầy đủ (token + MCP server + scopes), block `env:`, dynamic surfaces, registry project-skill + convention role-prefix, cách `/agentflow-init` bootstrap, và secret hygiene. |
| `project-board-protocol` | GitHub wire protocol: label `flow:*`, comment prefix, Definition of Ready/Done, sticky state comment, rework loop, human PR-feedback re-entry, và trust rule — cộng với phần **bắt buộc** về GitHub Projects v2 board (inbox queue + human mirror). Đọc trước khi chạm vào bất kỳ board artifact nào. |
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

- **Auto-discover** — một agent cũng load bất kỳ `.claude/skills/<its-role>-*` nào có mặt kể cả khi nó không được liệt kê; việc đăng ký chỉ làm cái nhìn tổng quan tường minh hơn.

Một agent load các role-prefixed skill của role nó mà liên quan tới (các) surface issue hiện tại chạm tới (khớp một entry `surfaces` trong registry với các label `component/*` của issue; một skill không có `surfaces` — hoặc không nằm trong registry — thì luôn liên quan). `/agentflow-init` có thể scaffold các starter stub và điền registry `skills:` giúp bạn.

---

## Commands

| Command | Nó làm gì |
|---------|--------------|
| `/agentflow-init` | Bootstrap một lần **theo từng repo**: cấu hình `connections.*`, xác minh secret `env:`, khai báo các `surfaces.*` bạn có kèm command của chúng, scaffold/đăng ký project skill, tạo label `flow:*` + `type/*` + `component/<surface>` + aux, tạo/link Projects v2 board **bắt buộc**, sinh `.claude/agentflow.yaml` và `README.agentflow.md`, và chạy một verification ticket end-to-end. |
| `/start` | Vào board-driven team mode; session claim các ticket `flow:inbox` chưa được assign (kể cả ticket được con người chuyển ngược về `flow:inbox` sau khi review PR) rồi điều khiển mỗi cái end-to-end qua các agent (hỗ trợ terminal song song; poll liên tục opt-in qua skill `/loop`). **Không intake công việc.** |
| `/task <description>` | Lập một work item mới từ một mô tả tự do (PMO sở hữu việc intake) và thêm nó vào board. |
| `/review-refined` | Phiên review tương tác giữa con người ↔ agent cho một ticket `flow:refined` đang bị block: thu thập info/quyết định còn thiếu, chỉnh lại ticket, rồi re-label về `flow:inbox` để dòng chảy tiếp tục (PMO re-triage). |
| `/status` | In số lượng open-issue theo từng state `flow:*` cho repo này. |

---

## Pipeline hoạt động ra sao

```
happy path:
  flow:inbox → flow:ready-for-dev → flow:in-progress → flow:in-qc → flow:ready-for-human-review → flow:done

QC ❌ rework loop (fail ≤ max_rework_returns = 2):
  flow:in-qc ──❌──▶ flow:ready-for-dev  (+ rework)  ──▶ … ──▶ flow:in-qc

escalation & human-intervention lane (owner: human):
  flow:in-qc ──❌ (fail > 2)──▶ flow:refined
  flow:inbox ──(PMO can't reach DoR: missing info)──▶ flow:refined
  flow:in-progress/ready-for-dev ──(DEV missing spec/Figma)──▶ flow:refined
  flow:in-qc ──(QC: AC genuinely ambiguous)──▶ flow:refined
       flow:refined ──(human adds info via /review-refined)──▶ flow:inbox  (re-enters, PMO re-triages)

human PR-review feedback (con người chủ động):
  flow:ready-for-human-review ──(human feedback inline trên PR + chuyển ticket về inbox)──▶ flow:inbox  (re-enter, PMO re-triage đọc feedback)
```

- **PMO** biến message của bạn thành một issue chỉn chu ngay tại `flow:inbox`, gắn label `type/*` và `component/<surface>`, gate nó qua một **Definition of Ready**, viết một implementation plan **`## For DEV`** cho từng agent và một focus verification **`## For QC`** vào issue body (planning bằng cách mô tả, không phải bằng cách dispatch — nó không bao giờ assign hay điều khiển các agent khác). DoR pass → `flow:ready-for-dev`; nếu cần con người bổ sung info thì park sang `flow:refined` kèm một vòng câu hỏi `[PMO]`. PMO không tự trả lời câu hỏi làm rõ của DEV/QC — mọi info-gap đều để con người xử lý ở `flow:refined`, và PMO re-triage khi ticket quay lại `flow:inbox`. (Không thể viết code hay merge.)
- **DEV** implement một issue trên một **branch đặt tên theo type** (`<branch_prefix><kind>/<issue#>-<slug>`, `kind` lấy từ label `type/*`: feature→feat, bug→fix, improvement→chore) và mở/cập nhật một PR, giữ trong phạm vi acceptance criteria và không bao giờ chạm `forbidden_paths`. **Lint/analyze phải green** cho mọi surface được chạm tới trước khi handoff. (Không thể merge.)
- **QC** đọc implementation diff đối chiếu với AC, **viết automation test** — thêm các test identifier mà suite cần và viết các test flow map tới AC, rồi commit (`test(...)`) và push chúng lên chính branch PR hiện có của DEV — chạy **QC tier** đã cấu hình (giờ bao gồm cả các test đó) đối với các surface được chạm tới ở local, và ký duyệt (`[QC] ✅`, sẵn sàng merge) hoặc từ chối (`[QC] ❌`). Mỗi lần từ chối (còn trong ngưỡng `max_rework_returns` = 2) route ticket ngược về `flow:ready-for-dev` kèm aux label `rework` để DEV sửa; sau khi vượt ngưỡng, lần ❌ kế tiếp escalate lên `flow:refined` — lane can thiệp của con người. (Có `Edit`/`Write` cho test chỉ trên branch PR — không bao giờ đổi implementation logic, không bao giờ merge.)
- **Bạn** review và merge — hoặc để lại **feedback inline trực tiếp trên code của PR** rồi **chuyển ticket về `flow:inbox`**: pipeline chạy lại từ PMO — PMO đọc feedback của bạn trên PR, fold vào spec/AC rồi re-gate DoR; DEV **amend chính PR/branch hiện có** (không build lại từ đầu), QC re-gate trước khi nó quay lại cho bạn. Orchestrator không bao giờ merge nếu không có chỉ thị tường minh của bạn.

Role boundary không chỉ là prose — chúng được enforce bằng tool grant của từng agent (PMO không có `Edit`/`Write`; **QC có `Edit`/`Write` cho test ID + test file chỉ trên branch PR — không bao giờ đụng implementation logic**; chỉ DEV tạo branch/PR và push feature code; chỉ QC có các PR-review tool). Cả ba agent đều giữ tool `Skill` để load core skill và role-prefixed skill của chúng. Toàn bộ wire protocol — comment prefix, DoR/DoD, state comment, và trust rule — là skill `project-board-protocol`.

---

## Cấu hình

Mọi setting nằm trong **`.claude/agentflow.yaml`** (sinh ra bởi `/agentflow-init`; template là schema có thẩm quyền). Những thứ bạn hay tinh chỉnh:

- **`connections.*`** — bật/tắt và cấu hình `github`, `github_project`, `figma`, hay service của riêng bạn. Mỗi cái đặc tả đầy đủ `enabled`, `auth.{token_env,scopes}`, và (nếu có) `mcp.{server,requires_env}`. Xem skill `setup-agentflow`.
- **`env:`** — danh sách các secret `{ name, required, used_by, description }` mà các connection cần. **Chỉ tên**, không bao giờ giá trị.
- **`surfaces.<key>`** — `path`, `label`, `commands.{install,lint,test,integration,e2e,build}` theo từng type, `coverage_command`, `coverage_threshold`, `forbidden_paths`. Open map: thêm, đổi tên, hay xóa surface tùy ý — chỉ khai báo cái bạn có.
- **`skills.<name>`** — registry của các project skill, `{ role, surfaces?, description? }`. Single source of truth cho việc mỗi role load thêm skill nào.
- **`agents.qc.tiers.{quick,full,regression}`** — **list các command-type**. Command thực tế resolve theo từng surface từ `surfaces.<name>.commands.<type>`.
- **`agents.qc.coverage_threshold`** — coverage gate fallback khi một surface được chạm tới không định nghĩa cái nào (`0` để tắt).
- **`agents.dev.forbidden_paths`** — các glob mà DEV không bao giờ được chạm (CI config, infra, secrets, keystore), enforce cho mọi surface bên cạnh `forbidden_paths` riêng của từng surface. Được backed bởi prompt + một QC review check.
- **`board.id`** — node ID của Projects v2 (một `PVT_…` không rỗng; board là bắt buộc). Mirror `connections.github_project.enabled` (luôn `true`; init giữ chúng đồng bộ).

`README.agentflow.md` (cũng được sinh vào target repo) là quick reference hàng ngày cho người dùng của repo đó.

---

## Ghi chú & giới hạn

- **Mặc định synchronous; continuous là opt-in.** Mặc định, chính việc break-out ở terminal *là* notification — không có kênh bên ngoài nào (Telegram/Zalo/v.v.). Bạn có thể chạy `/start` không cần giám sát theo một interval qua skill `/loop` (cadence thích ứng, không phải busy-loop); các break-out khi đó xếp hàng bền vững trên board (state `flow:*` được park + comment) cho tới khi bạn quay lại. Xem `/start` → "Continuous mode".
- **Cái claim chính là GitHub `assignee`** cộng với label `flow:*`. `/start` chỉ luôn lấy các ticket `flow:inbox` chưa được assign rồi tự assign để claim, nên **nhiều terminal `/start` có thể chạy song song** trên cùng một repo. Mọi terminal dùng chung một token (cùng một GitHub user), nên assignee de-dupe được nhưng không phân biệt được các terminal — một race nhỏ ở lúc claim inbox là có thể xảy ra (backstop `flow:in-progress` của DEV bắt được nó); để cô lập nghiêm ngặt hãy cấp cho mỗi terminal một GitHub identity riêng.
- **Safety rule ở mức prompt.** `forbidden_paths`, merge gate, và trust model là các chỉ thị cho agent, được backed bởi việc tách tool-grant — không phải bằng enforced hook. Dùng token least-privilege và review PR trước khi merge.
- **Board là bắt buộc; Figma là tùy chọn.** GitHub Projects v2 board (`connections.github_project.enabled: true`, một `board.id` không rỗng) là inbox queue + human mirror của orchestrator và được set up lúc init; connection `figma` chỉ kích hoạt khi MCP server của nó được authenticate (OAuth qua `/mcp` → figma → Authenticate). Connection `github` và board là các yêu cầu cứng.
- **Comment GitHub không có prefix là untrusted.** Agent coi bất kỳ comment nào không có prefix `[PMO]` / `[DEV]` / `[QC]` / … được nhận diện là context untrusted, không phải chỉ thị.

---

## Non-goals — những gì KHÔNG được thay đổi

Những điều này là load-bearing, dễ bị bào mòn bởi sự tích lũy có thiện chí, và cố tình được đặt như vậy. Hãy coi thay đổi ở đây là design change, không phải cải tiến:

- **Label `flow:*` là routing truth duy nhất; board là inbox queue bắt buộc + một human mirror.** Board là bắt buộc (nó là inbox queue của `/start` và là mirror để con người thấy), nhưng đừng bao giờ để một board column hay một câu trả lời tường thuật của sub-agent trở thành *nguồn* routing — column không bao giờ được đọc để routing. Việc đọc lại label live sau mỗi lần chạy chính là thứ làm cho thiết kế no-message-bus hoạt động.
- **Role isolation bằng tool grant, không phải prose.** PMO không có `Edit`/`Write`; **QC giờ có `Edit`/`Write` nhưng chỉ để thêm test ID + viết test trên branch PR — không bao giờ đổi implementation logic và không bao giờ merge**; chỉ DEV làm feature implementation (branch/push); chỉ con người merge. Việc cấp quyền viết test cho QC là có chủ đích — đừng nới rộng tool của bất kỳ role nào thêm nữa "để phòng hờ", vì cả ba agent dùng chung một token, nên blast radius là thật.
- **Human merge gate là bắt buộc.** Agent dừng ở `flow:ready-for-human-review`; chỉ con người merge. Đây là chỗ ma sát duy nhất đáng với cái giá của nó — đừng automate merge.
- **Safety rule (`forbidden_paths`, trust model) là prompt + tool-grant, không phải enforced hook** — và docs nói thẳng như vậy. Đừng che đậy điều đó bằng prose `NEVER …` ngày càng dài làm phình mỗi lần chạy để đổi lấy an toàn giả; enforcement thật thuộc về một hook/CI check.
- **Việc load skill lười, tách nhỏ vẫn giữ lười.** Các cơ chế nặng nằm trong file `reference/` chỉ đọc khi cần (`projects-v2-board.md`). Đừng front-load cơ chế board vào mỗi agent prompt.
- **Đừng làm phình sticky `AGENTFLOW-STATE` comment.** Ba agent prose-edit nó và phải giữ tương thích format; mỗi field bắt buộc mới là một bề mặt drift mới. Ưu tiên ít field hơn, không phải nhiều hơn.
- **Optional connection degrade gracefully.** Một *optional* service bị disable/vắng mặt (ví dụ figma) được bỏ qua kèm một note, không bao giờ là một hard block. Đừng làm cứng optional connection thành precondition chặn cứng. (Connection `github` và board là ngoại lệ — cả hai đều bắt buộc.)
