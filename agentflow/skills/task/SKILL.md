---
name: task
description: Tạo issue mới từ mô tả (hỏi đáp để chốt tiêu chí nghiệm thu, viết theo issue form của repo, đặt type/Priority/Size/Platform gợi ý) vào cột Backlog — hoặc hoàn thiện spec cho một issue đang ở Backlog (#n). Không bao giờ chuyển sang Ready; đó là quyết định của PO.
argument-hint: "<mô tả công việc> | #<số issue>"
disable-model-invocation: true
---

Bạn là người cầm bút, người dùng là PO. Hỏi đáp **ngay trong session** để chốt spec. Đọc `${CLAUDE_PLUGIN_ROOT}/references/protocol.md` §1–§6 (config, stage, board call, comment, thứ tự ghi).

## 1. Context (đọc ít)

- `agentflow.yaml`; `get_me`.
- Issue form của repo: `.github/ISSUE_TEMPLATE/*.yml` — chọn form theo type. Không có form → dùng khung ở §3.
- `CLAUDE.md` ở root (chỉ để AC không mâu thuẫn luật repo). **Không** đọc source code để viết AC.
- `#<n>`: `issue_read method=get` + comment; assert issue đang ở `backlog` (stage khác → dừng: "ticket đã vào pipeline — dùng `/agentflow:do #<n>`").

## 2. Hỏi đáp

- Chọn **một** type theo `types`: sai so với AC/thiết kế đã chốt → Bug · năng lực mới → Feature · làm tốt hơn cái đang chạy đúng → Improvement · việc kỹ thuật không đổi hành vi người dùng thấy → Task.
- Hỏi gọn, mỗi lượt ≤ 3 câu, câu nào cũng kèm phương án mặc định ("Tôi giới hạn ở Web, không đụng Mobile — đúng không?"). Ưu tiên câu hỏi làm đổi AC.
- Người mô tả bằng giải pháp → hỏi ngược về hành vi người dùng thấy; giải pháp ghi vào mục ghi chú kỹ thuật như gợi ý, không thành AC.
- Bug cần: bước tái hiện, mong đợi vs thực tế, môi trường/phiên bản, mức độ. Không tái hiện được và không có bằng chứng → ghi rõ, gắn `needs_info`.
- Ticket quá lớn (Size L trở lên, > 7 AC) → đề xuất tách thành nhiều issue; người đồng ý thì tạo từng cái.

## 3. Soạn

Theo đúng thứ tự section của issue form (heading `### <label của field>`). Không có form thì:

```
### Vấn đề và mục tiêu        (Feature/Improvement)  |  ### Các bước tái hiện / Kết quả mong đợi / Kết quả thực tế / Môi trường  (Bug)
### Tiêu chí nghiệm thu
- [ ] Khi <bối cảnh + hành động>, thì <kết quả người dùng/hệ thống ngoài quan sát được>
- [ ] … (3–7 dòng, ít nhất một dòng cho đường lỗi)
### Ngoài phạm vi
### Thiết kế                  (link Figma có node-id / ảnh / path — nếu có UI)
### Hướng dẫn cho QC          (cần test gì, ở đâu; mục nào cần test tay trên thiết bị)
```

Luật AC: mỗi dòng **một** hành vi kiểm được, không mô tả cách hiện thực (không tên file/hàm/thư viện). Tiêu đề: `<động từ> <đối tượng> <ngữ cảnh>`, không nhét `[Type]` vào tiêu đề.

**Trình bản nháp** (tiêu đề + body + type + Priority/Size/Platform gợi ý) → chờ người duyệt hoặc sửa. Chưa duyệt chưa ghi.

## 4. Ghi

1. Mode mới: `issue_write method=create` (title, body, type = issue type nếu `classify: issue-type`, không thì label tên type). Mode `#n`: đọc lại body ngay trước khi ghi, khác bản đã đọc → không ghi đè, báo người.
2. `add_project_item` → `update_project_item` Status = `board.status.backlog` (explicit — không dựa vào workflow của board); rồi Priority / Size / Platform (`updated_field={name: <fields.*>, value: <option>}`) nếu người đã chốt.
3. Comment `[AF:SPEC] created` (hoặc `[AF:SPEC] refined`) một dòng: type · size · priority.
4. Board write fail → **không nuốt lỗi**: báo issue `#n` đã tạo + lỗi + `/agentflow:doctor`.

## 5. Báo cáo — một dòng

`#<n> <tiêu đề> → Backlog (type · size · priority). PO kéo sang <board.status.ready> khi duyệt; sau đó /agentflow:do #<n> hoặc /agentflow:run.`

**Không bao giờ**: chuyển ra khỏi `backlog`, viết code, tạo branch, gắn `labels.agent`.
