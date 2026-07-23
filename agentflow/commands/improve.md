---
description: Capture một bài học từ lần dùng AgentFlow thực tế (điều agent nên làm khác, board write fail, misroute, convention bị hiểu sai, tối ưu prompt) và fold nó vào đúng file tri thức trong plugin SOURCE — minimal edit có duyệt diff, bump version + CHANGELOG, chạy release loop để version sau hoạt động chính xác hơn. Không truyền bài học thì tự mine session hiện tại tìm friction point.
argument-hint: "[bài học / điều agent nên làm khác lần sau — trống để tự mine session] [--no-release | --release]"
---

Bạn đang **dạy** plugin agentflow giỏi hơn: nhận bài học freeform, fold vào đúng nơi tri thức sống,
theo nguyên tắc **confirm-first** (sửa file plugin → user duyệt diff trước khi ghi). Mọi edit đi vào
**SOURCE** — không bao giờ vào `${CLAUDE_PLUGIN_ROOT}` (đó là cache snapshot khoá theo version; sửa
vào là mất khi update).

## 0. Preflight — resolve SOURCE + drift check

```bash
command -v jq >/dev/null || echo "STOP: cần jq (brew install jq)"
SRC="$(jq -r '.["agent-flow-plugins"].source | if .source=="directory" then .path else empty end' ~/.claude/plugins/known_marketplaces.json)/agentflow"
test -f "$SRC/.claude-plugin/plugin.json" || SRC=""
```

- `SRC` rỗng (marketplace là `github` source — máy teammate, hoặc path chết) → DỪNG, không bao giờ
  sửa cache. Hướng dẫn: máy không giữ source thì gửi bài học qua issue/PR lên repo marketplace cho
  maintainer chạy `/improve`; path chết thì `claude plugin marketplace remove/add` lại đúng chỗ.
- **Drift check**: so version source `SRC_V=$(jq -r '.version' "$SRC/.claude-plugin/plugin.json")`
  với bản đang cài `INST=$(jq -r '.plugins["agentflow@agent-flow-plugins"] // [] | map(select(.scope=="user")) | .[0].version // "none"' ~/.claude/plugins/installed_plugins.json)`.
  Lệch → warn một dòng: release lần này ship kèm toàn bộ backlog từ `<INST>` tới `<SRC_V>` — không
  chặn, chỉ để user không ngạc nhiên khi behavior đổi nhiều hơn một bài học.

## 1. Nhận bài học

Bài học: `$ARGUMENTS` (tách flag `--no-release`/`--release` ra khỏi nội dung nếu có).

**`--release`** (hoặc: drift check §0 báo lệch và user xác nhận không có bài học mới) → bỏ qua
§1–§5, nhảy thẳng tới §6 để xả backlog đã tích — đây chính là đường hành động cho lời nhắc
"release gộp".

**Trống → mine session hiện tại** tìm friction point:

- User phải **sửa lại agent**: message phủ định/chỉnh ngay sau một action, hoặc user tự làm lại tay.
- **Write call retry ≥2 lần** với params chỉnh dần tới khi pass (nhất là `projects_write`/`issue_write`)
  — bài học nằm ở delta params.
- **Fail-stop/degrade do thiếu kiến thức** (shape call, scope, thứ tự bước) — loại lỗi môi trường
  one-off (token hết hạn, mạng).
- **Auto-invoke sai**: command/skill/agent trigger nhầm chỗ, hoặc không trigger khi đáng lẽ phải.
- **Convention output bị sửa lại** (branch name, comment prefix, AC format, tên Status…).

Đề xuất 1–3 candidate, mỗi cái một dòng dạng "agent nên X thay vì Y (bằng chứng: …)", cho user
chọn/sửa/bỏ. Không thấy gì → hỏi thẳng: "Bài học lần này là gì?". Bài học **mơ hồ** (không chỉ ra
được hành vi khác đi cụ thể) → hỏi một câu làm rõ trước khi routing, đừng đoán.

## 2. Phân tầng — plugin hay project? (+ STOP protocol-change)

**Project-level** — convention/quyết định của riêng MỘT repo đang dùng agentflow, không generalize
cho mọi project: đích là repo ĐÓ, không phải plugin — config value trong `.claude/agentflow.yaml`,
hoặc một project skill role-prefixed `.claude/skills/<dev|qc|pmo>-*` (tạo mới thì đăng ký vào
`skills:` registry — skill: `setup-agentflow`). Vẫn confirm-first show diff, nhưng KHÔNG bump plugin
version, KHÔNG release loop. Xong dừng ở đây.

**STOP — protocol-change class.** Bài học đụng (a) FORMAT/schema của `agentflow.yaml` (thêm/đổi/bỏ
key mà agent đọc), (b) semantics Status column / state machine transition, hoặc (c) wire value (tên
Status option, comment prefix, format AGENTFLOW-STATE) → KHÔNG phải patch thường: cần bump protocol
constant trong `skills/setup-agentflow/SKILL.md` §"Version gate" + dòng `agentflow_version` trong
`templates/agentflow.yaml.template` + migration trong `commands/agentflow-init.md`, và mọi repo hiện
có sẽ lệch protocol cho tới khi re-init. DỪNG, liệt kê chính xác các chỗ phải đổi, chỉ tiếp tục khi
user xác nhận làm nó như một thay đổi có chủ đích (bump **minor/major**, không phải patch).

## 3. Routing table (plugin-level)

Map bài học tới **một** đích chính dưới `$SRC`:

| Bài học nói về… | File đích |
|---|---|
| Intake/refine/DoR gate, cách viết `## For DEV` / `## For QC` | `agents/pmo.md` |
| Cách implement, branch/PR behavior, blocked/resume | `agents/dev.md` (flow git thuần → `skills/git-flow-working/SKILL.md`) |
| Review đối chiếu AC, author test, QC tier, rework/escalate | `agents/qc.md` |
| Wire protocol: comment prefix, DoR/DoD, AGENTFLOW-STATE, trust rules | `skills/project-board-protocol/SKILL.md` |
| Board mechanics: shape call `projects_*`, Status write, paginate, scopes | `skills/project-board-protocol/reference/projects-v2-board.md` |
| Đọc config, read-before-use gate, connections/env | `skills/setup-agentflow/SKILL.md` |
| Figma → code mapping | `skills/figma-design/SKILL.md` |
| Behavior của một command entry (`/task`, `/start`, …) | `commands/<lệnh>.md` (kể cả chính `improve.md`) |
| **Auto-invoke sai lúc/sai chỗ** | `description:` frontmatter của file tương ứng (đó là cái điều khiển auto-invoke) |
| Shape config/README sinh mới | `templates/*` (đổi key yaml = protocol-change class §2) |
| Hook / MCP server | `hooks/hooks.json` / `.mcp.json` |

Đụng nhiều file → chọn MỘT primary home (nơi agent sẽ đọc nó đúng lúc cần), file khác tối đa một
dòng link. Thật sự cần 2 edit độc lập → show cả 2 diff, duyệt một lượt, một bump + một mục CHANGELOG
chung. Không chắc → nêu 1–2 ứng viên cho user chọn, đừng đoán bừa.

## 4. Soạn minimal edit, đúng style

- Đọc file đích trước. Fold thành **thay đổi nhỏ nhất** có tác dụng: một dòng gotcha, một mục list,
  sửa một câu — KHÔNG viết lại section, KHÔNG đổi cấu trúc heading.
- Giữ style file đích: tiếng Việt + thuật ngữ Anh, WHY trong ngoặc cho chỗ không hiển nhiên,
  cross-ref dạng (skill: `x` → §"section"). Đã có ý tương tự → chỉ làm rõ hơn, không lặp.
- Edit đổi behavior user-facing của một command → cập nhật luôn hàng tương ứng trong bảng Commands
  của `README.md` (cùng diff).

## 5. Duyệt → ghi

Trình bày: bài học một dòng + file đích + **diff dự kiến** + **mức bump dự kiến** (patch/minor →
version mới) — một lần duyệt phủ cả edit lẫn bump. Chờ duyệt — chưa duyệt chưa ghi gì. Khi đồng ý:

1. Áp edit vào `$SRC/...`.
2. **Bump version** trong `$SRC/.claude-plugin/plugin.json` — `LEVEL=patch` mặc định; thêm
   capability/file mới → `minor`; nhiều bài học một lượt → MỘT bump theo level cao nhất. Set
   `LEVEL` rồi chạy block **đúng một lần**:
   ```bash
   PJ="$SRC/.claude-plugin/plugin.json"; LEVEL=patch   # hoặc LEVEL=minor — chọn MỘT
   tmp=$(mktemp); jq --arg l "$LEVEL" '.version |= (split(".") | (if $l=="minor" then .[1]=((.[1]|tonumber+1)|tostring) | .[2]="0" else .[2]=((.[2]|tonumber+1)|tostring) end) | join("."))' "$PJ" > "$tmp" && mv "$tmp" "$PJ"
   NEW=$(jq -r '.version' "$PJ")
   ```
3. **Ghi `$SRC/CHANGELOG.md`** — prepend một mục `## [<NEW>] - <date +%F>` ngay **trên** entry
   `## [...]` mới nhất (giữ nguyên dòng mô tả dưới header `# Changelog`), với bullet tóm tắt bài
   học + `files:` đã đổi (nhiều bài học = nhiều bullet một mục).
4. **`claude plugin validate "$SRC"`** — chạy NGAY TẠI ĐÂY, kể cả khi `--no-release` (read-only,
   rẻ; fail thì user biết đúng lượt nào gây ra thay vì tới lần release gộp mới vỡ giữa nhiều bài
   học tích luỹ). Fail → giữ nguyên edits, in lỗi, gợi `git diff` trong repo source để soi.

## 6. Release loop + báo cáo

Cache khoá theo version — không chạy loop này thì bản sửa **không bao giờ** có hiệu lực
(CONTRIBUTING.md). Có flag `--no-release` → dừng sau §5 (validate đã chạy ở đó); drift check lần
sau sẽ nhắc release gộp — xả bằng `/improve --release`.

1. **Dirty-tree check** — directory source snapshot NGUYÊN working tree, nên mọi edit chưa commit
   trong `$SRC` (kể cả WIP không liên quan bài học) sẽ ship cùng: chạy
   `git -C "$SRC" status --porcelain -- .`; có file bẩn NGOÀI các file lượt improve này vừa ghi →
   liệt kê cho user và đưa vào câu hỏi duyệt ở bước 2 (chúng sẽ go live ở mọi project trên máy).
2. Hỏi user một lần (kèm danh sách bước 1 nếu có) rồi chạy:
   ```bash
   claude plugin marketplace update agent-flow-plugins && claude plugin update agentflow@agent-flow-plugins
   ```
3. **Verify**: đọc lại `installed_plugins.json` (query như §0) — installed == `NEW` và cache dir
   `~/.claude/plugins/cache/agent-flow-plugins/agentflow/<NEW>/` tồn tại. Mismatch → chạy lại
   `marketplace update`; kẹt nữa → mẹo `uninstall` + `install` (CONTRIBUTING.md).

In: version cũ → mới, file đã đổi, một dòng tóm tắt. Nhắc **restart Claude Code** để load (session
này vẫn chạy snapshot cũ). Protocol-change → nhắc thêm mỗi repo đang dùng chạy `/agentflow-init` để
migrate. Cuối cùng hỏi (không tự làm): commit repo plugin với message `improve: <tóm tắt> (v<NEW>)`?
(WHY message có nghĩa thay vì "update": `installed_plugins.json` ghi `gitCommitSha` lúc install —
commit đúng nhịp release thì sha ↔ version ↔ CHANGELOG trace được nhau.) Không bao giờ tự push.
