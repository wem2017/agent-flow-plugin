# Init — board, label, template, smoke test

## Link board có sẵn

```bash
agentflow-board inspect <url>        # fields + option + số card open theo cột
```

Map 7 stage vào option Status — đề xuất theo tên, người chốt:

| Stage | Tên thường gặp |
|---|---|
| `backlog` | Backlog, Inbox, Todo, New, Triage |
| `ready` | Ready, Ready for Dev, To Do, Selected |
| `in_progress` | In Progress, Doing, Dev |
| `in_review` | In Review, Code Review, Review |
| `in_qc` | In QC, QA, Testing, In Test |
| `ready_to_merge` | Ready to Merge, Approved, Ready for Review (khi nghĩa là chờ merge) |
| `done` | Done, Closed, Released |

Thiếu stage hoặc thứ tự sai → xem trước, người duyệt, rồi mới ghi:

```bash
agentflow-board status-plan <url> --want "Backlog,Ready,In Progress,In Review,In QC,Ready to Merge,Done" [--rename "Cũ=Mới"] [--describe]
agentflow-board status-apply <url> --want "…" [--rename "Cũ=Mới"] [--describe] --yes
```

- Truyền kèm id option sẵn có ⇒ đổi tên/đổi thứ tự/thêm **không làm mất Status của card**.
- Option thừa (không map) được giữ ở cuối — card ở đó vô hình với agent; đề nghị người chuyển card rồi chạy lại với `--drop-extra`. Xoá option còn card cần `--allow-drop` — chỉ dùng khi người đồng ý tường minh.
- Option cũ mang nghĩa của luồng khác (vd `Ready for QC` = "đã merge master, chờ QC") → đề nghị `--rename "Ready for QC=Ready to Merge"` (cùng vị trí ý nghĩa "chờ người") và `--describe` để mô tả cột khớp luồng mới.

Field tuỳ chọn thiếu:

```bash
agentflow-board ensure-field <url> --name Priority --options P0,P1,P2,P3
agentflow-board ensure-field <url> --name Size --options XS,S,M,L,XL
agentflow-board ensure-field <url> --name Platform --options <platform của từng surface>
```

Không muốn field nào → xoá key tương ứng trong `board.fields`.

## Tạo board mới (preset)

```bash
agentflow-board create --owner <owner> --owner-type <org|user> --title "<Tên dự án>" --repo <owner/repo> \
  --want "Backlog,Ready,In Progress,In Review,In QC,Ready to Merge,Done" \
  --field "Priority=P0,P1,P2,P3" --field "Size=XS,S,M,L,XL" --field "Platform=<a,b,…>" \
  [--sprint 14] --description "<mô tả ngắn>" --readme <file README đã điền>
```

README: copy `${CLAUDE_PLUGIN_ROOT}/templates/board-readme.md`, thay `{{…}}` (tên cột theo `board.status`, người, lệnh), ghi vào scratchpad rồi truyền `--readme`. Board có sẵn mà người muốn đổi README → hiển thị bản nháp, người tự dán vào board (Settings → README) — script không ghi đè README của board có sẵn.

Sau khi tạo: Settings → Workflows của board — bật **Item closed → Status: Done** và **Item added → Status: Backlog** (chỉ làm được trên UI).

## Label

| Key | Tên mặc định | Màu | Mô tả |
|---|---|---|---|
| `agent` | agentflow | 1D76DB | AgentFlow: ticket do agent xử lý |
| `blocked` | blocked | B60205 | Bị chặn — lý do và người gỡ ở comment; gỡ label khi xong |
| `needs_info` | needs-info | D93F0B | Thiếu thông tin — PO/người báo trả lời rồi gỡ label |
| `changes_requested` | changes-requested | FBCA04 | Review/người yêu cầu sửa — DEV agent xử lý |
| `qc_failed` | qc-failed | E99695 | QC trả về — DEV xem comment kết quả test |
| `qc_manual` | qc-manual | C5DEF5 | Chờ QC người test tay theo checklist |
| `deploying` | deploying | BFDADC | Đã merge lên staging — chờ pipeline xong mới QC |

Repo đã có label cùng ý nghĩa khác tên → dùng tên sẵn có trong `labels` (không tạo trùng). Mô tả tối đa 100 ký tự (GitHub từ chối).

`classify: label` → tạo thêm một label cho mỗi key trong `types` (màu 0E8A16).

## Template

Chỉ scaffold khi repo **chưa có** — có rồi thì giữ nguyên:

- `.github/ISSUE_TEMPLATE/` ← `${CLAUDE_PLUGIN_ROOT}/templates/ISSUE_TEMPLATE/*.yml`. Thay `{{PROJECT}}` = `<owner>/<number>` của board (form tự thêm issue vào board), `{{PLATFORMS}}` = danh sách platform. `classify: label` → đổi dòng `type:` thành `labels: [<tên type>]`.
- `.github/pull_request_template.md` ← `${CLAUDE_PLUGIN_ROOT}/templates/pull_request_template.md`, thay `{{LINK}}` = `git.link`.

Ghi file vào working tree (người tự commit) — init không commit, không push.

## Smoke test — bảng lỗi

| Triệu chứng | Nguyên nhân | Sửa |
|---|---|---|
| Không có tool `projects_write` | Token thiếu scope `project`, hoặc MCP chưa connect | Thêm scope (value không đổi, khỏi sửa file); `/mcp` → `plugin:agentflow:github` → Reconnect |
| `option_not_found` | Tên trong `board.status` lệch option trên board | Sửa yaml hoặc board cho khớp từng ký tự, chạy `agentflow-board doctor` |
| Status đọc lại rỗng | Quên `field_names:["Status"]` | Luôn truyền `field_names` |
| 404 board | Sai `board.url` hoặc thiếu `read:org` | Dán lại URL từ trình duyệt; thêm scope |
| HTTP 400 `Authorization header is badly formatted` | Helper không tìm thấy token ở đâu cả | `agentflow-settings set-secret GITHUB_TOKEN`, rồi `/mcp` → Reconnect |
