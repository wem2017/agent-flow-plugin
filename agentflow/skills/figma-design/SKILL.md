---
name: figma-design
description: Kéo design context từ Figma trong lúc làm UI và map nó tới acceptance criteria của issue — gate trên connections.figma, ưu tiên official Figma MCP server (get_metadata → get_design_context → get_variable_defs → get_screenshot → get_code_connect_map) với fallback PAT/REST, rồi translate (không bao giờ paste) kết quả vào implementation. Dùng khi một DEV issue đụng vào visual surface và AC của nó tham chiếu một Figma frame, file, hay link figma.com.
---

# Figma Design Handoff

**DEV** agent fetch design context như thế nào khi một issue đụng vào visual surface (bất kỳ `component/<surface>` nào mà surface được khai báo trong `surfaces:` có UI — web, admin, mobile, …) và AC tham chiếu một Figma design.

**Design quyết định thứ đó TRÔNG như thế nào và layout ra sao; AC của issue định nghĩa CÁI GÌ phải đúng.** Hai thứ này không thay thế cho nhau được — xem *Handoff discipline*. Theo chính guidance của Figma, MCP server chỉ cung cấp *structured context + một điểm khởi đầu về code*; **bạn adapt nó vào codebase này — bạn không bao giờ paste output của nó nguyên văn.**

## Gate trước khi dùng

Figma là một connection như mọi connection khác — đọc wiring của nó trong `.claude/agentflow.yaml` trước (xem skill: `setup-agentflow` để biết full spec về connection/env). **Không** gọi bất kỳ Figma tool hay REST endpoint nào trừ khi `connections.figma.enabled: true` **và** ít nhất một access path bên dưới thực sự khả dụng:

- **Official Figma MCP server (preferred)** — khả dụng khi `figma` MCP server đã được connect và OAuth-authenticated. Verify bằng một call `whoami` (nó trả về identity đang đăng nhập); nếu lỗi, server chưa được authenticate.
- **PAT fallback** — khả dụng khi biến được đặt tên bởi `connections.figma.auth.token_env` (vd `FIGMA_TOKEN`) có mặt, dùng cho legacy Framelink server / REST path.

```bash
# Gate check — connection on?
yq '.connections.figma.enabled' .claude/agentflow.yaml      # → true
# then probe a path: official MCP (whoami) OR a present PAT for the fallback
[ -n "${FIGMA_TOKEN:-}" ] && echo "PAT path available" || echo "PAT absent — needs official MCP"
```

Nếu gate fail (disabled, hoặc không có path nào khả dụng) → **skip toàn bộ design lookup** và build từ AC của issue **khi AC tự đủ**. Note lại trong comment `[DEV]` của bạn (vd `design lookup skipped: figma not configured — built from AC only`) để reviewer biết implementation là AC-driven. **Không bao giờ block dev work chỉ để chờ một optional connection** — nhưng một màn hình mới mà AC thực sự cần một design chưa từng được cung cấp thì đó là *missing input*, không phải build chỉ-từ-AC: xem *Handoff discipline*.

## Path A — official Figma MCP server (preferred)

Official server (Dev Mode MCP của Figma) authenticate qua **OAuth** — trên path này **không có `FIGMA_TOKEN`/`FIGMA_API_KEY`/`X-Figma-Token`**. Nó expose các tool ổn định, có tài liệu; **gọi chúng bằng fully-qualified name** (đừng "discover at runtime" — tên là ổn định). Flow design-to-code cho một frame:

| Bước | Tool | Dùng cho |
|------|------|---------|
| 1. Phác thảo một design lớn | `get_metadata` | XML thưa gồm node ID / tên / type / kích thước. Gọi không kèm `nodeId` để liệt kê các top-level page của file, rồi drill vào. Rẻ — dùng để tìm đúng node trước khi pull full context. |
| 2. Pull design context | `get_design_context` | Tool design→code chính. Trả về reference code (**React + Tailwind mặc định**), một screenshot, và metadata cho node. Coi nó là *context để translate*, không phải code để paste. |
| 3. Map tokens | `get_variable_defs` | Các variable/style dùng trong selection (màu, spacing, typography), vd `{ 'color/primary': '#1A73E8' }`. Map chúng tới các token sẵn có của project. |
| 4. Visual check | `get_screenshot` | Một PNG của node để diff implementation của bạn nhằm đảm bảo độ chính xác về layout. |
| 5. Reuse component thật | `get_code_connect_map` | Trả về `{ nodeId: { componentName, source, snippet, … } }` — code component thực tế mà một Figma node map tới. **Ưu tiên component đã được map thay vì markup viết mới.** |

**Prompt các tool bằng thông tin cụ thể của project** (theo guidance "write effective prompts" của Figma): nêu framework của project, thư mục component đích, và layout system, để output khớp codebase này thay vì mặc định React+Tailwind. Vài ví dụ để lồng vào cách bạn gọi `get_design_context`:

- Framework: *"generate this selection in `<the project's framework>`"* (vd Vue, SwiftUI, HTML+CSS thuần).
- Reuse: *"using components from `<surfaces.<surface>.path>/components`"*.
- Token thay vì literal: khi bạn muốn variable thay vì code, hãy hỏi rõ ràng — *"get the variable names and values for this selection"* (nếu không agent có thể trả về code).

**Remote vs desktop:** server **remote** (`https://mcp.figma.com/mcp`) là **link-based** — truyền URL figma.com của frame/layer (hoặc `fileKey` + `nodeId` của nó); nó tự extract node-id. Prompting kiểu **selection-based** ("my current selection") chỉ hoạt động với server **desktop**. AgentFlow chạy headless, nên luôn truyền URL/node tường minh lấy từ AC, không bao giờ dùng "the selection".

**Code Connect:** nếu project đã set up Code Connect, hãy set framework label để mapping đúng trả về (truyền `clientFrameworks` khớp với Code Connect label, vd `React`, `SwiftUI`). Việc author Code Connect mapping nằm ngoài scope của DEV ở đây — chuyển sang skill `figma-code-connect` của Figma nếu project muốn thêm chúng.

## Path B — PAT / REST fallback (legacy)

<details>
<summary>Framelink server hoặc Figma REST — cho các setup headless/enterprise không thể hoàn tất OAuth flow. Dùng một PAT <code>FIGMA_TOKEN</code> riêng (khai báo độc lập dưới <code>env:</code>), KHÔNG phải official server.</summary>

Đây là một **integration riêng biệt** so với official server phía trên. Chỉ dùng nó khi official MCP path không khả dụng và `FIGMA_TOKEN` đã được set. Token đặt trong **header** `X-Figma-Token`, không bao giờ đặt trong URL.

```bash
# Whole file (structure + styles)
curl -s -H "X-Figma-Token: $FIGMA_TOKEN" \
  "https://api.figma.com/v1/files/$FILE_KEY" | jq '.document.children[].name'

# A specific frame/node (cheaper) — NODE_ID uses ':' here, not '-'
curl -s -H "X-Figma-Token: $FIGMA_TOKEN" \
  "https://api.figma.com/v1/files/$FILE_KEY/nodes?ids=$NODE_ID" | jq '.nodes'

# Rendered preview of one or more nodes (returns image URLs)
curl -s -H "X-Figma-Token: $FIGMA_TOKEN" \
  "https://api.figma.com/v1/images/$FILE_KEY?ids=$NODE_ID&format=png&scale=2"
```

Các endpoint hữu ích: `/v1/files/<FILE_KEY>` (full tree), `/v1/files/<FILE_KEY>/nodes?ids=<NODE_ID>` (một frame), `/v1/images/<FILE_KEY>?ids=<NODE_ID>` (PNG/SVG đã render). Legacy Framelink MCP server (`figma-developer-mcp`) đọc cùng `FIGMA_TOKEN` dưới dạng `FIGMA_API_KEY` và expose các tool `mcp__figma__*` — discover chúng at runtime nếu server đó là cái được wire trong `.mcp.json`.
</details>

## Parse URL

Designer paste link kiểu như:

```
https://www.figma.com/design/AbC123dEfGhIj/Checkout-Flow?node-id=1234-5678
                              └── FILE_KEY ──┘             └─ node-id ─┘
```

- **FILE_KEY** là path segment ngay sau `/design/` (link cũ dùng `/file/` — cùng vị trí). Với branch URL `…/design/<key>/branch/<branchKey>/…`, dùng **branchKey** làm file key.
- **node-id** trong URL được phân tách bằng `-` (`1234-5678`). **Official MCP tools chấp nhận cả `1234-5678` lẫn `1234:5678`**; **REST API yêu cầu `:`** (`1234:5678`). Convert cho REST fallback:

```bash
FILE_KEY="AbC123dEfGhIj"
NODE_ID="${URL_NODE_ID//-/:}"   # 1234-5678 -> 1234:5678  (only needed for Path B/REST)
```

`connections.figma.files` có thể liệt kê sẵn các file đã biết dưới dạng entry `{ name, key }`. Nếu AC gọi tên một file bằng `name`, hãy resolve `key` của nó ở đó thay vì đòi một URL. Một URL trơ không có `node-id` nghĩa là toàn bộ file/page — dùng `get_metadata` (hoặc fetch các top-level frame) và chọn cái có tên khớp với AC.

## Cần extract gì cho implementation

Biến mỗi item thành một implementation note cụ thể, rồi map các note đó ngược lại các AC item:

| Lấy từ design | Dùng cho |
|------------------|---------|
| Auto-layout direction, gap, padding, alignment | Cấu trúc flex/stack và spacing |
| Sizing (fixed / hug / fill), constraints | Hành vi width/height, responsiveness |
| Màu, fill, effect (`get_variable_defs`) | Theming — match với token sẵn có |
| Typography (family, size, weight, line-height) | Text style — match với token sẵn có |
| Tên component / layer + `get_code_connect_map` | Component sẵn có nào để reuse |
| Variable / design token | Tham chiếu token, không phải literal |

**Ưu tiên design token và component sẵn có của project thay vì giá trị hardcode.** Nếu design chỉ định `#1A73E8` và project có token `--color-primary` cùng giá trị, hãy tham chiếu token đó. Chỉ hardcode khi không có token nào, và flag lại để follow-up.

Tạo một **implementation checklist** ngắn gắn với AC, vd:

```
AC-2 (button states): default/hover/disabled fills from frame 1234:5678;
  map to existing Button component (get_code_connect_map → src/ui/Button.tsx);
  spacing 8px gap (token: space-2 via get_variable_defs).
```

## Handoff discipline

- **AC là nguồn chân lý cho CÁI GÌ; design là nguồn chân lý cho việc nó TRÔNG như thế nào.** Khi chúng khớp nhau, implement theo cả hai.
- **Khi design và AC mâu thuẫn** — frame hiển thị một field mà AC không nhắc tới, hoặc AC yêu cầu một behavior mà design bỏ qua — thì **không** âm thầm làm theo design thay vì AC. Đây là một **human-intervention case**: post một comment `[DEV→PMO ?]` với tối đa 3 câu hỏi được đánh số, swap state sang `flow:refined` (owner: human), rồi dừng — con người bổ sung thông tin qua `/review-refined` rồi đưa ticket về `flow:inbox` (xem skill: `project-board-protocol`).
- **Khi issue là một màn hình mới mà AC tham chiếu một design nhưng không có Figma nào được cung cấp** — không có URL/node trong AC và không có gì khớp trong `connections.figma.files` — thì **không** tự bịa ra visual design. Coi design bị thiếu là một **missing input** và xử lý như **cùng human-intervention case đó**: post một `[DEV→PMO ?]` với tối đa 3 câu hỏi được đánh số, swap state sang `flow:refined` (owner: human), rồi dừng — con người bổ sung design/spec qua `/review-refined` rồi đưa ticket về `flow:inbox`. Chỉ build thẳng từ AC khi AC tự đặc tả đầy đủ màn hình đó.
- Trích dẫn cụ thể frame (`FILE_KEY` + `NODE_ID`) trong comment `[DEV]` của bạn để QC và PMO có thể mở cùng một node.
- Thay đổi design sau khi issue đã ở `flow:ready-for-dev` là một thay đổi AC/scope, không phải quyết định tùy tiện của DEV — route chúng qua PMO theo cùng cách.

## Secret hygiene

Trên official OAuth path thì **không có Figma token nào cần bảo vệ**. Trên PAT fallback, `FIGMA_TOKEN` là một secret: chỉ tham chiếu nó qua `${FIGMA_TOKEN}`, giữ nó trong header `X-Figma-Token` (không bao giờ trong URL), và không bao giờ print, echo, log, hay commit nó. Full rules: skill `setup-agentflow` → *Secret hygiene*.
