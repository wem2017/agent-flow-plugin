---
name: figma-design
description: Cơ chế Figma của skill design-handoff — official Figma MCP server (fallback PAT/REST), parse URL/node id, và extract spec/token từ một frame. Load khi design.kind là figma; discipline chung (revision pinning, design mâu thuẫn AC, missing input) nằm ở design-handoff.
---

# Figma — provider của `design-handoff`

Cơ chế Figma cho `design.kind: figma`. Skill **`design-handoff`** giữ phần chung: extract gì, revision pinning, ba ca ranh giới, trust. File này chỉ trả lời *lấy dữ liệu từ Figma bằng cách nào*.

MCP server chỉ cung cấp *structured context + một điểm khởi đầu về code*; **bạn adapt nó vào codebase này — không bao giờ paste output nguyên văn.**

## Gate trước khi dùng

**Không** gọi bất kỳ Figma tool hay REST endpoint nào trừ khi `design.kind: "figma"` **và** ít nhất một access path thực sự khả dụng:

- **Official Figma MCP server (preferred)** — khả dụng khi `figma` MCP server đã connect và OAuth-authenticated. Verify bằng một call `whoami` (trả về identity đang đăng nhập); lỗi = chưa authenticate.
- **PAT fallback** — khả dụng khi `${FIGMA_TOKEN}` có giá trị trong block `env` của `.claude/settings.local.json`, dùng cho legacy Framelink server / REST path. (Nó ở file local của repo vì `curl` đọc nó như một subprocess — xem `agentflow-protocol` §1 → Secret.)

Gate fail (kind khác, hoặc không path nào khả dụng) → `design-handoff` §5 quyết định đây là degrade hay missing input. Đừng tự quyết ở đây.

## Path A — official Figma MCP server (preferred)

Official server (Dev Mode MCP của Figma) authenticate qua **OAuth** — trên path này **không có `FIGMA_TOKEN`/`X-Figma-Token`**. Gọi tool bằng fully-qualified name (đừng "discover at runtime" — tên là ổn định):

| Bước | Tool | Dùng cho |
|---|---|---|
| 1. Phác thảo một design lớn | `get_metadata` | XML thưa gồm node ID / tên / type / kích thước. Gọi không kèm `nodeId` để liệt kê top-level page, rồi drill vào. Rẻ — dùng để tìm đúng node trước khi pull full context. |
| 2. Pull design context | `get_design_context` | Tool design→code chính. Trả reference code (**React + Tailwind mặc định**), screenshot, và metadata. Coi là *context để translate*, không phải code để paste. |
| 3. Map tokens | `get_variable_defs` | Variable/style trong selection (màu, spacing, typography), vd `{ 'color/primary': '#1A73E8' }`. Map tới token sẵn có của project. |
| 4. Visual check | `get_screenshot` | PNG của node để diff implementation, đảm bảo chính xác layout. |
| 5. Reuse component thật | `get_code_connect_map` | `{ nodeId: { componentName, source, snippet, … } }` — component code thật mà node map tới. **Ưu tiên component đã map thay vì markup viết mới.** |

**Prompt tool bằng thông tin cụ thể của project** để output khớp codebase này thay vì mặc định React+Tailwind: framework (*"generate this selection in `<framework>`"*), reuse (*"using components from `<surfaces.<key>.path>/components`"*), token thay vì literal (*"get the variable names and values for this selection"*).

**Remote vs desktop:** server **remote** (`https://mcp.figma.com/mcp`) là **link-based** — truyền URL figma.com của frame/layer (hoặc `fileKey` + `nodeId`); nó tự extract node-id. Prompting **selection-based** ("my current selection") chỉ hoạt động với server desktop. AgentFlow chạy headless → luôn truyền URL/node tường minh lấy từ AC.

**Code Connect:** project đã set up Code Connect thì set framework label cho mapping đúng (`clientFrameworks` khớp Code Connect label, vd `React`, `SwiftUI`). Việc author Code Connect mapping nằm ngoài scope của DEV.

## Path B — PAT / REST fallback (legacy)

<details>
<summary>Framelink server hoặc Figma REST — cho setup headless/enterprise không hoàn tất được OAuth. Dùng PAT <code>FIGMA_TOKEN</code> (giá trị trong <code>.claude/settings.local.json</code>), KHÔNG phải official server.</summary>

Đây là **integration riêng biệt** so với official server. Chỉ dùng khi official MCP path không khả dụng và `FIGMA_TOKEN` đã set. Token đặt trong **header** `X-Figma-Token`, không bao giờ trong URL.

```bash
# Whole file (structure + styles)
curl -s -H "X-Figma-Token: $FIGMA_TOKEN" \
  "https://api.figma.com/v1/files/$FILE_KEY" | jq '.document.children[].name'

# A specific frame/node (rẻ hơn) — NODE_ID dùng ':' ở đây, không phải '-'
curl -s -H "X-Figma-Token: $FIGMA_TOKEN" \
  "https://api.figma.com/v1/files/$FILE_KEY/nodes?ids=$NODE_ID" | jq '.nodes'

# Rendered preview (trả image URLs)
curl -s -H "X-Figma-Token: $FIGMA_TOKEN" \
  "https://api.figma.com/v1/images/$FILE_KEY?ids=$NODE_ID&format=png&scale=2"
```

Legacy Framelink MCP server (`figma-developer-mcp`) đọc cùng `FIGMA_TOKEN` dưới dạng `FIGMA_API_KEY`.
</details>

## Parse URL

```
https://www.figma.com/design/AbC123dEfGhIj/Checkout-Flow?node-id=1234-5678
                              └── FILE_KEY ──┘             └─ node-id ─┘
```

- **FILE_KEY** là path segment ngay sau `/design/` (link cũ dùng `/file/` — cùng vị trí). Branch URL `…/design/<key>/branch/<branchKey>/…` → dùng **branchKey** làm file key.
- **node-id** trong URL phân tách bằng `-` (`1234-5678`). **Official MCP tool chấp nhận cả `1234-5678` lẫn `1234:5678`**; **REST yêu cầu `:`**. Convert cho fallback: `NODE_ID="${URL_NODE_ID//-/:}"`.

`design.files` trong `agentflow.yaml` có thể liệt kê sẵn file đã biết dưới dạng `{ name, key }`. AC gọi tên file bằng `name` → resolve `key` ở đó thay vì đòi URL. URL trơ không có `node-id` = toàn bộ file/page — dùng `get_metadata` và chọn frame khớp AC.

## Sau khi lấy được context

Quay lại **`design-handoff`** §3 (extract gì → map sang token/component sẵn có), §4 (ghi revision: trích `FILE_KEY` + `NODE_ID` vào comment `[DEV]`), §5 (design mâu thuẫn AC · missing input · design đổi giữa chừng). **Đừng** tự chế quy tắc riêng cho Figma ở đây.

## Secret hygiene

Trên official OAuth path **không có Figma token nào cần bảo vệ**. Trên PAT fallback, `FIGMA_TOKEN` là secret: chỉ tham chiếu qua `${FIGMA_TOKEN}`, giữ trong header `X-Figma-Token` (không bao giờ trong URL). Full rules: `agentflow-protocol` §1 → *Secret hygiene*.
