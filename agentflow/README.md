# AgentFlow

Plugin Claude Code biến một repo GitHub thành **team agent có kỷ luật**: **DEV** (Opus) code, **REVIEWER** (Opus) soát code và giải pháp, **QC** test trên staging — tự chạy ticket trên GitHub Projects board **tới cổng của con người**. Bạn chỉ làm ba việc: **chốt việc** (PO kéo Backlog → Ready), **QC tay** khi cần, và **merge**.

- **Một plugin, nhiều repo** — tên cột, label, nhánh, lệnh check của từng repo nằm trong `agentflow.yaml`; plugin chỉ giữ ngữ nghĩa.
- **Tối ưu token** — lệnh chỉ load khi gọi, mỗi ticket một subagent (session chính chỉ giữ 3 dòng kết quả), review/QC lặp lại chỉ soát diff mới, chờ pipeline không tốn token, lệnh check lưu sẵn trong config, output dài vào log.
- **Tự học** — agent tự ghi friction vào journal; `/agentflow:learn` chưng cất thành diff nhỏ vào plugin, bạn duyệt rồi mới phát hành.

## Luồng

```
Backlog ─PO kéo→ Ready ─DEV→ In Progress ─draft PR→ In Review ─REVIEWER ✅, merge staging→ In QC +deploying
                                                                                              │ pipeline xong
                                     Done ←người merge─ Ready to Merge ←✅ undraft─ QC test trên staging

Review ❌            → In Progress +changes-requested
QC ❌                → Ready +qc-failed, kèm bước tái hiện + bằng chứng; DEV sửa trước việc mới, rồi review phần mới → staging → QC lại
Request changes trên PR hoặc gắn changes-requested → In Progress, PR về draft (comment thường trên PR không kích hoạt DEV)
Còn mục cần test tay → +qc-manual, checklist [AF:QC] 🧪 trên staging; QC người tick + kéo card (pass, agent undraft) hoặc gắn qc-failed (fail)
Pipeline fail       → QC đọc log: do ticket thì ❌ về Ready; do hạ tầng/ticket khác thì +blocked. Quá staging.timeout_min → +blocked
Người reset staging → ticket đang chờ build quay về In Review, REVIEWER deploy lại
Bị chặn ở cột nào   → +blocked / +needs-info, ticket đứng nguyên; người trả lời rồi bỏ label
Review ❌ liên tiếp > 3 hoặc QC ❌ > 2 → +blocked + [AF:SYS] escalated (round reset); người góp ý rồi bỏ blocked
```

Nhánh staging (`staging.branch`, bắt buộc) chỉ để build test: REVIEWER merge dồn PR đã ✅ vào đó, không reset, không force-push, không merge ngược về PR hay master. Vì vậy trên staging có thể có code chưa đạt của ticket khác; nhánh lệch nhiều thì bạn tự reset.

Tên cột thật của board được map trong `agentflow.yaml` → `board.status`.

## Yêu cầu

| Thứ | Ghi chú |
|---|---|
| Claude Code ≥ 2.1.295 | plugin dùng skills, `bin/`, hooks `onFailure` (đã test trên 2.1.314) |
| `git`, `python3` ≥ 3.9, `jq` | `jq` cho `/agentflow:learn` và init |
| Nhánh staging + pipeline | Push vào staging phải chạy pipeline và báo check về commit (GitHub Actions hoặc CI ngoài có commit status) |
| GitHub **classic PAT** | `repo`, `project`, `read:org` (board của org), `workflow` nếu agent được sửa CI. Chỉ cấp đúng chừng đó |
| Figma (tuỳ chọn) | MCP chính thức, OAuth: `/mcp` → figma → Authenticate |
| Telegram (tuỳ chọn) | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` |

Mọi secret nằm trong block `env` của **`.claude/settings.local.json`** của từng repo (gitignored — init kiểm trước khi nói tới token). Ghi bằng tool đi kèm để value không bao giờ hiện ra (guard chặn agent Read/Edit file này):

```bash
read -s T && printf '%s\n' "$T" | agentflow-settings set-secret GITHUB_TOKEN     # tương tự TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
agentflow-settings show                                                           # cây key, value bị che
```

GitHub MCP lấy token qua `headersHelper` (`scripts/mcp-headers.py`): đọc file settings → env → `gh auth token`. Đổi token → `/mcp` → `plugin:agentflow:github` → **Reconnect**, không cần restart.

Tài khoản test của staging cũng để trong `env`; `staging.notes` trong `agentflow.yaml` chỉ ghi tên biến.

## Cài đặt

```bash
claude plugin marketplace add wem2017/agent-flow-plugin     # phát triển plugin: thay bằng đường dẫn tới bản clone
cd <repo của bạn>
claude plugin install agentflow@agent-flow-plugins --scope local
claude plugin enable  agentflow@agent-flow-plugins --scope local
# mở Claude Code trong repo, rồi:
/agentflow:init
```

`--scope local` để mỗi repo tự bật plugin và giữ token riêng. Plugin khai `defaultEnabled: false` — không tự chạy ở repo chưa đồng ý.

## Lệnh

| Lệnh | Việc |
|---|---|
| `/agentflow:init` | Wizard: token + scope, link board có sẵn (map cột, thêm cột thiếu mà **không mất card**) hoặc tạo board theo preset, label, issue type, issue form + PR template, convention git + lệnh check đọc từ repo, Figma, Telegram, people, permission mode; smoke test |
| `/agentflow:task <mô tả>` | Hỏi đáp chốt AC → tạo issue theo issue form của repo vào **Backlog** (PO kéo Ready). `#n` = hoàn thiện spec một issue ở Backlog |
| `/agentflow:do #n` | Xử lý **một** ticket qua DEV → REVIEWER → pipeline staging → QC tới cổng của người |
| `/agentflow:run` | Chạy **cả hàng đợi**: việc dở trước (feedback → QC → review → rework), rồi Ready theo Priority; song song `run.parallel` ticket; dừng khi hết việc hoặc đủ `run.max_tasks`. Chạy định kỳ: `/loop 30m /agentflow:run` |
| `/agentflow:status` | Đếm theo stage, việc chờ người, bất thường. `--metrics`: cycle time, first-pass yield, số lần fail, aging + thống kê journal |
| `/agentflow:doctor` | Kiểm config, token/scope, board mapping, label, MCP, hook, Figma, Telegram — chỉ cách sửa từng lỗi |
| `/agentflow:learn [bài học]` | Gom journal + bài học → diff nhỏ vào source plugin → bạn duyệt → bump version → validate → phát hành |

## Bên trong

| Thành phần | Vai trò |
|---|---|
| `agents/dev.md` · `reviewer.md` · `qc.md` | Ba subagent (DEV và REVIEWER Opus effort xhigh, QC Sonnet — model đổi qua `run.models`) |
| `references/protocol.md` | Contract chung: stage, label, board call, state block, comment `[AF:…]`, thứ tự ghi, git, token hygiene, journal |
| `references/dispatch.md` | Orchestrator: hàng đợi, bảng hành động, model, song song, no-progress guard |
| `references/design.md` | Figma / design trong repo — chỉ load khi ticket chạm UI |
| `skills/*` | 7 lệnh (`disable-model-invocation` — không tốn context khi không gọi) |
| `hooks/hooks.json` + `scripts/guard.py` · `shellparse.py` | Hook chặn (best-effort, xem §Chạy không cần bạn), kể cả qua lệnh bọc (`bash -c`, `env`, `timeout`, `$(…)`, `xargs`, `eval`, code Python/Node): merge/approve PR, dispatch workflow, force-push, xoá nhánh remote, push nhánh protected/base, đọc/sửa/in path `forbidden`, token trong tham số. Thêm luật theo role: QC không đổi git, REVIEWER chỉ push staging, DEV không đụng staging |
| `scripts/result-check.py` | Hook `SubagentStop`: subagent phải kết thúc bằng khối `RESULT` |
| `bin/agentflow-board` | Setup + chẩn đoán qua GraphQL (Status option, field, view, label, issue type, doctor, metrics) + đọc check pipeline staging |
| `bin/agentflow-journal` · `agentflow-notify` · `agentflow-settings` | Journal tự học (`~/.claude/agentflow/journal.jsonl`) · ping Telegram · sửa settings local không lộ secret |
| `scripts/mcp-headers.py` | `headersHelper` cấp token cho GitHub MCP lúc connect |
| `templates/` | Issue form, PR template, README board |
| `tests/` · `evals/` | Test không tốn token (guard, script, contract giữa prompt và code) · eval agent thật với MCP giả |

Phối hợp hoàn toàn qua GitHub: **Status** trên board (sự thật), **label** (tín hiệu), **state block ẩn** cuối issue body (`<!-- agentflow:state … -->` — round, PR, branch, sha, deploy), **comment `[AF:ROLE] event`** (audit + phân biệt agent với người vì agent dùng token của bạn).

## Chạy không cần bạn

`/agentflow:init` đề nghị `permissions.defaultMode: "bypassPermissions"` trong `.claude/settings.local.json` để loop không dừng hỏi quyền. Khi đó lớp chặn là **hook guard** của plugin (luôn chạy, kể cả bypass; thiếu Python hoặc quá giờ thì chặn; guard lỗi nội bộ thì chặn nếu lệnh có từ khoá rủi ro). Guard đọc cấu trúc lệnh nhưng không thấy thứ chỉ lộ ra lúc chạy (`make deploy`, script sinh động) — best-effort, không phải ranh giới bảo mật tuyệt đối; branch protection phía GitHub vẫn là lớp chắc nhất nếu gói của bạn có, `/agentflow:doctor` báo khi base chưa bật.

## Tự học

1. Agent gặp friction (review/QC fail mà lẽ ra tự bắt được, call phải thử lại, người sửa convention, phải tự dò lệnh check…) → `agentflow-journal add …` một dòng.
2. `/agentflow:status --metrics` cho thấy chỗ đau (first-pass yield, aging).
3. `/agentflow:learn` → ≤ 5 bài học, mỗi bài một diff nhỏ vào đúng file (có trần ký tự để prompt không phình), gate theo `DESIGN-NOTES.md` §Non-goals, bạn duyệt → bump → `claude plugin validate` → `marketplace update` + `plugin update` → restart.

## Phát triển

Phát triển plugin: [`CONTRIBUTING.md`](CONTRIBUTING.md). Lý do thiết kế: [`DESIGN-NOTES.md`](DESIGN-NOTES.md). Dữ liệu đi đâu: [Privacy](PRIVACY.md).
