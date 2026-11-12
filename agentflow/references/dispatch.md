# Dispatch — orchestrator của `/agentflow:run` và `/agentflow:do`

Session chính là **orchestrator**: đọc board, chọn agent cho từng ticket, spawn, đọc kết quả. **Không** viết code, review, test.

## 1. Boot (một lần mỗi session)

1. `git rev-parse --show-toplevel`; `agentflow.yaml` + schema gate. Repo + base từ git (protocol §1).
2. Nạp tool MCP một lần (protocol §3), `get_me` → `my_login`. Fail → dừng: "GitHub MCP chưa connect — `/agentflow:doctor`."
3. `projects_get method=get_project` một lần. Fail → dừng, gợi `/agentflow:doctor`.
4. `agentflow-board preflight`, chạy lại ngay trước mỗi lượt spawn → `push: false` ⇒ dừng lượt, không spawn, không ghi lên ticket, báo `push_error` (mạng chặn push / credential). `missing_env` ⇒ nêu ở báo cáo cuối.

## 2. Đọc hàng đợi

```
projects_list method=list_project_items owner/owner_type/project_number từ board.url
  perPage: 50   field_names: ["Status", "Labels", <fields.priority>, <fields.size>]   (bỏ field không khai báo)
  query: is:open is:issue repo:<owner>/<repo> -label:"<labels.blocked>" -label:"<labels.needs_info>" status:"<ready>","<in_progress>","<in_review>","<in_qc>","<ready_to_merge>"
```

Paginate tới hết. Board có thể dùng chung nhiều repo, số issue trùng nhau: item có `content.repository` khác repo này → bỏ qua. Giữ cho mỗi item: `item_id`, `number`, Status, Priority, Size, labels (field `Labels`), assignees (`content.assignees`). Đủ cho bảng §3 — label không cần `issue_read`; chỉ dòng ghi `issue_read` mới đọc state.

Mỗi lượt **một lần**:
- `query: is:closed is:issue repo:<owner>/<repo> label:"<labels.agent>" -label:"<labels.blocked>" -status:"<done>"` → issue đã đóng mà card chưa `done` (merge với `Closes`, workflow board tắt) → SYS *done*; riêng khi PR `state.pr` còn mở: gắn `blocked`, `[AF:SYS] stuck`.
- Ticket `A` ở `in_review`, `in_qc`, `ready_to_merge`: **một** lệnh `agentflow-board feedback <owner/repo> --summary --issue <n> --issue <m> …` → `pending` > 0 = người còn góp ý trên PR chưa được trả lời. Lệnh lỗi ⇒ coi như 0, journal `tool_error`.

## 3. Bảng hành động

`A` = có label `labels.agent`. Ticket **không** `A` mà assign cho người khác → bỏ qua (ticket của người). Ticket `A` thì **bỏ qua assignee**.

| Status | Điều kiện | Hành động | Hạng |
|---|---|---|---|
| `ready_to_merge` | `A` — đọc state (`issue_read`) rồi `pull_request_read method=get` PR `state.pr` | PR đã merge → SYS *done* | – |
| `ready_to_merge` | `A` + PR đã đóng mà không merge | gắn `blocked`, comment `[AF:SYS] stuck — PR #<m> đã đóng mà chưa merge`, mention `people.po` | – |
| `ready_to_merge` | `A` + (`changes_requested` hoặc `pending` > 0) | SYS *feedback* → DEV `MODE=rework` | 0 |
| `ready_to_merge` | `A` + `qc_manual` (QC người đã pass, kéo card) | SYS *qc-manual-pass* | – |
| `ready_to_merge` | còn lại | chờ người merge — liệt kê ở báo cáo | – |
| `in_qc` | `A` + `qc_failed` (QC người fail) | SYS *qc-failed* → DEV `MODE=rework` | 1 |
| `in_qc` · `in_review` | `A` + `pending` > 0 | SYS *feedback* → DEV `MODE=rework` | 0 |
| `in_qc` | `A` + `qc_manual` | chờ QC người — liệt kê | – |
| `in_qc` | `A` (ticket bản cũ: chờ pipeline / QC agent) | SYS *requeue* → DEV `MODE=resume` | 3 |
| `in_review` | `A` | SA `MODE=review` | 2 |
| `in_progress` | `A` + (`changes_requested` hoặc `qc_failed`) | DEV `MODE=rework` | 3 |
| `in_progress` | `A`, không trong in-flight của session | DEV `MODE=resume` | 3 |
| `ready` | `A` + `qc_failed` (QC người trả về) | DEV `MODE=rework` | 3 |
| `ready` | `A` + state thiếu `design` (`issue_read`) | SA `MODE=design` | 4 |
| `ready` | `A` | DEV `MODE=new` | 4 |
| `ready` | không `A`, không assign người khác | SA `MODE=design` | 5 |

**SYS transition** — orchestrator tự làm theo thứ tự ghi protocol §6. Những cái dẫn tới DEV (*feedback*, *qc-failed*, *requeue*) chỉ chạy khi **sẽ spawn DEV ngay trong cùng bước** (không chạy dưới `--only sa`, không chạy khi đã chạm trần):
- *done*: Status → `done`, comment `[AF:SYS] done`, gỡ `qc_manual`; xoá worktree (§7).
- *feedback*: state `stage: in_progress`, `next: DEV xử lý góp ý trên PR #<m>`; comment `[AF:SYS] feedback`; gắn `changes_requested`, gỡ `qc_manual`; `update_pull_request draft=true` nếu PR chưa draft; Status → `in_progress`. Không tăng round.
- *qc-manual-pass*: state `stage: ready_to_merge`, `review_round: 0`, `qc_round: 0`; comment `[AF:SYS] qc-manual-pass`; `update_pull_request draft=false` rồi mới gỡ `qc_manual`, `qc_failed` (lỗi giữa chừng còn chạy lại được). Không spawn.
- *qc-failed*: `qc_round += 1`, trừ khi state đã `stage: ready` (chạy lại sau crash) (vượt `max_qc_rounds` → escalate theo protocol §7 và không spawn DEV); comment `[AF:SYS] qc-failed`; gỡ `qc_manual`, giữ `qc_failed`; state `stage: ready`; Status → `ready`.
- *requeue*: state `stage: in_progress`, `next: DEV deploy + chạy flow trên staging`; comment `[AF:SYS] requeue`; gỡ label cũ `deploying` nếu có; Status → `in_progress`.

## 4. Thứ tự và model

Sắp theo **hạng** tăng dần, rồi vị trí option Priority (option đầu = cao nhất; không có = cuối), rồi số issue tăng dần.

Model: DEV = `run.models.dev[<Size>]` nếu có, không thì `run.models.dev.default`; SA = `run.models.sa` (config cũ: `run.models.reviewer`; mặc định opus).

## 5. Spawn

```
Agent(subagent_type="agentflow:<sa|dev>", model=<model>,
      prompt="REPO: <owner/repo>\nISSUE: #<n>\nITEM_ID: <item_id>\nSTAGE: <stage key, vd in_review, sau SYS transition>\nMODE: <mode của bảng §3>\nSIZE: <Size, chỉ DEV, nếu có>")
```

- Song song: tối đa `run.parallel` ticket **khác nhau** trong **một** message. Một ticket không bao giờ có 2 agent cùng lúc. Mỗi ticket một worktree (protocol §8).
- Prompt chỉ gồm các dòng trên.
- Lượt DEV dài (tự chờ pipeline, chạy flow) là bình thường: đừng spawn lại hay gửi tin khi chưa có thông báo xong.

## 6. Sau mỗi kết quả

1. Đọc khối `RESULT` (bỏ qua narrative). Đọc lại Status bằng `get_project_item` (`field_names: ["Status"]`) — **Status là sự thật**. Không có `RESULT`: thông báo nói agent còn chạy nền ⇒ chờ thông báo kế. Đã dừng hẳn (`maxTurns`, chết giữa chừng) ⇒ `SendMessage` (ToolSearch) cho chính agent đó **một lần** "làm nốt, kết thúc bằng khối RESULT" (tính một spawn); vẫn không có ⇒ gắn `blocked`, comment `[AF:SYS] stuck — <agent> dừng không có RESULT, ticket ở <stage>`, journal `tool_error`, dừng ticket.
2. RESULT ≠ `ok` (`waiting_human`, `needs_info`, `blocked`, `escalated`, `abort`) → **dừng ticket**, đếm là 1 ticket xong.
3. RESULT `ok` + tới `ready_to_merge` → dừng ticket, đếm 1.
4. RESULT `ok` + stage mới do agent sở hữu → **đi tiếp ngay ticket đó** ở lượt spawn kế (chain SA design → DEV → SA review; SA ❌ → DEV `MODE=rework` → SA …). Ticket ở `ready`: đọc state rồi chọn dòng §3.
5. **No-progress guard** (chỉ khi RESULT `ok`): Status không đổi → không spawn lại (SA design giữ `ready` là đúng; thay vào đó: sau SA design state phải có `design` và ticket mang `labels.agent`): gắn `blocked`, comment `[AF:SYS] stuck — <agent> báo ok nhưng ticket vẫn ở <stage>`, journal `tool_error`, dừng ticket.
6. Trần mỗi ticket: `(run.max_qc_rounds + 1) × (2 × run.max_review_rounds + 2) + 2` lần spawn — chạm trần → gắn `blocked` + `[AF:SYS] stuck`, dừng ticket.
7. Trong context chỉ giữ bảng ngắn `#n · stage · kết quả`.

## 7. Dừng lượt

- Hết hành động, **hoặc** số ticket xong ≥ giới hạn (`/run`: `run.max_tasks`; `/do`: 1), **hoặc** người nói dừng. Chỉ dừng **giữa** hai spawn.
- Dọn worktree: `git worktree list` → mỗi `.claude/worktrees/af-<n>` mà issue đã đóng hoặc ticket đã `done`, và `git -C <wt> status --porcelain` rỗng → `git worktree remove <wt>`. `af-<n>-staging` (và `af-<n>-qc` của bản cũ) còn sót khi không có agent đang chạy trên ticket → `git worktree remove --force <wt>`.

## 8. Báo cáo cuối lượt (≤ 15 dòng)

```
AgentFlow <repo> — xong <k> ticket, <s> lần spawn
#42 ready_to_merge  PR #57 — chờ @<reviewer> merge
#43 in_qc           PR #58 — chờ @<qc> test 2 mục QC tay
#44 in_progress     blocked — 2 lỗi block sau 3 vòng sửa, xem issue
Chờ người: …  ·  Còn trong hàng đợi: <m>  ·  Gợi ý: /agentflow:status --metrics, /agentflow:learn
```

Không bao giờ hỏi người giữa lượt. Việc cần người nằm trên GitHub (comment + label + mention) và trong báo cáo.
