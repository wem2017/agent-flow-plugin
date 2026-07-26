---
name: design-system-rules
description: Resolve design system rules của project từ ba nguồn theo thứ tự ưu tiên cố định (rules file trong repo → Figma library qua MCP → suy ra từ codebase), rồi áp chúng như ràng buộc cứng khi tạo design artifact hoặc build UI — kèm compliance checklist và script check-design-compliance.sh. Dùng khi DESIGNER tạo/cập nhật design, khi DEV implement UI trên một surface có ui:true, hoặc khi review UI xem có lệch design system không.
---

# Design System Rules

Skill này trả lời đúng một câu hỏi: **"giá trị / component nào được phép dùng, và ai nói vậy?"** Nó là lớp ràng buộc mà DESIGNER luôn tuân theo, DEV tuân theo khi build UI, và design review đối chiếu vào.

Việc **tạo ra** artifact (file trong design folder, frame Figma, format spec) nằm ở reference đi kèm — đọc nó chỉ khi bạn thực sự sắp tạo artifact:

> **`reference/design-artifacts.md`** — folder convention, format spec, và Figma write mode.

## Gate trước khi dùng

Đọc `.claude/agentflow.yaml` trước (skill: `setup-agentflow` cho full spec về gate):

```bash
yq '.design.enabled' .claude/agentflow.yaml        # → true
yq '.design.folder' .claude/agentflow.yaml         # "" = figma-only
yq '.design.rules_file' .claude/agentflow.yaml
yq '.surfaces | to_entries | map(select(.value.ui == true) | .key)' .claude/agentflow.yaml
```

Nếu `design.enabled: false`, hoặc issue không mang `component/*` của surface nào có `ui: true` → **skill này không áp dụng**, skip. Nếu `enabled: true` nhưng **không nguồn nào trong ba nguồn dưới reachable** → đừng bịa ra một design system: escalate lên Status "Refined" kèm `[DESIGNER→PMO ?]` (skill: `project-board-protocol`).

## Ba nguồn, thứ tự ưu tiên cố định

Thứ tự này là **cố định và không thương lượng**. Nếu bạn resolve theo thứ tự khác, hai lần chạy trên cùng một ticket sẽ ra hai kết quả khác nhau.

**1. `design.rules_file` trong repo — authoritative, thắng mọi conflict.**
Con người viết ra nó, nên nó thắng cả Figma lẫn code. Đọc toàn bộ file trước khi làm bất cứ việc gì. Nếu nó nói "spacing scale là 4/8/12/16/24/32" thì đó là scale, kể cả khi Figma còn giá trị khác và code còn giá trị khác.

**2. Figma library qua MCP — authoritative cho giá trị token + inventory component, ở chỗ (1) im lặng.**
Chỉ dùng khi `connections.figma` pass gate (enabled + authenticated). Gọi bằng fully-qualified tool name:

| Cần gì | Tool |
|--------|------|
| Component/style nào tồn tại trong design system | `search_design_system` |
| Library nào đang được link vào file | `get_libraries` |
| Giá trị variable/token của một selection | `get_variable_defs` |
| Code component thật mà một Figma node map tới | `get_code_connect_map` |

**3. Suy ra từ codebase — authoritative cho "cái gì thực sự tồn tại trong code", và là tiebreaker về naming.**
Nguồn này **không bao giờ tạo ra rule mới** — nó chỉ báo cáo cái đang có. Quét trong `surfaces.<s>.path` của các surface `ui: true`:

- token/theme config — `tailwind.config.*`, `theme.*`, `tokens.*`, `*.css` có `--*` custom property, `Theme.kt`, `*.xcassets`
- thư mục component dùng chung — `components/ui/`, `design-system/`, `shared/`
- cái gì đang được dùng nhiều nhất trong code hiện tại (naming thắng theo số đông, không theo cái bạn thích)

### Khi các nguồn mâu thuẫn

| Tình huống | Xử lý |
|---|---|
| (1) nói A, (3) nói B | Theo (1). Ghi lệch vào `[DESIGNER]` comment như một follow-up cần dọn trong code. |
| (1) im lặng, (2) nói A, (3) nói B | Theo (2) cho **giá trị**, theo (3) cho **tên**. |
| (1) nói A, (2) nói B | **Không phải việc của bạn.** `[DESIGNER→PMO ?]` → Status "Refined". Rules file và design library lệch nhau là một quyết định của con người. |
| Cả ba im lặng về một quyết định cụ thể | **Không tự chế giá trị.** Ghi vào `Open questions` và hỏi qua clarification flow. |

## Compliance checklist (chạy TRƯỚC mọi handoff)

Không có checklist nào trong đây là tuỳ chọn. Chạy hết, rồi mới post comment và swap label.

- [ ] Đã đọc `design.rules_file` **toàn bộ**, không phải skim.
- [ ] Mọi màu / spacing / typography trong output tham chiếu **token có tên**, không phải literal thô. Nếu buộc phải hardcode vì không có token nào → flag nó trong comment, đừng giấu.
- [ ] Mọi component tái dùng được đều map tới một component **đã tồn tại** (Figma component hoặc component trong code), không phải markup viết mới song song. Dùng `get_code_connect_map` / quét thư mục component để xác nhận.
- [ ] Mọi state được đặc tả, không chỉ happy path: default / hover / focus / active / disabled / loading / empty / error.
- [ ] Responsive behavior được nêu cho từng breakpoint mà project thực sự có.
- [ ] Accessibility tối thiểu: contrast ratio đạt, focus visible, target size đủ lớn, thứ tự heading hợp lý.
- [ ] Mỗi AC item có UI chạm tới đều map được sang một phần cụ thể của artifact.
- [ ] `scripts/check-design-compliance.sh` exit 0.

## Script

**Resolve đường dẫn script trước** — `CLAUDE_PLUGIN_ROOT` có thể không được export vào shell của bạn, và một gate bị skip vì không tìm thấy file thì tệ hơn là không có gate:

```bash
CHECK=""
for c in "${CLAUDE_PLUGIN_ROOT:-}/skills/design-system-rules/scripts/check-design-compliance.sh" \
         "$HOME/.claude/plugins/agentflow/skills/design-system-rules/scripts/check-design-compliance.sh"; do
  [ -f "$c" ] && CHECK="$c" && break
done
# vẫn chưa thấy → tìm một lần rồi nhớ kết quả cho cả run
[ -z "$CHECK" ] && CHECK="$(find "$HOME/.claude" -name check-design-compliance.sh -type f 2>/dev/null | head -1)"

bash "$CHECK" [--staged|--diff <base>]
```

Nếu vẫn không resolve được → **đừng âm thầm bỏ qua**. Chạy tay bốn check trong đầu (chúng liệt kê ngay dưới đây), và ghi vào comment `[DESIGNER]` rằng script không chạy được, để reviewer biết phần cơ học chưa được verify bằng máy.

Exit `0` = pass, `1` = có vi phạm. Output là một list đánh số **đúng format** mà comment `[DESIGNER] ❌` cần, nên bạn paste thẳng được vào comment và nó rơi đúng vào rework loop có sẵn.

Nó check bốn thứ: (1) diff scope — mọi file staged nằm trong `design.folder` hoặc là `design.rules_file`; (2) raw-literal scan — hex color / `px` thô / font stack thô trong file UI mà không nằm trong token allowlist; (3) artifact completeness — mỗi screen có `spec.md` đủ heading; (4) rules file tồn tại và parse được.

**Nói thẳng về giới hạn:** script **không** check được visual fidelity, hierarchy, cân đối, hay design có tốt hay không. Những cái đó vẫn là judgment của bạn và của con người. Script chỉ biến phần cơ học của "tuân thủ design system" thành một gate thật — đừng coi exit 0 là bằng chứng design đã ổn.

## Áp cho từng role

- **DESIGNER** — load luôn, mọi lần chạy. Là ràng buộc khi tạo artifact, và là tiêu chí khi design review.
- **DEV** — load khi một touched surface có `ui: true`. Dùng token/component mà artifact + rules chỉ định; **không** tự chọn giá trị khác vì "trông cũng được".
- **QC** — load khi `design.design_review: true`, để hiểu vì sao một `[DESIGNER] ❌` là fail thật chứ không phải ý kiến thẩm mỹ.
