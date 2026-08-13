# AgentFlow

Một Claude Code plugin biến một coding agent đơn lẻ thành một team nhỏ có trách nhiệm rõ ràng: **bạn là Product Owner**, **DEV** implement, **QC** verify. Bạn chỉ làm hai việc bằng tay — **chốt việc cần làm** và **review/merge PR cuối cùng**.

AgentFlow **tech-stack-agnostic**. Cài **một lần**, chạy theo từng repo. Bốn điểm cốt lõi:

- **Con người ở trong vòng lặp, đúng chỗ nó có giá trị.** Intake và refine (viết AC, chọn QC tier, gate Definition of Ready) chạy **tương tác ngay trong session** — hỏi đáp trực tiếp với bạn. Không sub-agent nào tự viết spec rồi tự làm theo spec của chính nó.
- **Board 6 cột, một bất biến.** `Inbox · Ready for Dev · In Progress · In QC · Ready for Review · Done`. **Cột do agent sở hữu không bao giờ giữ ticket ở trạng thái nghỉ** — agent không đi tiếp được thì ticket về `Inbox` + label `blocked`. Không có ticket nào kẹt vô hình.
- **Config ~15 dòng.** `agentflow.yaml` ở root repo chỉ giữ thứ **không suy ra được**: board number, surfaces, hai toggle. Repo/branch/owner suy từ `git remote` mỗi run; tên column, label, MCP wiring, ngưỡng rework là **hằng số plugin**.
- **Token GitHub không nằm trong repo.** Nó là biến `GITHUB_TOKEN` trong block `env` của `~/.claude/settings.json` — settings **user-global**, ngoài mọi repo, nên không file nào trong repo chứa nó và không có gì để lỡ tay commit. Secret mà *shell* phải đọc (`TELEGRAM_*` cho notify, `FIGMA_TOKEN`) thì ở `.claude/settings.local.json` của repo.

Không có message bus. Agent giao tiếp hoàn toàn qua GitHub primitives: **`Status` field trên Projects v2 board** (state authoritative), **issue comment có prefix** (audit trail duy nhất của transition), và **một section `AGENTFLOW-STATE` trong issue body** (memory giữa các lần chạy). Label không mang state.

---

## Yêu cầu

| Đường | Dùng cho | Authenticate |
|---|---|---|
| **GitHub MCP server** (official, hosted tại `https://api.githubcopilot.com/mcp/`) | mọi GitHub-API op: issue, branch, PR, review, comment, label, và board | `${GITHUB_TOKEN}` → header `Authorization: Bearer` |
| **local `git`** (qua `Bash`) | VCS trên working tree: branch, commit, push, checkout, rebase | remote + credential sẵn có của repo |
| **Figma MCP server** *(tùy chọn)* (`https://mcp.figma.com/mcp`) | kéo frame spec/token khi làm UI | **OAuth** — `/mcp` → `figma` → Authenticate |

1. **Một GitHub token, cấu hình một lần cho cả máy** — thêm vào block `env` của **`~/.claude/settings.json`**:

   ```json
   {
     "env": { "GITHUB_TOKEN": "ghp_…" }
   }
   ```

   `.mcp.json` của plugin đọc nó qua `${GITHUB_TOKEN}`. File này nằm ngoài mọi repo nên không có gì để lỡ tay commit.

   > **Phải là settings user-global — `.claude/settings.local.json` của repo KHÔNG dùng được cho biến này.** `.mcp.json` chỉ expand `${VAR}` từ môi trường thật của tiến trình, từ `~/.claude/settings.json`, hoặc từ `--settings`; block `env` project-scope tới được subprocess (nên `curl` thấy `TELEGRAM_*`) nhưng **không** tới được bước expand config. Đặt `GITHUB_TOKEN` ở file local của repo thì server fail y như chưa đặt.
   >
   > **Restart là bắt buộc khi đổi token.** MCP server connect lúc boot, nên đổi xong phải thoát Claude Code và mở lại.

2. **Token scopes** — `repo` + `project` (+ `read:org` cho org board). Dùng **classic PAT**: fine-grained PAT chưa được verify cho Projects v2 user-owned board; board-write smoke test của init là nơi phát hiện token sai loại. Một classic PAT với `repo` cấp quyền write rộng tới *mọi* repo mà token vươn tới, và cả hai agent dùng chung token này — coi nó là secret.

3. **Một git repo với GitHub remote** — `git remote get-url origin` phải resolve được.

| Giá trị | Bắt buộc | Sống ở đâu | Dùng cho |
|---|---|---|---|
| `GITHUB_TOKEN` | **có** | `env` trong `~/.claude/settings.json` (user-global) | GitHub API + board |
| `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` | không | `env` trong `.claude/settings.local.json` (theo repo, gitignored) | `notify` — ping khi pipeline dừng chờ bạn |
| `FIGMA_TOKEN` | không | như trên | chỉ REST/Framelink fallback; official server dùng OAuth |

Hai đích khác nhau vì **hai cơ chế đọc khác nhau**, không phải vì sở thích: header của MCP server được expand ở một bước chỉ thấy môi trường thật / settings user-global, còn `curl` chạy như subprocess nên đọc được cả `env` project-scope. Xem §Non-goals.

---

## Cài đặt

```bash
# đường dẫn TUYỆT ĐỐI hoặc ./path tới thư mục chứa .claude-plugin/marketplace.json
# (dấu "." trần bị từ chối). Team dùng chung → dùng dạng owner/repo.
claude plugin marketplace add /path/to/Plugins
claude plugin install agentflow@agent-flow-plugins     # --scope user (mặc định) | project | local
# rồi đặt GITHUB_TOKEN trong env của ~/.claude/settings.json (xem §Yêu cầu)
```

`--scope user` cài **một bản dùng chung cho mọi repo trên máy** — đúng tinh thần "cài một lần, chạy theo từng repo". Rồi **restart Claude Code**. Quy trình dev/release plugin: [`CONTRIBUTING.md`](CONTRIBUTING.md).

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

- **Bạn (+ session)** sở hữu `Inbox`. Spec pass biến mô tả thành issue chuẩn: Context, AC đánh số testable, Out of Scope, size, QC tier, và hai section định hướng `## For DEV` / `## For QC`. Gate DoR sống ở **đúng một chỗ** — `/agentflow:task` §Spec pass.
- **DEV** implement trên branch đặt tên theo type (`agent/dev/<kind>/<issue#>-<slug>`) và mở/cập nhật PR, giữ trong phạm vi AC, không bao giờ chạm forbidden paths. Với mỗi surface bị chạm: lint/analyze **phải** green trước khi handoff. (Không bao giờ merge.)
- **QC** đọc diff đối chiếu AC, **author automation test** (thêm test ID + viết test flow map tới AC) rồi commit/push lên chính PR branch của DEV, chạy các test category mà QC tier ngụ ý ở local, và ký duyệt `[QC] ✅` hoặc từ chối `[QC] ❌`. Từ chối trong ngưỡng → `Ready for Dev` + `rework`; quá 2 lần liên tiếp → escalate về `Inbox +blocked`. (Chỉ đụng test file/test ID. Không bao giờ merge.)
- **Bạn** review và merge — hoặc để **feedback inline trên code của PR** rồi **kéo card về `Inbox`**: spec pass đọc feedback đó, fold vào AC, DEV **amend chính PR đó** (không build lại), QC re-gate.

**`/agentflow:start` bỏ qua ticket mang `blocked`** — nó đang chờ một quyết định của bạn, và chỉ `/agentflow:task #<n>` mới gỡ. Đây là chủ ý: nếu không, mỗi vòng poll (nhất là dưới `/loop`) sẽ hỏi lại bạn cùng một câu.

---

## Commands

| Command | Nó làm gì |
|---|---|
| `/agentflow:init` | Bootstrap một lần **theo từng repo**: verify GitHub auth, detect surfaces, tạo label, tạo/link board (Status field 6 option — bước UI thủ công, init validate lại), ghi `agentflow.yaml` + `.claude/settings.json`, rồi chạy board-write smoke test. |
| `/agentflow:task <mô tả>` | **Intake tương tác** — hỏi đáp để chốt AC, tạo issue, lên board. |
| `/agentflow:task #<n>` | **Gỡ một ticket đang kẹt** (`Inbox +blocked`) hoặc re-spec sau PR feedback. Đây là đường chính thức đưa ticket trở lại pipeline. |
| `/agentflow:start` | Vào board-driven team mode: claim ticket chưa assign ở `In QC` → `Ready for Dev` → `Inbox` (việc đã bắt đầu trước việc mới), tự chạy spec pass khi đủ dữ kiện, rồi chain DEV → QC. Poll liên tục opt-in qua skill `/loop`. |
| `/agentflow:status` | Đếm board item theo từng cột (tách riêng số `blocked`, và số ticket đã close mà Status còn kẹt ngoài `Done`). `--audit` chạy membership hai chiều + reconcile + orphan check; `--metrics` tính flow metrics (throughput, cycle time, first-pass yield, rework/escalation/blocked rate, WIP, aging) suy ra từ transition comment. |
| `/agentflow:improve [bài học]` | Capture bài học từ usage thực tế và fold vào đúng file tri thức trong plugin **SOURCE** — minimal edit có duyệt diff, bump version, chạy release loop. |

## Skills

Ba core skill đi kèm plugin, load on demand, không cần đăng ký:

| Skill | Dùng để làm gì |
|---|---|
| `agentflow-protocol` | **Contract lõi.** Config, hằng số plugin, 6 state + bất biến, shape của Status write, comment prefix, DoR/DoD, section AGENTFLOW-STATE, read/write order, rework loop, trust rules. Phần **chỉ orchestrator/init cần** — queue, `status_map`, tạo/link board, lane của con người, claim, scopes — nằm trong `references/projects-v2-board.md`, và DEV/QC **không** load nó. |
| `git-flow-working` | Branching tech-agnostic, Conventional Commits, PR convention, an toàn rebase/merge. |
| `figma-design` | Kéo frame spec/token qua `figma` MCP (có REST fallback) cho handoff design → implementation. |

Công thức spec pass (cấu trúc body, AC, sizing, QC tier, tag component, DoR gate, fold PR feedback) **không** là skill riêng — nó sống trong `commands/task.md` §Spec pass, nơi duy nhất chạy nó, với hai chế độ: interactive (`/agentflow:task`) và autonomous (`/agentflow:start` khi nhặt card `Inbox`).

**Project skill** mở rộng theo từng repo: thả một skill vào `.claude/skills/` đặt tên `dev-*` hoặc `qc-*` — agent tương ứng **auto-discover** nó. Không có registry nào phải giữ đồng bộ. `/agentflow:init` scaffold được các stub khởi đầu (luôn đề xuất `qc-automation-test`).

## Cấu hình

`agentflow.yaml` ở **root repo** cố tình chỉ giữ thứ **không suy ra được**:

```yaml
agentflow: "1.0"
board:   { number: 7, owner_type: user }
surfaces:                       # BỎ HẲN block này nếu repo single-surface
  api:    { path: "api/" }
  mobile: { path: "app/", forbidden: ["android/key.properties"] }
figma:   { enabled: true, files: [{ name: "Design System", key: "AbC123" }] }
notify:  { enabled: false, events: ["blocked", "ready_for_review"] }
```

Mọi thứ khác đến từ ba nguồn còn lại: **suy từ git** (repo, owner, default branch), **hằng số plugin** (6 tên column, label, branch prefix, global forbidden paths `infra/**` + `.github/workflows/**` + `**/*.pem` + `**/.env`, ngưỡng rework `2`, ý nghĩa QC tier), và **auto-discovery** (project skill). Quy tắc khi phân vân: *hành vi agent → yaml · công cụ/harness → `.claude/settings.json` · secret cho MCP → `env` của `~/.claude/settings.json` · secret cho shell → `.claude/settings.local.json`.*

**Surfaces** là tùy chọn — vắng mặt nghĩa là single-surface, DEV/QC gate toàn repo. Có mặt thì mỗi key sinh một label `component/<key>`; spec pass tag issue, DEV/QC chỉ build/lint/test những surface đó theo convention của chính repo (không có command nào trong config).

**QC tier** là gợi ý độ sâu test cố định trong plugin: `quick` = lint + unit · `full` = + integration · `regression` = + e2e (cộng dồn). Không có coverage gate bằng số — QC đánh giá test adequacy bằng inspection.

---

## Ghi chú & giới hạn

- **Mặc định synchronous; continuous là opt-in.** Break-out ở terminal *chính là* notification. Chạy `/agentflow:start` unattended qua skill `/loop`; bật `notify` (Telegram) để biết ngay khi ticket park, thay vì phát hiện muộn. Ping **một chiều tới người** — không agent nào đọc kênh đó, board vẫn là nơi phối hợp duy nhất.
- **Không có agent nào gate DoR thay bạn.** Đây là đánh đổi trực tiếp của thiết kế: chất lượng spec phụ thuộc bạn có mặt lúc intake. Dưới `/loop`, ticket cần quyết định của con người park ở `Inbox +blocked` và loop drain phần còn lại.
- **Claim là GitHub `assignee`** + Status trên board. `/agentflow:start` lấy ticket chưa assign, không mang `blocked`, ở một trong ba cột agent-actionable (`Inbox`, `Ready for Dev`, `In QC`) rồi tự assign — nên **nhiều terminal `/agentflow:start` chạy song song được**, và một turn kết thúc giữa chừng vẫn resume được (orchestrator luôn nhả claim khi dừng, ticket rơi lại vào queue). Mọi terminal trên cùng một máy dùng chung một token (cùng GitHub user) nên còn một race window nhỏ ở bước claim; backstop: re-check Status trước mỗi spawn, và DEV abort khi thấy `In Progress`. `GITHUB_TOKEN` sống ở settings user-global nên là **một giá trị cho mỗi user profile** — không tách identity theo clone được; muốn cô lập nghiêm ngặt thì mỗi identity một máy / user profile.
- **Kéo card là human API chính thức — nhưng chỉ ở parked state**: `Ready for Review` → `Inbox` (PR-feedback re-entry), close issue / merge PR → `Done`. Kéo card khi ticket đang `In Progress` / `In QC` **không an toàn**: compare-then-write bắt được phần lớn nhưng vẫn còn cửa sổ clobber — muốn dừng một run đang chạy, dừng terminal.
- **Status write là mandatory-success.** Fail = **pipeline dừng có chủ đích** (fail-stop), không phải desync. Issue OPEN không có trên board là **vô hình với routing** — `/agentflow:status --audit` phát hiện.
- **Merge PR trên github.com thì nhớ bật built-in workflow `Item closed → Done`.** Bạn có hai đường merge: gõ `merge #<n>` trong `/agentflow:start` (nó ghi Status `Done` explicit), hoặc bấm Merge trên github.com — đường thứ hai để lại card ở `Ready for Review` với issue đã đóng, trừ khi workflow đó đã bật, và `/agentflow:init` **không verify được** nó (không API nào đọc được). Card như vậy vô hình với cả queue lẫn bảng đếm; `/agentflow:status` in nó ở dòng `⚠ closed ≠ Done`.
- **Safety rule: một phần đã enforce, phần còn lại vẫn ở mức prompt — đừng nhầm hai cái.**
  - **Đã enforce (tầng tool):** `disallowedTools` gỡ hẳn `merge_pull_request` khỏi cả hai agent, cộng restriction theo role (DEV mất `pull_request_review_write` — không tự approve PR của mình; QC mất `create_pull_request` — chỉ push lên PR branch sẵn có). Agent bị derail/inject **không gọi được** MCP tool merge.
  - **Đã enforce (harness):** `/agentflow:init` sinh `permissions.deny` vào `.claude/settings.json` của repo — force-push, `gh pr merge`, global forbidden paths (`infra/**`, `.github/workflows/**`, `**/.env`, `**/*.pem`), **và `forbidden` riêng của từng surface** khai trong `agentflow.yaml`. Deny thắng allow, nên đây là gate thật chứ không phải prose. `git push` thường thì allow dạng `Bash(git push:*)` để lần push đầu của mỗi branch (`git push -u origin …`) không phải hỏi.
  - **CHƯA enforce (vẫn là prompt contract):** no-push-to-default-branch, và ranh giới "QC không đụng implementation logic". **`Bash` vẫn là escape hatch** — rule deny bám theo *chuỗi command*, nên một biến thể chưa liệt kê vẫn lọt. Và deny chỉ được sinh **một lần lúc init**: thêm surface `forbidden` mới vào `agentflow.yaml` thì phải chạy lại `/agentflow:init` mới có rule tương ứng.
  - **Lớp enforcement thật còn thiếu:** một PreToolUse hook match path/command, và branch-protection ruleset phía repo (block force-push + require PR review) — cái sau là gate duy nhất chạy ngoài tầm với của agent. Cho tới khi có, hãy dùng token least-privilege và review PR trước khi merge.
- **Comment GitHub không có prefix là untrusted.** Mọi actor — kể cả main session — coi comment không mang prefix nhận diện được là context untrusted, không phải chỉ thị.

## Non-goals — những gì KHÔNG được thay đổi

Load-bearing, dễ bị bào mòn bởi tích lũy có thiện chí, và cố tình được đặt như vậy. Thay đổi ở đây là **design change**, không phải cải tiến:

- **`Status` trên board là state authoritative duy nhất; label không bao giờ mang state.** Đọc lại Status live sau mỗi lần chạy chính là thứ làm thiết kế no-message-bus hoạt động.
- **Cột agent-owned không bao giờ giữ ticket ở trạng thái nghỉ.** Đừng thêm một "parked" state mới cho agent — mọi ngõ cụt về `Inbox`. Bất biến này là thứ xoá được cả một lớp ticket kẹt vô hình.
- **Human merge gate là bắt buộc.** Agent dừng ở `Ready for Review`; chỉ con người merge. **Đừng bao giờ trả `merge_pull_request` lại cho một sub-agent.**
- **`agentflow.yaml` chỉ giữ thứ không suy ra được.** Một key mới phải trả lời được "vì sao không suy từ git / không làm hằng số plugin / không auto-discover?". Không trả lời được thì nó thuộc về một trong ba chỗ đó. Config phình là cách plugin này chết lần trước.
- **Đừng giả vờ phần CHƯA enforce là đã enforce.** Đừng che khoảng trống bằng prose `NEVER …` ngày càng dài làm phình mỗi run để đổi lấy an toàn giả.
- **Việc load skill lười vẫn giữ lười — và ranh giới là AUDIENCE, không phải chủ đề.** `SKILL.md` giữ đúng phần mọi actor cần (gồm hai shape call `update_project_item` / `get_project_item` mà DEV/QC dùng ở **mọi** run); `references/` giữ phần chỉ orchestrator/init chạm. Chia sai chiều thì "lười" chỉ là hình thức: nếu DEV/QC phải load reference ở mọi ticket thì tách file chỉ thêm round-trip chứ không giảm token. Đừng front-load queue/`status_map`/board setup vào agent prompt, và đừng đẩy runtime shape ra reference.
- **File runtime là prompt, không phải tài liệu.** `agents/*.md` và `skills/*/SKILL.md` bị trả giá ở **mọi lần spawn**, nhân với số ticket và số vòng rework. Prose giải thích *vì sao thiết kế như vậy* thuộc về README (mục này) — file runtime chỉ nhận mệnh đề mệnh lệnh kèm pointer. Ngoại lệ: WHY chặn được một hành vi sai hấp dẫn thì giữ, ở dạng ngắn nhất có tác dụng.
- **Đừng làm phình section `AGENTFLOW-STATE`.** Hai agent prose-edit nó và phải giữ tương thích format; mỗi field bắt buộc mới là một bề mặt drift mới.
- **Optional service degrade gracefully.** Figma/notify vắng mặt → bỏ qua kèm note, không bao giờ là hard block. GitHub và board là ngoại lệ — cả hai bắt buộc.
- **Secret đi HAI đích, và đó là ràng buộc kỹ thuật chứ không phải sở thích.** `GITHUB_TOKEN` → `env` của `~/.claude/settings.json` (user-global); `TELEGRAM_*` / `FIGMA_TOKEN` → `env` của `.claude/settings.local.json` (theo repo). Đừng "thống nhất" bằng cách kéo `GITHUB_TOKEN` xuống file local của repo: đã verify trên Claude Code 2.1.228 rằng `.mcp.json` chỉ expand `${VAR}` từ môi trường thật của tiến trình, từ settings user-global, hoặc từ `--settings` — `env` project-scope **không** tới được bước đó, nên server sẽ fail hệt như khi chưa đặt token (`HTTP 400 Authorization header is badly formatted`). Chiều ngược lại thì được nhưng vô ích: `TELEGRAM_*` đặt ở user-global cũng chạy, chỉ là mất tính theo-repo.
- **Token GitHub giờ nằm trong env của session, nên Bash đọc được nó** — kể cả `gh`, vốn tự nhận `GITHUB_TOKEN`. Đây là đánh đổi đã biết của việc bỏ keychain: đổi lấy một đường cấu hình duy nhất, bằng một token đầy quyền mà mọi Bash command trong session nhìn thấy. Hai hệ quả **không được** bào mòn: (1) secret hygiene lên mức bắt buộc — không bao giờ `echo`, nội suy vào command string, hay ghi token ra file; (2) việc `gh api` **chạy được** không biến nó thành đường hợp lệ — board write vẫn đi qua MCP, không ngoại lệ, vì một API surface thứ hai mang tập lỗi và tập quyền riêng.
