---
name: figma-design
description: Kéo design context từ Figma và map nó tới acceptance criteria của issue — gate trên figma.enabled, official Figma MCP server (fallback PAT/REST), rồi translate chứ không bao giờ paste kết quả vào implementation. Dùng khi một DEV issue đụng visual surface và AC của nó tham chiếu một Figma frame, file, hay link figma.com.
---

# Figma Design Handoff

**DEV** fetch design context thế nào khi một issue đụng visual surface và AC tham chiếu một Figma design.

MCP server chỉ cung cấp *structured context + một điểm khởi đầu về code*; **bạn adapt nó vào codebase này — không bao giờ paste output nguyên văn.**

## Gate trước khi dùng

Đọc `agentflow.yaml` ở repo root. **Không** gọi bất kỳ Figma tool hay REST endpoint nào trừ khi `figma.enabled: true` **và** ít nhất một access path thực sự khả dụng:

- **Official Figma MCP server (preferred)** — khả dụng khi `figma` MCP server đã connect và OAuth-authenticated. Verify bằng một call `whoami` (trả về identity đang đăng nhập); lỗi = chưa authenticate.
- **PAT fallback** — khả dụng khi `${FIGMA_TOKEN}` có giá trị trong block `env` của `.claude/settings.local.json`, dùng cho legacy Framelink server / REST path. (Nó ở file local của repo vì `curl` đọc nó như một subprocess — xem `agentflow-protocol` §1 → Secret.)

Gate fail (disabled, hoặc không path nào khả dụng) → **skip toàn bộ design lookup** và build từ AC **khi AC tự đủ**. Note lại trong comment `[DEV]` (vd `design lookup skipped: figma not configured — built from AC only`) để reviewer biết implementation là AC-driven. **Không bao giờ block dev work chỉ để chờ một optional service** — nhưng một màn hình mới mà AC thực sự cần một design chưa từng được cung cấp thì đó là *missing input*, không phải build chỉ-từ-AC: xem *Handoff discipline*.

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

`figma.files` trong `agentflow.yaml` có thể liệt kê sẵn file đã biết dưới dạng `{ name, key }`. AC gọi tên file bằng `name` → resolve `key` ở đó thay vì đòi URL. URL trơ không có `node-id` = toàn bộ file/page — dùng `get_metadata` và chọn frame khớp AC.

## Cần extract gì cho implementation

| Lấy từ design | Dùng cho |
|---|---|
| Auto-layout direction, gap, padding, alignment | Cấu trúc flex/stack và spacing |
| Sizing (fixed / hug / fill), constraints | Hành vi width/height, responsiveness |
| Màu, fill, effect (`get_variable_defs`) | Theming — match token sẵn có |
| Typography (family, size, weight, line-height) | Text style — match token sẵn có |
| Tên component/layer + `get_code_connect_map` | Component sẵn có nào để reuse |
| Variable / design token | Tham chiếu token, không phải literal |

**Ưu tiên design token và component sẵn có của project thay vì giá trị hardcode.** Design chỉ định `#1A73E8` mà project có token `--color-primary` cùng giá trị → tham chiếu token. Chỉ hardcode khi không có token nào, và flag để follow-up.

Tạo một **implementation checklist** ngắn gắn với AC, mỗi entry trích frame/node nguồn và token/component nó map tới.

## Handoff discipline

- **AC là nguồn chân lý cho CÁI GÌ; design là nguồn chân lý cho việc nó TRÔNG như thế nào.** Khớp nhau → implement theo cả hai.
- **Design mâu thuẫn AC** — frame có field mà AC không nhắc, hoặc AC yêu cầu behavior mà design bỏ qua → **không** âm thầm chọn design thay vì AC. Đây là **human-intervention case**: post `[DEV] ?` với tối đa 3 câu hỏi đánh số, add aux label `blocked`, tự ghi Status → `Inbox`, rồi dừng. Người gỡ qua `/agentflow:task #<n>`.
- **Issue là màn hình mới mà AC tham chiếu design nhưng không có Figma nào được cung cấp** — không URL/node trong AC, không gì khớp trong `figma.files` → **không** bịa visual design. Đây là **missing input**, xử lý y hệt case trên (`[DEV] ?` → `blocked` → `Inbox` → dừng). Chỉ build thẳng từ AC khi AC tự đặc tả đầy đủ màn hình đó.
- Trích cụ thể frame (`FILE_KEY` + `NODE_ID`) trong comment `[DEV]` để QC và người mở được cùng một node.
- Design đổi sau khi ticket đã ở `Ready for Dev` là một thay đổi AC/scope, không phải quyết định tùy tiện của DEV — route qua cùng đường trên.

## Secret hygiene

Trên official OAuth path **không có Figma token nào cần bảo vệ**. Trên PAT fallback, `FIGMA_TOKEN` là secret: chỉ tham chiếu qua `${FIGMA_TOKEN}`, giữ trong header `X-Figma-Token` (không bao giờ trong URL). Full rules: `agentflow-protocol` §1 → *Secret hygiene*.
