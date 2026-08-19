# AgentFlow

Một Claude Code plugin biến một coding agent đơn lẻ thành một team nhỏ có trách nhiệm rõ ràng: **bạn là Product Owner**, **DEV** implement, **QC** verify. Bạn chỉ làm hai việc bằng tay — **chốt việc cần làm** và **review/merge PR cuối cùng**.

AgentFlow **tech-stack-agnostic**. Cài **một lần**, chạy theo từng repo. Bốn điểm cốt lõi:

- **Con người ở trong vòng lặp, đúng chỗ nó có giá trị.** Intake và refine (viết AC, chọn QC tier, gate Definition of Ready) chạy **tương tác ngay trong session** — hỏi đáp trực tiếp với bạn. Không sub-agent nào tự viết spec rồi tự làm theo spec của chính nó.
- **Board 6 cột, một bất biến.** `Inbox · Ready for Dev · In Progress · In QC · Ready for Review · Done`. **Cột do agent sở hữu không bao giờ giữ ticket ở trạng thái nghỉ** — agent không đi tiếp được thì ticket về `Inbox` + label `blocked`. Không có ticket nào kẹt vô hình.
- **Config ~15 dòng.** `agentflow.yaml` ở root repo chỉ giữ thứ **không suy ra được**: URL board, surfaces, design source, notify. Owner/owner_type/number của board parse từ chính URL đó; repo/branch/owner suy từ `git remote` mỗi run; tên column, label, MCP wiring, ngưỡng rework là **hằng số plugin**.
- **Mọi secret một chỗ, theo từng repo.** `GITHUB_TOKEN` — cùng `TELEGRAM_*` và `FIGMA_TOKEN` — sống trong block `env` của **`.claude/settings.local.json`**, file mà `/agentflow:init` bắt buộc phải thấy đã gitignore *trước khi* nói tới token. Đổi lại rủi ro "secret nằm trong working tree": mỗi clone một token, nên mỗi repo chạy được dưới một GitHub identity riêng.

Không có message bus. Agent giao tiếp hoàn toàn qua GitHub primitives: **`Status` field trên Projects v2 board** (state authoritative), **issue comment có prefix** (audit trail duy nhất của transition), và **một section `AGENTFLOW-STATE` trong issue body** (memory giữa các lần chạy). Label không mang state.

---

## Yêu cầu

| Đường | Dùng cho | Authenticate |
|---|---|---|
| **GitHub MCP server** (official, hosted tại `https://api.githubcopilot.com/mcp/`) | mọi GitHub-API op: issue, branch, PR, review, comment, label, và board | `${GITHUB_TOKEN}` → header `Authorization: Bearer` |
| **local `git`** (qua `Bash`) | VCS trên working tree: branch, commit, push, checkout, rebase | remote + credential sẵn có của repo |
| **Figma MCP server** *(tùy chọn)* (`https://mcp.figma.com/mcp`) | kéo frame spec/token khi làm UI | **OAuth** — `/mcp` → `figma` → Authenticate |

1. **Một GitHub token cho mỗi repo** — thêm vào block `env` của **`.claude/settings.local.json`** trong repo đó:

   ```json
   {
     "env": { "GITHUB_TOKEN": "ghp_…" }
   }
   ```

   `.mcp.json` của plugin đọc nó qua `${GITHUB_TOKEN}`. **File này phải được gitignore** — `/agentflow:init` §1a tự thêm dòng đó vào `.gitignore` và **từ chối chạy tiếp** nếu vẫn chưa ignore được (vd file đang bị git track).

   > **Đừng chẩn đoán bằng `claude mcp list`** — nó không nạp project settings nên báo `Missing environment variables` kể cả khi token đã đặt đúng. Dùng `/agentflow:init`: nó probe `get_me` ngay trong session. Một `export GITHUB_TOKEN=…` còn sót trong shell sẽ **đè** giá trị của file.
   >
   > **Restart là bắt buộc khi đổi token.** MCP server connect lúc boot, nên đổi xong phải thoát Claude Code và mở lại.

2. **Token scopes** — `repo` + `project` (+ `read:org` cho org board). Dùng **classic PAT**: fine-grained PAT chưa được verify cho Projects v2 user-owned board; board-write smoke test của init là nơi phát hiện token sai loại. Một classic PAT với `repo` cấp quyền write rộng tới *mọi* repo mà token vươn tới, và cả hai agent dùng chung token này — coi nó là secret.

3. **Một git repo với GitHub remote** — `git remote get-url origin` phải resolve được.

| Giá trị | Bắt buộc | Sống ở đâu | Dùng cho |
|---|---|---|---|
| `GITHUB_TOKEN` | **có** | `env` trong `.claude/settings.local.json` (theo repo, gitignored) | GitHub API + board |
| `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` | không | như trên | `notify` — ping khi pipeline dừng chờ bạn |
| `FIGMA_TOKEN` | không | như trên | chỉ REST/Framelink fallback; official server dùng OAuth |

Một file phục vụ cả hai đích: `curl` đọc nó như subprocess, `.mcp.json` expand `${VAR}` từ chính env đó. Xem [`DESIGN-NOTES.md`](DESIGN-NOTES.md).

---

## Cài đặt

Plugin khai báo `defaultEnabled: false`, nên **cài xong nó nằm im — bạn phải tự bật**. Đây là chủ ý: AgentFlow cầm `GITHUB_TOKEN` và ghi lên board thật, nên nó không được tự chạy chỉ vì có mặt trong marketplace. Bước `enable` là chỗ bạn nói "đồng ý, repo này dùng AgentFlow".

```bash
# đường dẫn TUYỆT ĐỐI hoặc ./path tới thư mục chứa .claude-plugin/marketplace.json
# (dấu "." trần bị từ chối). Team dùng chung → dùng dạng owner/repo.
claude plugin marketplace add /path/to/Plugins

# đứng TRONG repo muốn dùng:
claude plugin install agentflow@agent-flow-plugins --scope local
claude plugin enable  agentflow@agent-flow-plugins --scope local
# rồi đặt GITHUB_TOKEN trong env của .claude/settings.local.json (xem §Yêu cầu)
```

**`--scope local` là mặc định khuyến nghị.** Nó ghi vào `.claude/settings.local.json` của chính repo — gitignored, theo từng repo, không lan sang teammate — tức **cùng một file đang giữ `GITHUB_TOKEN`**. Nhờ vậy "repo nào đã bật AgentFlow" và "repo nào có token" luôn khớp nhau ở đúng một chỗ, thay vì plugin bật toàn máy còn token thì chỉ vài repo có. `--scope user` cài chung cho mọi repo — chỉ chọn khi bạn thực sự muốn mọi project đều thấy plugin. Sau khi enable, **restart Claude Code**.

Quy trình dev/release plugin: [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Bắt đầu nhanh

Command của plugin **luôn mang namespace `agentflow:`** — gõ `/agentflow` rồi để autocomplete gợi ý. Tên trần (`/task`, `/start`) không tồn tại.

```text
/agentflow:init                                       # setup một lần cho REPO NÀY
/agentflow:task thêm nút export CSV vào trang reports # hỏi đáp → AC chốt → lên board
/agentflow:start                                      # board-driven: drain queue, chain DEV → QC
```

---

## Pipeline

```
/agentflow:task <mô tả> ──(hỏi đáp → DoR pass)──▶ Ready for Dev
              └─(bạn hoãn / thiếu quyết định)──▶ Inbox +blocked

happy path:  Inbox ─spec pass─▶ Ready for Dev ─▶ In Progress ─▶ In QC ─▶ Ready for Review ─▶ Done
QC ❌ (≤2):   In QC ──▶ Ready for Dev +rework
về tay bạn:  In Progress ─DEV thiếu spec/Figma, blocker môi trường──▶ Inbox +blocked
             In QC ─AC mơ hồ · escalate (>2 fail) · infra stop─────▶ Inbox +blocked
PR feedback: Ready for Review ─bạn comment inline trên PR + KÉO CARD──▶ Inbox
```

- **Bạn (+ session)** sở hữu `Inbox`. Spec pass biến mô tả thành issue chuẩn theo **template riêng của từng `type/*`** (feature: user story + design pointer · bug: repro + mong đợi/thực tế + bằng chứng + severity · improvement: baseline→target đo được + hành vi không đổi), cộng phần chung: Context, AC Given/When/Then đánh số, Out of Scope, size (định nghĩa ở `agentflow-protocol` §4), QC tier, và hai section định hướng `## For DEV` / `## For QC`. **Ticket mô tả hành vi quan sát được, không nói bằng code** — không file, không tên hàm, không chọn thư viện; cách hiện thực là quyết định của DEV sau khi đọc source. Gate DoR sống ở **đúng một chỗ** — `/agentflow:task` §Spec pass.
- **DEV** implement trên branch đặt tên theo type (`agent/dev/<kind>/<issue#>-<slug>`) và mở/cập nhật PR, giữ trong phạm vi AC, không bao giờ chạm forbidden paths. Với mỗi surface bị chạm: lint/analyze **phải** green trước khi handoff. (Không bao giờ merge.)
- **QC** đọc diff đối chiếu AC, **author automation test** (thêm test ID + viết test flow map tới AC) rồi commit/push lên chính PR branch của DEV, chạy các test category mà QC tier ngụ ý ở local, và ký duyệt `[QC] ✅` hoặc từ chối `[QC] ❌`. Từ chối trong ngưỡng → `Ready for Dev` + `rework`; quá 2 lần liên tiếp → escalate về `Inbox +blocked`. (Chỉ đụng test file/test ID. Không bao giờ merge.)
- **Bạn** review và merge — hoặc để **feedback inline trên code của PR** rồi **kéo card về `Inbox`**: spec pass đọc feedback đó, fold vào AC, DEV **amend chính PR đó** (không build lại), QC re-gate.

**`/agentflow:start` bỏ qua ticket mang `blocked`** — nó đang chờ một quyết định của bạn, và chỉ `/agentflow:task #<n>` mới gỡ. Đây là chủ ý: nếu không, mỗi vòng poll (nhất là dưới `/loop`) sẽ hỏi lại bạn cùng một câu.

---

## Commands

| Command | Nó làm gì |
|---|---|
| `/agentflow:init` | Bootstrap một lần **theo từng repo**: verify GitHub auth, resolve owner canonical (remote có thể stale sau transfer), detect surfaces, tạo label, tạo/link board — Status field 6 option + link board↔repo + view `Pipeline` set tự động khi có `gh`, fallback UI thủ công — ghi `agentflow.yaml` + `.claude/settings.local.json`, rồi chạy board-write smoke test. Còn đúng một bước tay: 3 built-in workflow. |
| `/agentflow:task <mô tả>` | **Intake tương tác** — hỏi đáp để chốt AC, tạo issue, lên board. |
| `/agentflow:task #<n>` | **Gỡ một ticket đang kẹt** (`Inbox +blocked`) hoặc re-spec sau PR feedback. Đây là đường chính thức đưa ticket trở lại pipeline. |
| `/agentflow:start` | Vào board-driven team mode: claim ticket chưa assign ở `In QC` → `Ready for Dev` → `Inbox` (việc đã bắt đầu trước việc mới), tự chạy spec pass khi đủ dữ kiện, rồi chain DEV → QC. Poll liên tục opt-in qua skill `/loop`. |
| `/agentflow:status` | Đếm board item theo từng cột (tách riêng số `blocked`, và số ticket đã close mà Status còn kẹt ngoài `Done`). `--audit` chạy membership hai chiều + reconcile + orphan check; `--metrics` tính flow metrics (throughput, cycle time, first-pass yield, rework/escalation/blocked rate, WIP, aging) suy ra từ transition comment. |
| `/agentflow:improve [bài học]` | Capture bài học từ usage thực tế và fold vào đúng file tri thức trong plugin **SOURCE** — minimal edit có duyệt diff, bump version, chạy release loop. |

## Skills

Bốn core skill đi kèm plugin, load on demand, không cần đăng ký:

| Skill | Dùng để làm gì |
|---|---|
| `agentflow-protocol` | **Contract lõi.** Config, hằng số plugin, 6 state + bất biến, shape của Status write, comment prefix, DoR/DoD, section AGENTFLOW-STATE, read/write order, rework loop, trust rules. Phần **chỉ orchestrator/init cần** — queue, `status_map`, tạo/link board, lane của con người, claim, scopes — nằm trong `references/projects-v2-board.md`, và DEV/QC **không** load nó. |
| `git-flow-working` | Branching tech-agnostic, Conventional Commits, PR convention, an toàn rebase/merge. |
| `design-handoff` | Nguồn design của repo → implementation: dispatch theo `design.kind` (`repo` · `artifact` · `design-system` · `figma`), extract token/component, ghi revision đã build, và ba ca ranh giới design↔AC. DEV load khi chạm UI; QC load để verify đúng revision đó. |
| `figma-design` | Provider Figma của `design-handoff` — MCP tool (REST fallback), parse URL/node id. |

Công thức spec pass (ba template body theo `type/*`, luật ngôn ngữ ticket, AC, QC tier, tag component, DoR gate, write order, fold PR feedback) **không** là skill riêng — nó sống trong `commands/task.md` §Spec pass, nơi duy nhất chạy nó, với hai chế độ: interactive (`/agentflow:task`) và autonomous (`/agentflow:start` khi nhặt card `Inbox`).

**Project skill** mở rộng theo từng repo: thả một skill vào `.claude/skills/` đặt tên `dev-*` hoặc `qc-*` — agent tương ứng **auto-discover** nó. Không có registry nào phải giữ đồng bộ. `/agentflow:init` scaffold được các stub khởi đầu (luôn đề xuất `qc-automation-test`).

## Cấu hình

`agentflow.yaml` ở **root repo** cố tình chỉ giữ thứ **không suy ra được**:

```yaml
schema: 2
board:   { url: "https://github.com/orgs/passion-ui/projects/11" }   # hoặc /users/<login>/projects/<N>
surfaces:                       # BỎ HẲN block này nếu repo single-surface
  api:    { path: "api/" }
  mobile: { path: "app/", forbidden: ["android/key.properties"] }
design:  { kind: repo, path: "docs/design", screens: "screens/*.html", tokens: "css/app.css" }
notify:  { enabled: false, events: ["blocked", "ready_for_review"] }
```

`board.url` là nguồn duy nhất cho `owner` + `owner_type` + `project_number` của mọi call `projects_*` — dán nguyên URL từ trình duyệt, và board **được phép** thuộc owner khác repo. Mọi thứ khác đến từ ba nguồn còn lại: **suy từ git** (repo, owner, default branch), **hằng số plugin** (6 tên column, label, branch prefix, global forbidden paths `**/*.pem` + `**/.env`, ngưỡng rework `2`, ý nghĩa QC tier), và **auto-discovery** (project skill). Quy tắc khi phân vân: *hành vi agent → yaml · công cụ/harness và mọi secret → `.claude/settings.local.json`.*

**`forbidden`** (top-level) là tùy chọn — list glob no-touch cấp repo, hợp với global và với `forbidden` của surface bị chạm.

**Surfaces** là tùy chọn — vắng mặt nghĩa là single-surface, DEV/QC gate toàn repo. Có mặt thì mỗi key sinh một label `component/<key>`; spec pass tag issue, DEV/QC chỉ build/lint/test những surface đó theo convention của chính repo (không có command nào trong config).

**Design source** là tùy chọn và có 5 `kind`. `repo` (prototype trong repo) là kind duy nhất **pin được theo commit** — design đổi là một commit, hiện trong PR diff. Ba kind cloud (`artifact`, `design-system`, `figma`) cho phép designer sửa mà không cần push repo, đổi lại design có thể đổi giữa chừng pipeline: DEV bắt buộc ghi `design: <kind> @ <revision>` vào comment handoff, QC verify đúng revision đó. `design-system` lưu **component kit**, không phải screens.

**QC tier** là gợi ý độ sâu test cố định trong plugin: `quick` = lint + unit · `full` = + integration · `regression` = + e2e (cộng dồn). Không có coverage gate bằng số — QC đánh giá test adequacy bằng inspection.

---
