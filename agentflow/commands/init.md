---
description: Bootstrap AgentFlow trong repo hiện tại — verify GitHub auth (token đọc từ env GITHUB_TOKEN của settings user-global, không phải file trong repo), phát hiện surfaces, tạo label classification, tạo/link một Projects v2 board với Status field 6 option, rồi ghi agentflow.yaml ở root + .claude/settings.json và chạy board-write smoke test.
argument-hint: (không có args — chạy một setup wizard tương tác)
---

Bạn đang bootstrap **AgentFlow** trong repository HIỆN TẠI. Đây là setup một lần nhưng **idempotent và chạy lại được** — user chạy lại để re-detect surface, đổi toggle, hay refresh config. Không bao giờ ghi đè một `agentflow.yaml` đã sửa tay mà không cảnh báo: đã có thì đọc nó, coi value của nó là default cho mỗi bước, và xác nhận trước khi ghi.

**Config viết theo protocol khác `1.0`** → **không migrate tự động**. Nói cho user biết file sẽ được thay; đọc value cũ làm default ở đâu suy được (board number, surface path, figma/notify on-off) rồi ghi lại theo format `1.0`.

Thực hiện các bước **theo thứ tự**. Precondition fail → nói chính xác cần fix gì rồi **stop**; đừng cố tiếp tục với một repo cấu hình dở dang. **Không bao giờ echo giá trị secret.**

---

## 1. Preconditions

```bash
git rev-parse --is-inside-work-tree    # phải là git repo
git remote get-url origin              # phải resolve ra một GitHub remote
git rev-parse --show-toplevel          # REPO ROOT — mọi path bên dưới relative tới đây
```

- Không phải git repo → "Chạy `git init` và thêm một GitHub `origin` remote trước." **Stop.**
- Không có `origin` → "Thêm remote: `git remote add origin git@github.com:OWNER/REPO.git`." **Stop.**

Init có thể được gọi từ subdirectory. Mọi path (`agentflow.yaml`, `.claude/…`, `.gitignore`) là **relative tới repo root** — resolve một lần rồi dùng xuyên suốt.

### 1a. Auth check

`.mcp.json` của plugin đọc token qua `${GITHUB_TOKEN}`, và giá trị đó đến từ block `env` của
**`~/.claude/settings.json`** (settings user-global) — không phải file nào trong repo. Chỉ **probe MCP**:

```
get_me      → trả về `login`
```

- **Trả về `login`** → authenticated. Cache `login`, sang Step 2.
- **Call fail** → token chưa đặt, sai, hết hạn, hoặc thiếu scope. `claude mcp list` phân biệt nhanh
  hai ca (server **luôn tồn tại**, kể cả khi biến trống — nó chỉ fail lúc connect):

  | Dòng `plugin:agentflow:github` báo | Nghĩa là |
  |---|---|
  | `HTTP 400 … Authorization header is badly formatted` | `GITHUB_TOKEN` **chưa đặt** — header gửi đi nguyên văn `Bearer ${GITHUB_TOKEN}` |
  | `HTTP 401` / `unauthorized` | Biến có giá trị nhưng token sai, hết hạn, hoặc thiếu scope |

Fail → **STOP**. Đây là **thông điệp canonical**; `/agentflow:start` và `/agentflow:task` in bản rút gọn của chính nó, đừng ai soạn lại bản khác:

```
GitHub MCP chưa authenticate được.

Token của AgentFlow đọc từ biến môi trường GITHUB_TOKEN. Đặt nó trong block `env` của
settings USER-GLOBAL — ~/.claude/settings.json:

    {
      "env": { "GITHUB_TOKEN": "ghp_…" }
    }

Cần CLASSIC PAT — https://github.com/settings/tokens/new
    scopes: repo + project   (+ read:org nếu board thuộc org)

Dùng CLASSIC PAT, không phải fine-grained: fine-grained PAT chưa được verify cho Projects v2
user-owned board. Board-write smoke test ở Step 10 là nơi phát hiện token sai loại.

Đặt xong → THOÁT Claude Code và mở lại (MCP server connect lúc boot) → chạy lại /agentflow:init.
```

> **Phải là settings user-global, KHÔNG phải `.claude/settings.local.json` của repo.** Đã verify trên
> Claude Code 2.1.228: `.mcp.json` chỉ expand `${VAR}` từ **môi trường thật của tiến trình**, từ
> `~/.claude/settings.json`, hoặc từ `--settings` — block `env` của `.claude/settings.json` và
> `.claude/settings.local.json` (cả hai đều project-scope) **không** tới được bước expand đó. Đặt
> `GITHUB_TOKEN` vào file local của repo thì server vẫn fail y như chưa đặt. (Ngược lại, `TELEGRAM_*`
> ở Step 3 **hoạt động** từ file local, vì `curl` đọc chúng như một subprocess — xem `agentflow-protocol` §1.)

Sau khi STOP thì **không chạy tiếp bước nào**. `export GITHUB_TOKEN=…` trong shell trước khi mở
Claude Code cũng có tác dụng, nhưng đừng khuyến nghị nó làm đường chính: nó mất khi đổi terminal.

## 2. Xác định project

Suy từ **local git** (MCP không biết checkout hiện tại thuộc repo GitHub nào) — **không** ghi những giá trị này vào config, chúng được suy lại mỗi run:

```bash
git remote get-url origin               # parse OWNER/REPO (SSH git@github.com:O/R.git hoặc HTTPS)
git rev-parse --abbrev-ref origin/HEAD  # default branch (origin/main → main)
```

Không resolve được default branch (chưa có `origin/HEAD`) → hỏi user; đó là vấn đề của repo, không phải của config.

Thứ **duy nhất** cần chốt ở đây và ghi vào config: **`board.owner_type`** (`org` | `user`). Lấy own login qua `get_me`; `OWNER == login` → `user`, ngược lại **hỏi user xác nhận** (MCP không có tool suy trực tiếp owner_type).

## 3. Optional secrets (chỉ có/không — KHÔNG BAO GIỜ giá trị)

GitHub auth đã xong ở Step 1 và **không** đụng tới file nào của repo. Ở đây chỉ còn optional — chúng sống trong block `env` của `.claude/settings.local.json` (gitignored), và **không cái nào được phép stop init**:

```bash
[ -n "${TELEGRAM_BOT_TOKEN:-}" ] && echo "TELEGRAM_BOT_TOKEN: set" || echo "TELEGRAM_BOT_TOKEN: absent"
[ -n "${TELEGRAM_CHAT_ID:-}" ]   && echo "TELEGRAM_CHAT_ID: set"   || echo "TELEGRAM_CHAT_ID: absent"
```

> **Vì sao TELEGRAM_\* nằm ở file local của REPO còn `GITHUB_TOKEN` thì không:** `curl` chạy như một **subprocess** của session, và block `env` của `.claude/settings.local.json` **có** tới được subprocess. Còn header của MCP server thì được expand ở một bước sớm hơn, chỉ đọc môi trường thật / settings user-global (Step 1a). Hai đích khác nhau vì hai cơ chế khác nhau, không phải vì sở thích.

Thiếu → `notify` tự tắt lúc runtime, pipeline chạy bình thường. User muốn điền ngay:

1. **Gitignore guard trước** (chạy trước mọi lần Write vào `.claude/settings.local.json`):

   ```bash
   if ! git check-ignore -q .claude/settings.local.json; then
     [ -s .gitignore ] && [ -n "$(tail -c1 .gitignore)" ] && printf '\n' >> .gitignore   # .gitignore thiếu newline cuối → đừng nối vào dòng cuối
     printf '%s\n' '.claude/settings.local.json' >> .gitignore
   fi
   git check-ignore -q .claude/settings.local.json && echo "gitignored ✓" || echo "WARNING: VẪN không được ignore"
   git ls-files --error-unmatch .claude/settings.local.json >/dev/null 2>&1 \
     && echo "WARNING: file đang được git TRACK — chạy: git rm --cached .claude/settings.local.json" \
     || echo "not tracked ✓"
   ```

   Gate bằng `git check-ignore` chứ không `grep`, để repo đã ignore qua pattern rộng hơn (vd `.claude/`) không bị thêm dòng thừa. Cả hai WARNING cùng lúc = file đang được track (git không ignore file đã track) → `git rm --cached …` rồi chạy lại. Chỉ WARNING đầu = một rule negation (`!.claude/…`) cuối `.gitignore` đang ghi đè → in `tail -5 .gitignore`, sửa, chạy lại.

2. Chưa xanh thì **chưa được Write**. Xanh rồi: thêm key vào `env` của `.claude/settings.local.json` bằng **Read + Write** (không Bash — tránh ghi secret vào shell history), giữ nguyên mọi key sẵn có.

3. Nói rõ nó **chỉ có hiệu lực sau khi restart**; init cứ chạy tiếp lượt này với `notify` bật trong config nhưng tắt lúc runtime.

> **`.claude/settings.json` KHÔNG được ignore** — nó là file team-shared, có commit (Step 8). Chỉ `.claude/settings.local.json` bị ignore.

Figma official MCP server dùng **OAuth**, không có token nào để kiểm ở đây.

## 4. Toggle

Chỉ hai câu hỏi (không có "connections wizard" — GitHub và board là bắt buộc, wiring của chúng là hằng số plugin):

- **figma** — *bật design source cho DEV?* Bật → `figma.enabled: true`, seed `figma.files` bằng các file key đã biết (`[{ name, key }]`), và bảo user authenticate một lần: `claude mcp add --transport http figma https://mcp.figma.com/mcp` rồi `/mcp → figma → Authenticate`. Từ chối → `enabled: false`.
- **notify** — *ping Telegram khi pipeline dừng chờ bạn?* Giải thích ngắn giá trị: cần cho việc chạy `/agentflow:start` unattended qua `/loop` — không có nó, ticket park ở `Inbox +blocked` / `Ready for Review` mà không ai biết. Nói rõ đây là ping **một chiều cho người**, không phải kênh giữa các agent. Bật → `notify.enabled: true`, `events: ["blocked", "ready_for_review"]`. Cả hai key đã có giá trị → chạy **smoke test** (fail thì **cảnh báo rồi tiếp tục**, không bao giờ stop init):

  ```bash
  curl -sS --max-time 10 -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
    --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" \
    --data-urlencode "text=AgentFlow: notify wired ✅ (setup check)" \
    -o /dev/null -w '%{http_code}\n' \
    || echo "notify smoke test FAILED — kiểm tra TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID"
  ```

  `200` = ok · `401` = bot token sai · `400 chat not found` = chat id sai, hoặc bạn chưa nhắn `/start` cho bot một lần (Telegram chặn bot nhắn trước tới user chưa từng chat).

## 5. Phát hiện surface

Surfaces là **tùy chọn**. Scan marker, rồi **ĐỀ XUẤT** — user xác nhận, chỉnh, hoặc đổi tên:

```bash
ls package.json go.mod pom.xml build.gradle build.gradle.kts requirements.txt \
   pyproject.toml Gemfile Cargo.toml pubspec.yaml composer.json 2>/dev/null
ls -d android ios web frontend backend server api admin mobile app 2>/dev/null
```

- **Repo single-app** (một stack, một root) → **BỎ HẲN block `surfaces`** khỏi yaml. Đây là mặc định tốt: DEV/QC gate toàn repo, issue không cần label `component/*`, và không có block config nào để trôi. **Đừng** viết `.: { path: "." }` cho có.
- **Nhiều phần build được riêng** → một block mỗi phần, key do user chọn (`api`, `web`, `mobile`, `admin`…), `path` là glob root, `forbidden` là các glob không ai được động (vd `["android/key.properties", "ios/Runner/GoogleService-Info.plist"]`).
- Surface **không** khai báo build/lint/test command hay coverage — marker ở trên chỉ để chốt key + path; DEV/QC tự khám phá theo convention của repo.

## 6. Board (bắt buộc)

Chi tiết cơ chế: skill **`agentflow-protocol`** → `references/projects-v2-board.md`.

- Hỏi: **tạo board mới** hay **link board có sẵn theo number** (không được skip).
  - *create*: `projects_write` method=`create_project` (owner, owner_type, title) → board **rỗng**. Lưu **number**.
  - *link*: resolve theo number qua `projects_get` method=`get_project`.
- **Status field 6 option — bước UI thủ công một lần** (`projects_write` không có method tạo/sửa field; xem reference §"Tạo board" cho lý do đầy đủ). Đây là **bước dễ sai nhất của cả init** — tên option là wire value resolve by-name, sai một ký tự là hard-error ở ticket thật đầu tiên. Nên **đừng chỉ liệt kê tên**: in nguyên bảng dưới cho user dán vào GitHub UI (Board → `⋯` → Settings → field `Status`), đúng thứ tự, mỗi option kèm **Description** — nó là chỗ duy nhất semantics của cột hiện ra cho người đang đứng trước board:

  | # | Option name (chính xác) | Color | Description (dán vào ô Description của option) |
  |---|---|---|---|
  | 1 | `Inbox` | Gray | Chờ người: chốt AC, hoặc gỡ ticket mang label `blocked`. Kéo card về đây để yêu cầu sửa một PR. |
  | 2 | `Ready for Dev` | Blue | Đã đạt Definition of Ready — DEV tự nhặt. Đừng kéo tay vào đây. |
  | 3 | `In Progress` | Yellow | DEV đang code. Không kéo card khi ticket ở cột này. |
  | 4 | `In QC` | Orange | QC đang review + author test trên PR branch. Không kéo card khi ticket ở cột này. |
  | 5 | `Ready for Review` | Purple | **Việc của bạn**: review + merge PR. Muốn sửa → comment inline trên PR rồi kéo card về Inbox. |
  | 6 | `Done` | Green | Terminal. |

  Rồi **validate** qua `projects_list` method=`list_project_fields`: assert đủ 6 option đúng tên. Thiếu → liệt kê tên còn thiếu, yêu cầu thêm, validate lại. **Thừa option** (vd `Todo` mặc định của board mới) → bảo user **kéo hết card ra khỏi option đó trước** rồi xoá nó; card nằm ở một option ngoài 6 tên trên là card ngoài state machine.

  Description **không** load-bearing với agent (agent resolve by-name, không đọc description) — thiếu nó không fail validate. Nhưng đừng bỏ qua: nó là thứ giữ cho người thứ hai trong team không kéo card vào cột agent đang giữ.
- **Board description — đặt luôn ở cùng lượt UI này.** Board là nơi người PO nhìn hằng ngày, nên đây là entry point đúng cho người mới vào repo (Step 8 giải thích vì sao **không** nhét nội dung này vào `agentflow.yaml`). Board → `⋯` → Settings → *Short description*:

  ```
  AgentFlow · <OWNER/REPO> — bạn là Product Owner. Việc mới: /agentflow:task <mô tả> · chạy pipeline: /agentflow:start · xem trạng thái: /agentflow:status. Bạn làm tay đúng 2 việc: chốt AC ở Inbox, và review/merge PR ở Ready for Review.
  ```
- **Built-in workflows — thủ công-UI** (không API nào config được). Project settings → Workflows:
  - **Item added to project** → Status: `Inbox`
  - **Item reopened** → Status: `Inbox`
  - **Item closed** → Status: `Done`

  Đây là automation miễn phí phủ các cạnh agent không chứng kiến. Không verify được nó đã bật hay chưa, nên `/agentflow:task` vẫn ghi Status explicit — không bao giờ dựa vào workflow.

  **Nhấn mạnh với user rằng `Item closed → Done` là cái quan trọng nhất trong ba cái**: nó là lane thoát cho việc merge PR trên github.com (đường merge tự nhiên nhất — không ai gõ `merge #<n>` mọi lần). Chưa bật ⇒ card kẹt ở `Ready for Review` với issue đã đóng, vô hình với cả queue lẫn bảng đếm; `/agentflow:status` bắt triệu chứng ở dòng `closed ≠ Done` nhưng đó là chữa, không phải phòng.

Board op fail vì permission → bảo user thêm scope `project` vào classic PAT (thêm scope vào token có sẵn **không** đổi value, nên không phải sửa settings và không phải restart) rồi **stop**.

## 7. Labels

Idempotent. **Label không mang state** — chỉ classification + hai aux signal. Với mỗi label gọi `label_write` method=`create`; lần chạy lại dùng method=`update` để re-apply color/description thay vì báo lỗi:

```
# type/* — green
label_write name="type/feature"     color=0E8A16  description="AgentFlow: new capability"
label_write name="type/improvement" color=0E8A16  description="AgentFlow: enhancement"
label_write name="type/bug"         color=0E8A16  description="AgentFlow: defect"

# component/<surface> — MỘT cái cho mỗi surface khai báo ở Step 5 (bỏ qua nếu single-surface) — purple
for s in <surface keys>: label_write name="component/$s" color=5319E7 description="AgentFlow: $s surface"

# aux signals — amber
label_write name="rework"  color=FBCA04  description="AgentFlow: QC reject — DEV đọc QC rejection mới nhất trước"
label_write name="blocked" color=D93F0B  description="AgentFlow: ticket ở Inbox đang chờ quyết định của con người — /agentflow:start bỏ qua, gỡ bằng /agentflow:task #<n>"
```

## 8. Ghi file

Hai file, hai mối quan tâm (skill `agentflow-protocol` §1):

1. **`agentflow.yaml` ở REPO ROOT** — copy `${CLAUDE_PLUGIN_ROOT}/agentflow.yaml` rồi điền value. Template là một file YAML **hợp lệ** với default tối thiểu; bạn chỉ sửa value, không dựng cấu trúc mới. Đọc template để xác nhận đủ bộ; **không đọc được template → STOP**, đừng dựng yaml từ trí nhớ.

   | Key | Giá trị |
   |---|---|
   | `agentflow: "1.0"` | copy nguyên văn — đây là **protocol version**, KHÔNG substitute từ `plugin.json` |
   | `board.number` | project number từ Step 6 — integer thật. Template để `null`; ghi xong **assert nó là integer > 0**, vì một init crash giữa chừng để lại `null` là fail sớm và đọc được, còn `0` thì trông như đã điền |
   | `board.owner_type` | `org` \| `user` từ Step 2 |
   | `surfaces` | Step 5 phát hiện **nhiều** surface → bỏ comment block ví dụ và khai báo từng cái (`path` + `forbidden`). **Single-surface → để nguyên dạng comment**: key `surfaces` vắng mặt chính là mặc định đúng |
   | `figma.enabled` / `figma.files` | Step 4 |
   | `notify.enabled` | Step 4 |

   Giữ nguyên các comment đã curate. **Đừng bịa key template không có** — đặc biệt không thêm `project:`, `connections:`, `labels:`, hay `board.columns`: repo/owner/default-branch suy từ git, còn label và 6 tên column là hằng số plugin. Khai chúng trong yaml là tạo một bản sao sẽ stale.

2. **`.claude/settings.json`** — **sinh ra, không copy.** Nội dung là hằng số cộng với ba thứ phải suy lúc chạy, nên không có file template nào nói đúng được cho mọi repo.

   **2a. Hằng số — copy VERBATIM khối dưới đây**, đừng viết lại từ trí nhớ, đừng thêm bớt rule:

   ```json
   {
     "permissions": {
       "allow": [
         "Bash(git status:*)",
         "Bash(git diff:*)",
         "Bash(git log:*)",
         "Bash(git show:*)",
         "Bash(git branch:*)",
         "Bash(git remote get-url:*)",
         "Bash(git rev-parse:*)",
         "Bash(git fetch:*)",
         "Bash(git switch:*)",
         "Bash(git checkout:*)",
         "Bash(git rebase:*)",
         "Bash(git add:*)",
         "Bash(git commit:*)",
         "Bash(git push:*)"
       ],
       "deny": [
         "Bash(git push --force:*)",
         "Bash(git push -f:*)",
         "Bash(gh pr merge:*)",
         "Read(./**/.env)",
         "Read(./**/*.pem)",
         "Edit(./infra/**)",
         "Edit(./.github/workflows/**)",
         "Edit(./**/.env)",
         "Edit(./**/*.pem)",
         "Write(./infra/**)",
         "Write(./.github/workflows/**)"
       ]
     }
   }
   ```

   `allow` dùng `Bash(git push:*)` chứ **không** phải dạng bare `Bash(git push)` — lần push đầu của mỗi branch là `git push -u origin <branch>`, dạng bare không match và DEV sẽ dính prompt ở mọi ticket. Force-push bị chặn bằng `deny` (deny thắng allow), không phải bằng cách thu hẹp `allow`.

   **2b. `enabledPlugins` — suy ra plugin id thật, đừng hardcode.** Fork hoặc marketplace đổi tên là id đổi theo:

   ```bash
   jq -r '.plugins | keys[] | select(startswith("agentflow@"))' ~/.claude/plugins/installed_plugins.json
   ```

   → `{ "enabledPlugins": { "<id vừa đọc>": true } }`. Không đọc được (plugin chạy từ `--agents` dir, file vắng) → dùng `agentflow@agent-flow-plugins` và nói rõ là đang đoán.

   **2c. `extraKnownMarketplaces` — suy từ marketplace ĐANG đăng ký.** Đây là thứ làm teammate clone repo về là có sẵn nguồn plugin; thiếu nó thì `enabledPlugins` trỏ vào một marketplace máy họ chưa có và Claude Code bỏ qua entry đó (log `Skipping orphaned enabledPlugins entry`).

   ```bash
   MKT="${ID#*@}"   # phần sau @ của plugin id ở 2b
   jq --arg m "$MKT" '.[$m].source' ~/.claude/plugins/known_marketplaces.json
   ```

   - `source == "github"` → ghi nguyên vào `extraKnownMarketplaces.<MKT>.source`. Đây là ca đúng.
   - `source == "directory"` (marketplace là thư mục local trên máy bạn) → **đường dẫn đó không tồn tại trên máy teammate.** Hỏi user repo GitHub của marketplace; có thì ghi dạng `{"source":"github","repo":"<owner>/<repo>"}`, không thì **bỏ hẳn key** và note ở Step 11 rằng repo này chưa share được cho người khác.
   - Không đọc được → bỏ key, note ở Step 11. **Đừng bịa một `repo`.**

   **2d. Forbidden paths của từng surface → deny rule.** Với mỗi glob trong `surfaces.<key>.forbidden` (Step 5), thêm `"Edit(./<glob>)"` và `"Write(./<glob>)"` vào `deny`. Global forbidden paths đã nằm trong khối 2a rồi — đừng lặp lại. Không có surface nào khai `forbidden` → không thêm gì.

   **2e. Merge, không ghi đè.** File đã tồn tại → đọc nó, **giữ nguyên mọi key và mọi entry sẵn có**, chỉ **thêm** entry còn thiếu vào `permissions.allow` / `permissions.deny` (so sánh theo chuỗi chính xác, không dedupe mờ), và thêm `enabledPlugins` / `extraKnownMarketplaces` nếu chưa có. **Không bao giờ xoá** một rule user tự thêm, kể cả khi nó mâu thuẫn với rule của AgentFlow — nêu mâu thuẫn ở Step 11 để user tự quyết.

   File này **được commit** — không bao giờ đặt secret vào đây.

**Không sinh file doc thứ ba, và không nhét doc vào `agentflow.yaml`.** Mọi bản sao của phần "dùng như thế nào" nằm trong repo user đều là **bản đóng băng**: plugin bump version thì nó stale, và không ai sửa nó. Entry point cho người mới clone repo là (1) README của plugin — update theo version, và (2) **description của chính board** (Step 6), nơi người PO thật sự nhìn hằng ngày. `agentflow.yaml` giữ đúng vai trò config: value + comment giải thích *từng key*, không hướng dẫn sử dụng.

## 9. Scaffold project skill (opt-in)

Đề nghị tạo skill stub role-prefix dưới `.claude/skills/`: `dev-*` → DEV, `qc-*` → QC. Agent **auto-discover** chúng — không có registry nào phải đăng ký.

**Luôn đề xuất `qc-automation-test`** (QC load nó để thêm test ID và author test flow trên PR branch). Đề xuất phần còn lại khớp surface đã detect, vd `dev-<surface>-development`. **Hỏi trước khi tạo.** Mỗi stub được chấp nhận: ghi một `SKILL.md` với YAML frontmatter (`name` = tên directory, `description` một dòng) + body TODO. Liệt kê chính xác cái gì đã tạo.

## 10. Verify (BẮT BUỘC — đây là nơi bắt payload lỗi)

```bash
python3 -c "import yaml; yaml.safe_load(open('agentflow.yaml'))" && echo "yaml: ok"
python3 -c "import json; json.load(open('.claude/settings.json'))" && echo "settings.json: ok"
```

- **Labels:** `list_label` → đủ 3 `type/*`, một `component/*` cho mỗi surface (nếu có), `rework`, `blocked`.
- **Board:** `projects_get` method=`get_project` + `projects_list` method=`list_project_fields` (đủ 6 option Status).

### Board write smoke test — bắt buộc, KHÔNG hỏi consent

Board resolve được **không** chứng minh AgentFlow ghi được vào nó. Read-only check bỏ sót cả một class lỗi payload — và Status write là **authoritative path, mandatory-success**: một `updated_field` sai shape sẽ dừng pipeline ngay ở ticket thật đầu tiên. Đây là lần duy nhất trong đời một repo mà authoritative write path được kiểm chứng end-to-end trước khi có ticket thật phụ thuộc vào nó.

```
# 1. issue tạm
issue_write method=create title="AgentFlow setup check" body="temporary — safe to close"   → #<n>

# 2. add lên board → item_id
projects_write method=add_project_item
  owner=<owner> owner_type=<org|user> project_number=<board.number>
  item_type=issue item_owner=<owner> item_repo=<repo> issue_number=<n>

# 3. set Status=Inbox — BY-NAME shape
projects_write method=update_project_item
  owner=<owner> owner_type=<org|user> project_number=<board.number>
  item_owner=<owner> item_repo=<repo> issue_number=<n>
  updated_field={ name: "Status", value: "Inbox" }

# 4. READ-BACK — thiếu bước này thì bước 3 không chứng minh được gì
projects_get method=get_project_item item_id=<item_id> field_names=["Status"]   → assert "Inbox"

# 5. transition Inbox → Ready for Dev, read-back lần nữa
projects_write method=update_project_item ... updated_field={ name: "Status", value: "Ready for Dev" }
projects_get   method=get_project_item item_id=<item_id> field_names=["Status"] → assert "Ready for Dev"

# 6. dọn dẹp (chạy KỂ CẢ khi 4/5 fail — dọn trước, báo lỗi sau)
projects_write method=delete_project_item owner=<owner> project_number=<board.number> item_id=<item_id>
issue_write    method=update state=closed
```

**Bước 4/5 fail → STOP** và báo đúng nguyên nhân:

| Triệu chứng | Nguyên nhân | Fix |
|---|---|---|
| `option_not_found` (kèm candidates) | Tên option Status không khớp 6 hằng số | Sửa trong GitHub UI cho khớp một-đối-một, chạy lại `/agentflow:init` |
| Lỗi khác về `updated_field` | Sai shape — by-id không resolve option theo tên | Dùng **by-name** shape (reference `projects-v2-board.md`). Không tự chế shape khác |
| Status read-back rỗng/vắng | Thiếu `field_names:["Status"]` ở call read | Luôn truyền `field_names` |

## 11. Tóm tắt

```
AgentFlow initialized on <OWNER/REPO> (protocol v1.0)

Board       : #<N> (<org|user>) — Status field 6 option, built-in workflows đã hướng dẫn bật
Surfaces    : <key>=<path>, …   |   single-surface (không khai báo — gate toàn repo)
Labels      : <5 + N> created/updated (type/* ·3, component/* ·N, rework, blocked)
Toggles     : figma <on (OAuth) | off>   notify <on (smoke ✓) | on (chưa có secret — tự tắt) | off>
Auth        : GITHUB_TOKEN (env, ~/.claude/settings.json) ✓ — login <login>
              TELEGRAM_* trong .claude/settings.local.json: <có | không>
              <chỉ khi guard ở Step 3 còn WARNING: ⚠ .claude/settings.local.json chưa được gitignore / đang bị track>
Skills      : <stub đã scaffold, hoặc none>
Files       : agentflow.yaml, .claude/settings.json, [.claude/skills/<role>-* …]

Next: /agentflow:task <mô tả> để tạo việc đầu tiên, rồi /agentflow:start để vào team mode.
```
