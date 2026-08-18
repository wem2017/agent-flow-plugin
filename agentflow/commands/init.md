---
description: Bootstrap AgentFlow trong repo hiện tại — verify GitHub auth (token đọc từ env GITHUB_TOKEN trong .claude/settings.local.json của repo, gitignored), phát hiện surfaces, tạo label classification, tạo/link một Projects v2 board với Status field 6 option, rồi ghi agentflow.yaml ở root + .claude/settings.local.json và chạy board-write smoke test.
argument-hint: (không có args — chạy một setup wizard tương tác)
---

Bootstrap **AgentFlow** trong repository HIỆN TẠI. Setup một lần nhưng **idempotent và chạy lại được**. Không bao giờ ghi đè một `agentflow.yaml` đã sửa tay mà không cảnh báo: đã có thì đọc nó, coi value của nó là default cho mỗi bước, và xác nhận trước khi ghi.

**Config viết theo `schema` khác `2`** → **không migrate tự động**. Nói cho user biết file sẽ được thay, hỏi lại từng giá trị như một lần init mới, rồi ghi lại theo schema `2`.

Thực hiện các bước **theo thứ tự**. Precondition fail → nói chính xác cần fix gì rồi **stop**. **Không bao giờ echo giá trị secret.**

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

### 1a. Secret file guard — CHẠY TRƯỚC KHI NÓI TỚI TOKEN

Mọi secret của AgentFlow (`GITHUB_TOKEN` bắt buộc, `TELEGRAM_*` / `FIGMA_TOKEN` tùy chọn) sống trong block `env` của **`.claude/settings.local.json` của repo này**. File đó nằm trong working tree, nên **chưa chứng minh được nó bị git bỏ qua thì tuyệt đối chưa được hướng dẫn user ghi token vào**. Guard chạy **trước** auth check:

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

Gate bằng `git check-ignore` chứ không `grep` (repo ignore qua pattern rộng hơn như `.claude/` thì không bị thêm dòng thừa). Cả hai WARNING = file đang được track → `git rm --cached …` rồi chạy lại. Chỉ WARNING đầu = một rule negation (`!.claude/…`) cuối `.gitignore` đang ghi đè → in `tail -5 .gitignore`, sửa, chạy lại.

**Chưa xanh cả hai dòng → STOP.** Không probe auth, không in hướng dẫn đặt token.

### 1b. Auth check

`.mcp.json` đọc token qua `${GITHUB_TOKEN}`, giá trị đến từ block `env` của `.claude/settings.local.json`. Chỉ **probe MCP** — đừng test biến, biến có giá trị vẫn có thể sai scope:

```
get_me      → trả về `login`
```

- **Trả về `login`** → authenticated. Cache `login`, sang Step 2.
- **Call fail** → phân biệt bằng **mã lỗi của chính call vừa fail** (server **luôn tồn tại**, kể cả khi biến trống — nó chỉ fail lúc connect):

  | Lỗi | Nghĩa là |
  |---|---|
  | `HTTP 400 … Authorization header is badly formatted` | `GITHUB_TOKEN` **chưa đặt** — header gửi đi nguyên văn `Bearer ${GITHUB_TOKEN}` |
  | `HTTP 401` / `unauthorized` | Biến có giá trị nhưng token sai, hết hạn, hoặc thiếu scope |

> **ĐỪNG chẩn đoán bằng `claude mcp list`** — nó không nạp project settings nên báo `Missing environment variables: GITHUB_TOKEN` kể cả khi token đã đặt đúng.

Fail → **STOP** với **thông điệp canonical** này (`/agentflow:start` và `/agentflow:task` in bản rút gọn của chính nó — đừng soạn bản khác):

```
GitHub MCP chưa authenticate được.

Token của AgentFlow đọc từ biến môi trường GITHUB_TOKEN, lấy từ block `env` của
.claude/settings.local.json TRONG REPO NÀY (file đã được gitignore):

    {
      "env": { "GITHUB_TOKEN": "ghp_…" }
    }

Đặt xong → THOÁT Claude Code và mở lại (MCP server connect lúc boot) → chạy lại /agentflow:init.
```

User muốn đưa giá trị ngay trong session này → ghi bằng **Read + Write**, không Bash (tránh secret vào shell history), giữ nguyên mọi key sẵn có. Rồi vẫn STOP: giá trị mới **không** có hiệu lực với session đang chạy. Sau STOP thì **không chạy tiếp bước nào**.

> Một `export GITHUB_TOKEN=…` trong shell **đè** giá trị của file. Probe fail mà file trông đúng → nghi biến shell trước.

## 2. Xác định repo

Suy từ **local git** — **không** ghi những giá trị này vào config, chúng được suy lại mỗi run:

```bash
git remote get-url origin               # parse OWNER/REPO (SSH git@github.com:O/R.git hoặc HTTPS)
git rev-parse --abbrev-ref origin/HEAD  # default branch (origin/main → main)
```

Không resolve được default branch (chưa có `origin/HEAD`) → hỏi user; đó là vấn đề của repo, không phải của config.

**Remote chỉ là seed — resolve canonical rồi mới dùng OWNER.** Repo đã transfer/rename thì remote giữ owner cũ và GitHub redirect ngầm (call vẫn `200`), sai lệch chỉ lộ ở Step 6 khi board tạo xong không link được vào repo.

```bash
gh api "repos/$OWNER/$REPO" --jq '.full_name, .owner.type'   # canonical, đã theo redirect
```

- Khác remote → dùng **canonical**, báo user một dòng (`remote trỏ <cũ>, canonical là <mới>`).
- `.owner.type` → `owner_type` (`Organization` → `org`, `User` → `user`) cho `create_project` ở Step 6, và segment đầu của URL (`org` → `/orgs/`, `user` → `/users/`).
- `gh` vắng/chưa auth → fallback `OWNER == get_me().login` → user; ngược lại **hỏi user xác nhận**, kèm cảnh báo rằng phép so này KHÔNG phát hiện được ca repo đã transfer.

## 3. Optional secrets (chỉ có/không — KHÔNG BAO GIỜ giá trị)

`GITHUB_TOKEN` đã xong ở Step 1 và ở **cùng file** với các key dưới đây. Ở đây chỉ còn optional, và **không cái nào được phép stop init**:

```bash
[ -n "${TELEGRAM_BOT_TOKEN:-}" ] && echo "TELEGRAM_BOT_TOKEN: set" || echo "TELEGRAM_BOT_TOKEN: absent"
[ -n "${TELEGRAM_CHAT_ID:-}" ]   && echo "TELEGRAM_CHAT_ID: set"   || echo "TELEGRAM_CHAT_ID: absent"
```

Thiếu → `notify` tự tắt lúc runtime, pipeline chạy bình thường. User muốn điền ngay: thêm key vào `env` của `.claude/settings.local.json` bằng **Read + Write** (giữ nguyên mọi key sẵn có, **kể cả `GITHUB_TOKEN`**), và nói rõ nó **chỉ có hiệu lực sau khi restart**.

Figma official MCP server dùng **OAuth**, không có token nào để kiểm ở đây.

## 4. Toggle

Chỉ hai câu hỏi (GitHub và board là bắt buộc, wiring của chúng là hằng số plugin):

- **design source** — *DEV implement theo design nào?* Hỏi `kind`, rồi chỉ hỏi tiếp key của kind đó (skill `design-handoff` §2 giữ shape đầy đủ):

  | kind | Hỏi thêm | Verify tại chỗ |
  |---|---|---|
  | `none` (mặc định) | — | — |
  | `repo` | `path`, `screens` glob, `tokens`, `frame` w×h | `ls` thấy `path`; glob `screens` khớp ≥1 file — không khớp thì hỏi lại, đừng ghi config trỏ vào chỗ trống |
  | `artifact` | `url` | assert dạng `https://claude.ai/…/artifact/<id>` |
  | `design-system` | `project_id` | `DesignSync` method=`list_projects`; user chưa có project nào → nói thẳng và đề nghị chuyển sang kind khác |
  | `figma` | `files: [{ name, key }]` | bảo user authenticate một lần: `claude mcp add --transport http figma https://mcp.figma.com/mcp` rồi `/mcp → figma → Authenticate` |

  Scan trước khi hỏi — thấy prototype trong repo thì **đề xuất `kind: repo`** kèm path tìm thấy, thay vì hỏi mở:

  ```bash
  for d in docs/design design prototype mockups; do [ -d "$d" ] && echo "$d: $(find "$d" -name '*.html' | wc -l) html"; done
  ```

  Ba kind cloud (`artifact` / `design-system` / `figma`) **không pin được revision** — design đổi giữa chừng pipeline mà không ai thấy. Nói một câu cho user biết trước khi chọn.
- **notify** — *ping Telegram khi pipeline dừng chờ bạn?* Cần khi chạy `/agentflow:start` unattended qua `/loop`; ping **một chiều cho người**, không phải kênh giữa các agent. Bật → `notify.enabled: true`, `events: ["blocked", "ready_for_review"]`. Cả hai key đã có giá trị → **smoke test** (fail thì **cảnh báo rồi tiếp tục**, không bao giờ stop init):

  ```bash
  curl -sS --max-time 10 -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
    --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" \
    --data-urlencode "text=AgentFlow: notify wired ✅ (setup check)" \
    -o /dev/null -w '%{http_code}\n' \
    || echo "notify smoke test FAILED — kiểm tra TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID"
  ```

  `200` = ok · `401` = bot token sai · `400 chat not found` = chat id sai, hoặc bạn chưa nhắn `/start` cho bot một lần.

## 5. Phát hiện surface

Surfaces là **tùy chọn**. Scan marker, rồi **ĐỀ XUẤT** — user xác nhận, chỉnh, hoặc đổi tên:

```bash
ls package.json go.mod pom.xml build.gradle build.gradle.kts requirements.txt \
   pyproject.toml Gemfile Cargo.toml pubspec.yaml composer.json 2>/dev/null
ls -d android ios web frontend backend server api admin mobile app 2>/dev/null
```

- **Repo single-app** (một stack, một root) → **BỎ HẲN block `surfaces`** khỏi yaml. Đây là mặc định tốt: DEV/QC gate toàn repo, issue không cần label `component/*`, không có block config nào để trôi. **Đừng** viết `.: { path: "." }` cho có.
- **Nhiều phần build được riêng** → một block mỗi phần, key do user chọn (`api`, `web`, `mobile`, `admin`…), `path` là glob root, `forbidden` là các glob không ai được động (vd `["android/key.properties", "ios/Runner/GoogleService-Info.plist"]`).
- Surface **không** khai báo build/lint/test command hay coverage — marker ở trên chỉ để chốt key + path.

## 6. Board (bắt buộc)

Chi tiết cơ chế: skill **`agentflow-protocol`** → `references/projects-v2-board.md`.

- Hỏi: **tạo board mới** hay **dán URL board có sẵn** (không được skip).
  - *create*: `projects_write` method=`create_project` (owner canonical, owner_type từ Step 2, title) → board **rỗng**.
  - *link*: user dán URL từ trình duyệt. Parse `^https://github\.com/(orgs|users)/([^/]+)/projects/(\d+)` → owner_type + owner + number; validate qua `projects_get` method=`get_project`. Không parse được → hỏi lại, **đừng đoán**.
- **Chốt `board.url`** — giá trị sẽ ghi vào yaml ở Step 8, dạng `https://github.com/{orgs|users}/<OWNER>/projects/<N>`. Board vừa tạo thì ghép từ owner_type + owner + number trả về.
- **Status field 6 option — bước dễ sai nhất của cả init.** Tên option là wire value resolve by-name; sai một ký tự là hard-error ở ticket thật đầu tiên. Bảng dưới là **canonical** cho cả đường tự động lẫn thủ công (agent không đọc description, người đứng trước board thì có):

  | # | Option name (chính xác) | Color | Description |
  |---|---|---|---|
  | 1 | `Inbox` | Gray | Chờ người: chốt AC, hoặc gỡ ticket mang label `blocked`. Kéo card về đây để yêu cầu sửa một PR. |
  | 2 | `Ready for Dev` | Blue | Đã đạt Definition of Ready — DEV tự nhặt. Đừng kéo tay vào đây. |
  | 3 | `In Progress` | Yellow | DEV đang code. Không kéo card khi ticket ở cột này. |
  | 4 | `In QC` | Orange | QC đang review + author test trên PR branch. Không kéo card khi ticket ở cột này. |
  | 5 | `Ready for Review` | Purple | **Việc của bạn**: review + merge PR. Muốn sửa → comment inline trên PR rồi kéo card về Inbox. |
  | 6 | `Done` | Green | Terminal. |

  **Đường tự động — mặc định khi có `gh`.** `projects_write` không expose method sửa **option của một single-select field sẵn có**, nên đây là **carve-out `gh api graphql` chỉ-ở-init**; **hỏi user một câu trước khi chạy**. Một call set cả 6 option, đúng thứ tự, kèm description:

  ```bash
  gh api graphql -f query='mutation($f:ID!){ updateProjectV2Field(input:{fieldId:$f,
    singleSelectOptions:[
      {name:"Inbox",            color:GRAY,   description:"…"}
      {name:"Ready for Dev",    color:BLUE,   description:"…"}
      {name:"In Progress",      color:YELLOW, description:"…"}
      {name:"In QC",            color:ORANGE, description:"…"}
      {name:"Ready for Review", color:PURPLE, description:"…"}
      {name:"Done",             color:GREEN,  description:"…"}
    ]}){ projectV2Field{ ... on ProjectV2SingleSelectField { options{ name } } } } }' -f f="$STATUS_FIELD_ID"
  ```

  `$STATUS_FIELD_ID` (`PVTSSF_…`) đọc qua `{user|organization}(login:){ projectV2(number:){ field(name:"Status"){ ... on ProjectV2SingleSelectField { id } } } }` — chọn `user`/`organization` theo owner_type của `board.url`.

  **`singleSelectOptions` THAY THẾ cả tập option**: option không được truyền kèm `id` sẵn có sẽ bị **xoá cùng mọi value đang trỏ vào nó**. Board vừa tạo (rỗng) → an toàn. **Board link-có-sẵn đang có card → KHÔNG chạy mutation này**, đi đường thủ công.

  **Đường thủ công** — fallback khi thiếu `gh`, user từ chối, hoặc board đã có card: in bảng trên cho user dán vào GitHub UI (Board → `⋯` → Settings → field `Status`), đúng thứ tự. Board mới đi kèm `Todo`/`In Progress`/`Done`: **rename `Todo` → `Inbox`** rồi thêm 4 cái còn thiếu — rename giữ nguyên card, xoá thì mất.

  Cả hai đường đều **validate** qua `projects_list` method=`list_project_fields`: assert đủ 6 option đúng tên. Thiếu → liệt kê tên còn thiếu, yêu cầu thêm, validate lại.
- **Link board vào repo — ngay sau khi tạo.** Không link thì board không xuất hiện ở `https://github.com/<owner>/<repo>/projects`.

  ```bash
  gh api graphql -f query='mutation($p:ID!,$r:ID!){ linkProjectV2ToRepository(input:{projectId:$p,
    repositoryId:$r}){ repository{ nameWithOwner } } }' \
    -f p="$PROJECT_NODE_ID" -f r="$(gh api "repos/$OWNER/$REPO" --jq .node_id)"
  ```

  Fail `Only projects owned by the same owner as the repository can be linked` → **board thuộc sai owner**, gần như luôn là hệ quả của Step 2 lấy OWNER từ remote stale. Không sửa tại chỗ được: tạo lại board dưới owner canonical rồi link lại. (Board **link-có-sẵn** thuộc owner khác repo vẫn chạy được — chỉ là không hiện ở tab Projects của repo.)
- **Board description** — cùng lượt. Board là nơi người PO nhìn hằng ngày, nên đây là entry point đúng cho người mới vào repo:

  ```bash
  gh api graphql -f query='mutation($p:ID!,$d:String!){ updateProjectV2(input:{projectId:$p,
    shortDescription:$d}){ projectV2{ shortDescription } } }' -f p="$PROJECT_NODE_ID" -f d="$DESC"
  ```

  ```
  AgentFlow · <OWNER/REPO> — bạn là Product Owner. Việc mới: /agentflow:task <mô tả> · chạy pipeline: /agentflow:start · xem trạng thái: /agentflow:status. Bạn làm tay đúng 2 việc: chốt AC ở Inbox, và review/merge PR ở Ready for Review.
  ```
- **View: đổi view mặc định thành `Pipeline` / BOARD_LAYOUT.** Project mới mở ra ở TABLE_LAYOUT — sai hình dạng cho một state machine 6 cột.

  ```bash
  gh api graphql -f query='mutation($v:ID!){ updateProjectV2View(input:{viewId:$v, name:"Pipeline",
    layout:BOARD_LAYOUT}){ projectV2View{ name layout } } }' -f v="$VIEW_ID"
  ```

  `$VIEW_ID` = view đầu tiên (`views(first:1)`). BOARD_LAYOUT tự group theo `Status`. Đừng thêm view thứ hai; **đừng** dùng project template (`copyProjectV2` / `markProjectV2AsTemplate`) — một bản sao nữa để drift.
- **Built-in workflows — bước thủ công-UI DUY NHẤT còn lại** (GraphQL chỉ có `deleteProjectV2Workflow`). Project settings → Workflows:
  - **Item added to project** → Status: `Inbox`
  - **Item reopened** → Status: `Inbox`
  - **Item closed** → Status: `Done` — *project mới đã bật sẵn cái này (cùng "PR merged → Done")*, nên thực tế chỉ hai cái trên phải bật tay; vẫn kiểm cả ba.

  Không verify được nó đã bật hay chưa, nên `/agentflow:task` vẫn ghi Status explicit — không bao giờ dựa vào workflow.

  **Nhấn mạnh với user rằng `Item closed → Done` là cái quan trọng nhất trong ba cái**: nó là lane thoát cho việc merge PR trên github.com. Chưa bật ⇒ card kẹt ở `Ready for Review` với issue đã đóng, vô hình với cả queue lẫn bảng đếm.

Board op fail vì permission → bảo user thêm scope `project` vào classic PAT (thêm scope vào token có sẵn **không** đổi value, nên không phải sửa settings và không phải restart) rồi **stop**.

## 7. Labels

Idempotent. **Label không mang state** — chỉ classification + hai aux signal. Mỗi label gọi `label_write` method=`create`; lần chạy lại dùng method=`update` để re-apply color/description thay vì báo lỗi:

```
# type/* — green
label_write name="type/feature"     color=0E8A16  description="AgentFlow: new capability"
label_write name="type/improvement" color=0E8A16  description="AgentFlow: enhancement"
label_write name="type/bug"         color=0E8A16  description="AgentFlow: defect"

# component/<surface> — MỘT cái cho mỗi surface khai báo ở Step 5 (bỏ qua nếu single-surface) — purple
for s in <surface keys>: label_write name="component/$s" color=5319E7 description="AgentFlow: $s surface"

# aux signals — amber
label_write name="rework"  color=FBCA04  description="AgentFlow: QC reject — DEV đọc QC rejection mới nhất trước"
label_write name="blocked" color=D93F0B  description="AgentFlow: Inbox chờ quyết định của người; /agentflow:start bỏ qua — gỡ: /agentflow:task #<n>"
```

**Description cap 100 ký tự** — GitHub reject cứng, không truncate. Chuỗi `blocked` ở trên là 93, sát trần: đừng nới.

**Label lạ = dấu vết một init cũ.** `list_label` xong, liệt kê label có description mở đầu `AgentFlow:` mà **không** thuộc bộ trên → báo ở Step 11. **Không tự xoá**: issue cũ có thể còn gắn.

## 8. Ghi file

Hai file, hai mối quan tâm (skill `agentflow-protocol` §1):

1. **`agentflow.yaml` ở REPO ROOT** — copy `${CLAUDE_PLUGIN_ROOT}/agentflow.yaml` rồi điền value. Chỉ sửa value, không dựng cấu trúc mới; **không đọc được template → STOP**, đừng dựng yaml từ trí nhớ.

   | Key | Giá trị |
   |---|---|
   | `schema: 2` | copy nguyên văn — schema version của file yaml, **KHÔNG** substitute từ `plugin.json` |
   | `board.url` | URL chốt ở Step 6. Ghi xong **assert nó khớp regex** `^https://github\.com/(orgs\|users)/[^/]+/projects/[0-9]+$` — template để `null`, và một init crash giữa chừng để lại `null` là fail sớm và đọc được |
   | `forbidden` | Chỉ ghi khi user muốn chặn thêm glob cấp repo. **Mặc định → để nguyên dạng comment** |
   | `surfaces` | Step 5 phát hiện **nhiều** surface → bỏ comment block ví dụ và khai báo từng cái (`path` + `forbidden`). **Single-surface → để nguyên dạng comment** |
   | `design.kind` + key của kind đó | Step 4 — **chỉ ghi key thuộc kind đã chọn**, key của kind khác là rác |
   | `notify.enabled` | Step 4 |

   Giữ nguyên các comment đã curate. **Đừng bịa key template không có** — đặc biệt không thêm `project:`, `connections:`, `labels:`, `board.number`, hay `board.columns`: repo/owner/default-branch suy từ git, board params parse từ `board.url`, còn label và 6 tên column là hằng số plugin.

2. **`.claude/settings.local.json`** — **sinh ra, không copy.** init chỉ ghi **hai** key, cả hai đều phải suy lúc chạy. Đây cũng là file giữ `env` (§1a) — nên **mọi thao tác ghi phải là merge**, xem 2c.

   **init KHÔNG sinh `permissions`.** Allow/deny là cấu hình của riêng từng người, plugin không áp đặt. Hệ quả phải nói thẳng ở Step 11: forbidden paths / no-force-push / no-merge chỉ còn là prompt contract (README §Safety).

   **2a. `enabledPlugins` — suy ra plugin id thật, đừng hardcode** (fork hoặc marketplace đổi tên là id đổi theo):

   ```bash
   jq -r '.plugins | keys[] | select(startswith("agentflow@"))' ~/.claude/plugins/installed_plugins.json
   ```

   → `{ "enabledPlugins": { "<id vừa đọc>": true } }`. Không đọc được → dùng `agentflow@agent-flow-plugins` và nói rõ là đang đoán.

   **2b. `extraKnownMarketplaces` — suy từ marketplace ĐANG đăng ký.** Thiếu nó thì `enabledPlugins` trỏ vào marketplace chưa đăng ký và Claude Code bỏ qua entry đó (log `Skipping orphaned enabledPlugins entry`).

   ```bash
   MKT="${ID#*@}"   # phần sau @ của plugin id ở 2a
   jq --arg m "$MKT" '.[$m].source' ~/.claude/plugins/known_marketplaces.json
   ```

   - `source == "github"` → ghi nguyên vào `extraKnownMarketplaces.<MKT>.source`. Đây là ca đúng.
   - `source == "directory"` → ghi nguyên value đó (đường dẫn chỉ đúng trên máy này, nhưng file này cũng chỉ sống trên máy này).
   - Không đọc được → bỏ key, note ở Step 11. **Đừng bịa một `repo`.**

   **2c. Merge, không ghi đè — và `env` là phần dễ mất nhất.** File đã tồn tại → đọc nó, **giữ nguyên mọi key và entry sẵn có**, chỉ **thêm** `extraKnownMarketplaces` nếu chưa có.

   **Ngoại lệ đúng một key: `enabledPlugins.<id>` phải ghi đè thành `true`.** `claude plugin install --scope local` đã ghi sẵn `"<id>": false` vào chính file này (plugin khai `defaultEnabled: false`); "chỉ thêm nếu chưa có" ở key đó sẽ để plugin kẹt ở trạng thái tắt và mọi `/agentflow:*` im lặng không load.

   Block `env` mang `GITHUB_TOKEN` (§1a): **đọc rồi ghi lại nguyên vẹn**. Ghi bằng **Read + Write**, không Bash. **Không bao giờ xoá hay sửa** key user tự thêm — kể cả `permissions` họ tự viết.

   **2d. File này gitignored, nên nó là cấu hình CỦA MÁY NÀY.** Teammate clone repo về **không** thừa hưởng `enabledPlugins` — mỗi người tự chạy `/agentflow:init` một lần. Nêu điều này ở Step 11 nếu repo có nhiều người.

**Không sinh file doc thứ ba, và không nhét doc vào `agentflow.yaml`** — bản sao "dùng như thế nào" trong repo user sẽ đóng băng. Entry point cho người mới clone là README của plugin + description của board (Step 6).

## 9. Scaffold project skill (opt-in)

Đề nghị tạo skill stub role-prefix dưới `.claude/skills/`: `dev-*` → DEV, `qc-*` → QC. Agent **auto-discover** chúng — không có registry nào phải đăng ký.

**Luôn đề xuất `qc-automation-test`** (QC load nó để thêm test ID và author test flow trên PR branch). Đề xuất phần còn lại khớp surface đã detect, vd `dev-<surface>-development`. **Hỏi trước khi tạo.** Mỗi stub được chấp nhận: ghi một `SKILL.md` với YAML frontmatter (`name` = tên directory, `description` một dòng) + body TODO. Liệt kê chính xác cái gì đã tạo.

## 10. Verify (BẮT BUỘC — đây là nơi bắt payload lỗi)

```bash
python3 -c "import yaml; yaml.safe_load(open('agentflow.yaml'))" && echo "yaml: ok"
python3 -c "import json; json.load(open('.claude/settings.local.json'))" && echo "settings.local.json: ok"
```

- **Labels:** `list_label` → đủ 3 `type/*`, một `component/*` cho mỗi surface (nếu có), `rework`, `blocked`.
- **Board:** `projects_get` method=`get_project` + `projects_list` method=`list_project_fields` (đủ 6 option Status), tham số parse từ `board.url` vừa ghi — đây cũng là lần verify rằng URL parse ra đúng board.

### Board write smoke test — bắt buộc, KHÔNG hỏi consent

Board resolve được **không** chứng minh AgentFlow ghi được vào nó, và Status write là mandatory-success: một `updated_field` sai shape sẽ dừng pipeline ngay ở ticket thật đầu tiên. (`owner` / `owner_type` / `project_number` dưới đây đều parse từ `board.url`.)

```
# 1. issue tạm
issue_write method=create title="AgentFlow setup check" body="temporary — safe to close"   → #<n>

# 2. add lên board → item_id
projects_write method=add_project_item
  owner=<owner> owner_type=<org|user> project_number=<N>
  item_type=issue item_owner=<owner repo> item_repo=<repo> issue_number=<n>

# 3. set Status=Inbox — BY-NAME shape
projects_write method=update_project_item
  owner=<owner> owner_type=<org|user> project_number=<N>
  item_owner=<owner repo> item_repo=<repo> issue_number=<n>
  updated_field={ name: "Status", value: "Inbox" }

# 4. READ-BACK — thiếu bước này thì bước 3 không chứng minh được gì
projects_get method=get_project_item item_id=<item_id> field_names=["Status"]   → assert "Inbox"

# 5. transition Inbox → Ready for Dev, read-back lần nữa
projects_write method=update_project_item ... updated_field={ name: "Status", value: "Ready for Dev" }
projects_get   method=get_project_item item_id=<item_id> field_names=["Status"] → assert "Ready for Dev"

# 6. dọn dẹp (chạy KỂ CẢ khi 4/5 fail — dọn trước, báo lỗi sau)
projects_write method=delete_project_item owner=<owner> project_number=<N> item_id=<item_id>
issue_write    method=update state=closed
```

**Bước 4/5 fail → STOP** và báo đúng nguyên nhân:

| Triệu chứng | Nguyên nhân | Fix |
|---|---|---|
| `option_not_found` (kèm candidates) | Tên option Status không khớp 6 hằng số | Sửa trong GitHub UI cho khớp một-đối-một, chạy lại `/agentflow:init` |
| Lỗi khác về `updated_field` | Sai shape — by-id không resolve option theo tên | Dùng **by-name** shape (reference `projects-v2-board.md`). Không tự chế shape khác |
| Status read-back rỗng/vắng | Thiếu `field_names:["Status"]` ở call read | Luôn truyền `field_names` |
| Board không resolve (404) | `board.url` sai owner/owner_type/number | Dán lại URL từ trình duyệt, chạy lại |

## 11. Tóm tắt

```
AgentFlow initialized on <OWNER/REPO> (config schema 2)

Board       : <board.url> — Status field 6 option, built-in workflows đã hướng dẫn bật
Surfaces    : <key>=<path>, …   |   single-surface (không khai báo — gate toàn repo)
Labels      : <5 + N> created/updated (type/* ·3, component/* ·N, rework, blocked)
Design      : <kind> <path/url/project_id/files — hoặc "không khai báo, DEV build từ AC">
Notify      : <on (smoke ✓) | on (chưa có secret — tự tắt) | off>
Auth        : GITHUB_TOKEN (env, .claude/settings.local.json — gitignored ✓) — login <login>
              TELEGRAM_* cùng file: <có | không>
Skills      : <stub đã scaffold, hoặc none>
Files       : agentflow.yaml (commit), .claude/settings.local.json (gitignored),
              [.claude/skills/<role>-* …]
              <repo nhiều người: mỗi teammate tự chạy /agentflow:init — enabledPlugins
               nằm trong file gitignored, không đi theo repo>
Permissions : init không sinh — forbidden paths / no-force-push / no-merge là prompt
              contract. Muốn gate tầng harness thì tự thêm permissions.deny.

Next: /agentflow:task <mô tả> để tạo việc đầu tiên, rồi /agentflow:start để vào team mode.
```
