# Design → code (DEV) và design → verify (QC)

Chỉ đọc file này khi ticket chạm UI **và** (`design.figma: true` hoặc `design.repo` khác rỗng hoặc issue có link Figma/ảnh thiết kế).

## Nguồn design, theo thứ tự ưu tiên

1. Link trong issue (section Thiết kế / Design): Figma URL có `node-id`, ảnh, path trong repo.
2. `design.repo`: prototype trong repo (HTML/ảnh) — pin theo commit, chắc chắn nhất.
3. Không có gì → build theo AC + design system sẵn có của repo. **Không bịa visual mới**: màn mới hoàn toàn mà không có design ⇒ `needs_info`.

## Figma (MCP chính thức `figma`, OAuth)

Parse URL: `https://www.figma.com/design/<FILE_KEY>/<name>?node-id=<A-B>` → truyền nguyên URL cho tool (server tự tách); nếu truyền `nodeId` thì đổi `-` → `:`. Branch URL `/design/<key>/branch/<branchKey>/` → dùng `branchKey`.

Gọi theo thứ tự, dừng khi đủ (mỗi call đều tốn token — đừng gọi hết cho chắc):

| Cần | Tool | Ghi chú |
|---|---|---|
| Cấu trúc frame lớn | `get_metadata` | Rẻ; dùng để chọn đúng node con trước khi lấy code |
| Spec để code | `get_design_context` | Prompt kèm framework của surface + "dùng component/token sẵn có của repo" |
| Token màu/spacing/type | `get_variable_defs` | Map sang token có sẵn; **không hardcode giá trị đã có token** |
| Ảnh để so | `get_screenshot` | QC dùng để so; DEV dùng khi layout mơ hồ |
| Component đã map | `get_code_connect_map` | Có mapping ⇒ dùng component thật thay vì viết mới |

Tool `figma` không có / chưa authenticate ⇒ build theo AC, ghi một dòng `design: không truy cập được Figma` trong comment PR + journal `kind=tool_error`; nếu AC nói rõ "theo thiết kế" thì `needs_info`.

## DEV

- Ghi **revision đã build** vào PR body: `Design: <url hoặc path> @ <ngày fetch | commit>` — Figma sửa được giữa chừng, QC verify đúng bản này.
- Design mâu thuẫn AC ⇒ AC thắng nếu rõ ràng; mơ hồ ⇒ `needs_info` hỏi PO, đừng tự chọn.
- Thiếu state (empty/loading/error) trong design ⇒ dùng pattern sẵn có của repo, ghi rõ trong PR.

## QC

- So đúng revision DEV đã ghi. Design đổi sau khi DEV build ⇒ không phải lỗi của DEV: ghi vào checklist "design đã đổi — PO xác nhận", **không** tính ❌.
- Web: mở staging bằng Claude in Chrome hoặc e2e của repo, chụp màn hình và so với `get_screenshot`: layout, spacing, màu token, chữ, đủ state. Lệch rõ ⇒ ❌ kèm ảnh/vị trí; lệch cảm quan ⇒ đưa vào checklist test tay.
- Mobile: chạy được trên emulator/simulator thì so như web. Không chạy được UI ⇒ toàn bộ phần so UI vào checklist test tay (`[AF:QC] 🧪`), kèm link frame Figma cho từng mục.
