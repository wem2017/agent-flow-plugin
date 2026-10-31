# Dispatch — orchestrator của `/agentflow:run` và `/agentflow:do`

Session chính là **orchestrator**: đọc board, chọn agent cho từng ticket, spawn, đọc kết quả. **Không** viết code, review, test. Đọc `protocol.md` trước file này.

## 1. Boot (một lần mỗi session)

1. `git rev-parse --show-toplevel`; `agentflow.yaml` + schema gate. Repo + base từ git (protocol §1).
2. Nạp tool MCP một lần (protocol §3), `get_me` → `my_login`. Fail → dừng: "GitHub MCP chưa connect — `/agentflow:doctor`."
3. `projects_get method=get_project` một lần. Fail → dừng, gợi `/agentflow:doctor`.

## 2. Đọc hàng đợi

```
projects_list method=list_project_items owner/owner_type/project_number từ board.url
  perPage: 50   field_names: ["Status", "Labels", <fields.priority>, <fields.size>]   (bỏ field không khai báo)
  query: is:open is:issue repo:<owner>/<repo> -label:"<labels.blocked>" -label:"<labels.needs_info>" status:"<ready>","<in_progress>","<in_review>","<in_qc>","<ready_to_merge>"
```

Paginate tới hết. Board có thể dùng chung nhiều repo, số issue trùng nhau: item có `content.repository` khác repo này → bỏ qua. Giữ cho mỗi item: `item_id`, `number`, Status, Priority, Size, labels (field `Labels`), assignees (`content.assignees`). Đủ cho bảng §3 — **không** `issue_read` từng ticket để xem label.

Mỗi lượt **một lần**:
- `query: is:closed is:issue repo:<owner>/<repo> label:"<labels.agent>" -label:"<labels.blocked>" -status:"<done>"` → issue đã đóng mà card chưa `done` (merge với `Closes`, workflow board tắt) → SYS *done*; riêng khi PR `state.pr` còn mở: gắn `blocked`, `[AF:SYS] stuck`.
- Có ticket `A` ở `ready_to_merge`: `search_pull_requests` query `repo:<owner>/<repo> is:pr review:changes_requested` → tập PR có người yêu cầu sửa.

## 3. Bảng hành động

`A` = có label `labels.agent`. Ticket **không** `A` mà assign cho người khác → bỏ qua (ticket của người). Ticket `A` thì **bỏ qua assignee** (QC/reviewer người hay tự assign để làm việc của họ).

| Status | Điều kiện | Hành động | Hạng |
|---|---|---|---|
| `ready_to_merge` | `A` — đọc state (`issue_read`) rồi `pull_request_read method=get` PR `state.pr` | PR đã merge → SYS *done* | – |
| `ready_to_merge` | `A` + PR đã đóng mà không merge | gắn `blocked`, comment `[AF:SYS] stuck — PR #<m> đã đóng mà chưa merge`, mention `people.po` | – |
| `ready_to_merge` | `A` + (`changes_requested`, hoặc PR thuộc tập changes_requested **và** `get_reviews` có review CHANGES_REQUESTED `submitted_at` > `state.fb`) | SYS *feedback* → DEV `MODE=rework` | 0 |
| `ready_to_merge` | `A` + `qc_manual` (QC người đã pass, kéo card) | SYS *qc-manual-pass* | – |
| `ready_to_merge` | còn lại | chờ người merge — liệt kê ở báo cáo | – |
| `in_qc` | `A` + `qc_manual` + `qc_failed` | SYS *qc-failed* → DEV `MODE=rework` | 1 |
| `in_qc` | `A` + `qc_manual` | chờ QC người — liệt kê | – |
| `in_qc` | `A` + `deploying` | kiểm pipeline (§3b) | 1 |
| `in_qc` | `A` | QC | 1 |
| `in_review` | `A` | REVIEWER | 2 |
| `in_progress` | `A` + (`changes_requested` hoặc `qc_failed`) | DEV `MODE=rework` | 3 |
| `in_progress` | `A`, không trong in-flight của session | DEV `MODE=resume` | 3 |
| `ready` | `A` + `qc_failed` (QC trả về) | DEV `MODE=rework` | 3 |
| `ready` | không assign người khác | DEV `MODE=new` | 4 |

**SYS transition** — orchestrator tự làm theo thứ tự ghi protocol §6. Hai cái dẫn tới DEV (*feedback*, *qc-failed*) chỉ chạy khi **sẽ spawn DEV ngay trong cùng bước** (không chạy dưới `--only review|qc`, không chạy khi đã chạm trần). §3b chỉ chạy khi QC được spawn (bỏ qua dưới `--only dev|review`):
- *done*: Status → `done`, comment `[AF:SYS] done`, gỡ `qc_manual`; xoá worktree (§7).
- *feedback*: state `stage: in_progress`, `fb: <submitted_at mới nhất>`, `next: DEV sửa theo feedback trên PR #<m>`; comment `[AF:SYS] feedback`; gắn `changes_requested`, gỡ `qc_manual`; `update_pull_request draft=true` (chưa qua QC thì chưa merge được); Status → `in_progress`. Không tăng round.
- *qc-manual-pass*: state `stage: ready_to_merge`, `review_round: 0`, `qc_round: 0`; comment `[AF:SYS] qc-manual-pass`; `update_pull_request draft=false` rồi mới gỡ `qc_manual`, `qc_failed` (lỗi giữa chừng còn chạy lại được). Không spawn.
- *qc-failed*: `qc_round += 1` (vượt `max_qc_rounds` → escalate theo protocol §7 và không spawn DEV); comment `[AF:SYS] qc-failed`; gỡ `qc_manual`, giữ `qc_failed`; state `stage: ready`; Status → `ready`.

## 3b. Kiểm pipeline staging

Ticket `in_qc` + `deploying`: `issue_read` lấy `deploy_sha`, `deploy_at` rồi chạy (rẻ, không qua MCP):

```bash
agentflow-board checks <owner/repo> --branch <staging.branch> --contains <deploy_sha> --since <deploy_at>
# → {"state":"success|failure|pending","sha":"<head staging>","contains":true,"failed":[{"name","url"}]}
```

Luôn xét **head** của staging: merge dồn nên head chứa `deploy_sha` là đủ.

| Kết quả | Hành động |
|---|---|
| `contains: false` | Người đã reset staging. SYS *redeploy*: gỡ `deploying`, state `stage: in_review`, `next: Deploy lại lên staging`, comment `[AF:SYS] redeploy — staging không còn chứa <deploy_sha>`, Status → `in_review` (verdict ✅ còn đó nên REVIEWER đi thẳng tới bước deploy) |
| `success` | SYS *pipeline-ok*: gỡ `deploying`, comment `[AF:SYS] pipeline-ok @<sha>`, state `next: QC test trên staging`, rồi spawn QC |
| `failure` | Spawn QC, thêm vào prompt `PIPELINE: failed <sha> <name + url của các check fail>` (QC phân loại) |
| `pending`, chưa quá `staging.timeout_min` từ `deploy_at` | Không spawn: ticket vào danh sách đang build |
| `pending`, đã quá | SYS *pipeline-timeout*: state `deploy_at: <bây giờ>` (bỏ `blocked` là tính lại từ đầu), gắn `blocked`, comment `[AF:SYS] pipeline-timeout` + `sha`, mention `people.po`, `agentflow-notify blocked …` (head không có check nào cũng rơi vào đây) |

Không còn gì để spawn mà danh sách đang build chưa rỗng: chạy lệnh trên kèm `--wait <số phút còn lại>` cho ticket sớm hết hạn nhất, **dạng lệnh nền** (`run_in_background`), chờ thông báo; không `sleep`, không poll bằng model. Ticket đang build **không** đếm vào số ticket xong.

## 4. Thứ tự và model

Sắp theo **hạng** tăng dần, rồi vị trí option Priority (option đầu = cao nhất; không có = cuối), rồi số issue tăng dần.

Model: DEV = `run.models.dev[<Size>]` nếu có, không thì `run.models.dev.default`; REVIEWER = `run.models.reviewer` (mặc định opus); QC = `run.models.qc`.

## 5. Spawn

```
Agent(subagent_type="agentflow:<dev|reviewer|qc>", model=<model>,
      prompt="REPO: <owner/repo>\nISSUE: #<n>\nITEM_ID: <item_id>\nSTAGE: <stage key, vd in_qc, sau SYS transition>\nMODE: <mode, chỉ DEV>\nSIZE: <Size, chỉ DEV, nếu có>\nPIPELINE: <chỉ QC, khi pipeline fail>")
```

- Song song: tối đa `run.parallel` ticket **khác nhau** trong **một** message. Một ticket không bao giờ có 2 agent cùng lúc. Mỗi ticket một worktree (protocol §8).
- Prompt chỉ gồm các dòng trên.

## 6. Sau mỗi kết quả

1. Đọc khối `RESULT` (bỏ qua narrative). Đọc lại Status bằng `get_project_item` (`field_names: ["Status"]`) — **Status là sự thật**. Không có `RESULT` (agent chạm `maxTurns` hoặc chết giữa chừng) ⇒ gắn `blocked`, comment `[AF:SYS] stuck — <agent> dừng không có RESULT, ticket ở <stage>`, journal `tool_error`, dừng ticket.
2. RESULT ≠ `ok` (`waiting_human`, `needs_info`, `blocked`, `escalated`, `abort`) → **dừng ticket**, đếm là 1 ticket xong.
3. RESULT `ok` + tới `ready_to_merge` → dừng ticket, đếm 1.
4. RESULT `ok` + stage mới do agent sở hữu → **đi tiếp ngay ticket đó** ở lượt spawn kế (chain DEV → REVIEWER → pipeline → QC; QC ❌ → DEV `MODE=rework` → REVIEWER …). REVIEWER xong ⇒ §3b, không spawn QC ngay.
5. **No-progress guard** (chỉ khi RESULT `ok`): Status không đổi → không spawn lại: gắn `blocked`, comment `[AF:SYS] stuck — <agent> báo ok nhưng ticket vẫn ở <stage>`, journal `tool_error`, dừng ticket.
6. Trần mỗi ticket: `(run.max_qc_rounds + 1) × (2 × run.max_review_rounds + 3)` lần spawn — chạm trần → gắn `blocked` + `[AF:SYS] stuck`, dừng ticket.
7. Trong context chỉ giữ bảng ngắn `#n · stage · kết quả`.

## 7. Dừng lượt

- Hết hành động **và** không còn ticket đang build (§3b), **hoặc** số ticket xong ≥ giới hạn (`/run`: `run.max_tasks`; `/do`: 1), **hoặc** người nói dừng. Chỉ dừng **giữa** hai spawn.
- Dọn worktree: `git worktree list` → mỗi `.claude/worktrees/af-<n>` mà issue đã đóng hoặc ticket đã `done`, và `git -C <wt> status --porcelain` rỗng → `git worktree remove <wt>`. `af-<n>-staging`, `af-<n>-qc` còn sót khi không có agent đang chạy trên ticket → `git worktree remove --force <wt>`.

## 8. Báo cáo cuối lượt (≤ 15 dòng)

```
AgentFlow <repo> — xong <k> ticket, <s> lần spawn
#42 ready_to_merge  PR #57 — chờ @reviewer merge
#43 in_qc           🧪 checklist — chờ @qc test tay
#44 ready           needs_info — PO trả lời câu hỏi rồi bỏ label
Chờ người: …  ·  Còn trong hàng đợi: <m>  ·  Gợi ý: /agentflow:status --metrics, /agentflow:learn
```

Không bao giờ hỏi người giữa lượt. Việc cần người nằm trên GitHub (comment + label + mention) và trong báo cáo.
