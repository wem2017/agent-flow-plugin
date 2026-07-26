# Design artifacts — tạo và handoff

Reference của skill `design-system-rules`. Đọc file này **chỉ khi bạn thực sự sắp tạo hoặc sửa artifact**. Rules resolution và compliance checklist nằm ở `SKILL.md`; đừng đọc file này để trả lời câu hỏi "token nào được phép dùng".

Hai mode, không loại trừ nhau. Resolve mode bằng cách **nhìn**, không bằng config:

| Mode | Khả dụng khi | Deliverable | Đụng git? |
|------|--------------|-------------|-----------|
| **Folder** | `design.folder` khác `""` **và** tồn tại trên disk | File trong `design.folder/<slug>/` | **Có** — commit + push |
| **Figma** | `connections.figma` pass gate enabled + authenticated | Frame trong Figma + spec trong issue body | **Không** |

Cả hai cùng khả dụng → làm cả hai, và spec phải trỏ chéo lẫn nhau (file spec nêu Figma node, comment nêu đường dẫn file).
Không mode nào khả dụng → escalate lên Status "Refined", đừng bịa.

---

## New vs update — quyết định bằng cách đọc, không hỏi

Bạn **không** được cho biết đây là việc mới hay việc sửa. Tự xác định:

1. Slug hoá tên screen/flow từ tiêu đề issue + AC (ví dụ "Profile settings screen" → `profile-settings`).
2. Folder mode: có `design.folder/<slug>/` không? Figma mode: `get_metadata` trên file design system, có frame nào tên khớp không?
3. **Có** → đây là **update**: đọc artifact hiện có trước, rồi **sửa tại chỗ**. Tuyệt đối không tạo một artifact thứ hai song song (`profile-settings-v2`, `Profile Settings (new)`) — artifact trùng là cách chắc chắn nhất để DEV implement nhầm bản.
4. **Không** → đây là **new**.

Khi update, ghi rõ trong `[DESIGNER]` comment **cái gì đổi và vì sao**, không chỉ "đã cập nhật design".

---

## Folder mode

### Layout

```
<design.folder>/
  <slug>/
    spec.md            # BẮT BUỘC — contract cho DEV
    <screen>.html      # hoặc .jsx/.svg/.png — artifact do claude design hoặc tool khác sinh
    states/            # tuỳ chọn — biến thể tách riêng khi spec.md quá dài
```

Giữ nguyên format mà repo đang dùng. Nếu `design.folder` đã có artifact `.html` thì tạo tiếp `.html` — **đừng** đổi repo sang format bạn thích hơn.

### `spec.md` — heading bắt buộc

Script compliance check đúng các heading này, nên tên phải khớp chính xác:

```markdown
# <Screen name>

## Maps to
- Issue: #<n>
- AC: AC-1, AC-3        # AC item nào screen này phục vụ

## Layout
<structure, auto-layout direction, gap, padding, alignment — mô tả bằng token, không phải px thô>

## Tokens
| Vai trò | Token | Nguồn |
|---------|-------|-------|
| Surface background | `color/surface` | rules_file |
| Body text | `text/body-md` | figma:get_variable_defs |

## Components
| Phần tử | Component tái dùng | Đường dẫn / node |
|---------|--------------------|------------------|
| Primary CTA | `Button` variant=primary | src/ui/Button.tsx (code-connect) |

## States
default / hover / focus / active / disabled / loading / empty / error — mỗi cái một dòng, cái nào
không áp dụng thì ghi `n/a` kèm lý do. Đừng bỏ trống.

## Responsive
<hành vi theo từng breakpoint mà project thực sự có>

## Accessibility
<contrast, focus order, target size, label>

## Open questions
<cái gì chưa quyết được, hoặc "(none)">
```

### Git

Folder mode commit lên **chính feature branch mà DEV sẽ dùng** — không có branch base thứ hai, không có PR riêng:

```bash
# kind lấy từ label type/*: feature→feat, bug→fix, improvement→chore
git switch -c agent/dev/<kind>/<issue#>-<slug> origin/<default_branch>
git add <design.folder>/<slug>
bash "$CHECK" --staged        # $CHECK resolve theo snippet trong SKILL.md
git commit -m "design(<slug>): add spec and artifacts for #<issue#>"
git push -u origin agent/dev/<kind>/<issue#>-<slug>
```

- Prefix `agent/dev/` là **hằng số cố định của plugin** — nghĩa là "agent-authored", không phải "DEV-authored". Đừng đổi thành `agent/design/`; DEV dò đúng pattern này để nhận ra branch đã tồn tại.
- Branch **luôn** cắt từ `origin/<default_branch>` (skill: `git-flow-working`). Bạn chạy trước DEV nên bạn là người tạo branch; DEV sau đó switch vào chính branch này.
- **KHÔNG mở PR.** DEV mở PR sau khi có code. Một issue = một branch = một PR = một human merge.
- Branch đã tồn tại (rework, hoặc DEV đã tạo) → `git switch` vào nó và commit tiếp, đừng tạo branch mới.

---

## Figma write mode

### `figma-use` là prerequisite bắt buộc — và nó KHÔNG ship cùng AgentFlow

Mọi call `use_figma` **phải** có `Skill(figma-use)` chạy trước. Skill đó thuộc plugin Figma, không thuộc AgentFlow, nên nó **có thể không được cài**.

```
1. Kiểm tra skill `figma-use` có khả dụng không.
2. CÓ    → Skill(figma-use), rồi mới use_figma.
3. KHÔNG → TUYỆT ĐỐI không gọi use_figma mù. Degrade sang folder mode nếu folder mode khả dụng;
           nếu không → [DESIGNER→PMO ?] + Status "Refined", nêu rõ thiếu plugin Figma.
```

### Flow

1. **`search_design_system`** — tìm component + style có sẵn TRƯỚC KHI vẽ bất cứ thứ gì. Design system thắng sáng tạo tự do.
2. **`get_libraries`** — xác nhận library nào được link, để import đúng nguồn.
3. **`get_variable_defs`** — lấy giá trị token thật, bind vào property thay vì set giá trị thô.
4. **`generate_figma_design`** / **`use_figma`** — dựng frame, lắp bằng component đã import, bind variable.
5. **`get_screenshot`** — nhìn lại cái vừa dựng. Không skip bước này; sai layout thường chỉ lộ ra khi nhìn.

**Server remote là link-based.** AgentFlow chạy headless nên luôn truyền URL/`fileKey`+`nodeId` tường minh; prompt kiểu "my current selection" chỉ chạy với server desktop và sẽ im lặng làm sai ở đây.

### Handoff

Figma mode **không** ghi file nào vào repo. Spec đi vào **issue body** dưới section `## Design`, đặt ngay trước `## For DEV`:

```markdown
## Design
- Figma: <URL đầy đủ có node-id>  (FILE_KEY `<key>`, node `<id>`)
- Tokens: <bảng như trong spec.md>
- Components: <bảng như trong spec.md>
- States / Responsive / Accessibility: <như trên>
```

Upsert section này y như cách `AGENTFLOW-STATE` được upsert (skill: `project-board-protocol`): tìm heading `## Design`, có thì thay tại chỗ, không có thì chèn vào. DEV, QC và con người đều đã đọc issue body sẵn — đó là lý do spec ở đây tốt hơn một file spec rời.

---

## Design review mode (aux label `design-review`)

Chạy sau khi QC ✅ một ticket UI, khi `design.design_review: true`. Bạn đang so **UI đã build** với **artifact + rules**, không phải review lại code.

1. Checkout PR head (`gh pr checkout <m>` hoặc theo `headRefName`).
2. Chạy `check-design-compliance.sh --diff <default_branch>` → phần cơ học.
3. Đọc diff của các file UI, so với `spec.md` / section `## Design`: token có đúng không, component có tái dùng không, state nào bị bỏ, responsive/a11y có được xử lý không.
4. Verdict:
   - **✅** → `[DESIGNER] ✅` + checklist ngắn, gỡ aux `design-review` TRƯỚC, rồi Status → "Ready for Human Review" (`board.columns.ready_for_human_review`).
   - **❌** → `[DESIGNER] ❌` + list đánh số, mỗi item trích `file:line` và nêu token/component đúng phải là gì. Aux label TRƯỚC (gỡ `design-review`, add `rework`), rồi Status → "Ready for Dev" (`board.columns.ready_for_dev`); append vào `QC rejections` (ghi `— design review` ở dòng attempt) và tăng `consecutive_fail`.

**Chỉ fail trên vi phạm kiểm chứng được.** "Tôi thấy nó chưa đẹp" không phải là một finding — nếu rules không nói gì về nó thì đó là ý kiến, và ý kiến không được chặn một PR. Vi phạm hợp lệ trông như: dùng `#1A73E8` trong khi có token `color/primary`; viết markup nút mới trong khi có `Button`; thiếu disabled state mà spec yêu cầu.
