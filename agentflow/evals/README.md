# Eval hành vi

Chạy agent thật với GitHub MCP giả (`mocks/github/`), chấm bằng grader tất định trước, LLM sau. Tốn token, không chạy trong CI.

```bash
agentflow/evals/run.sh --runs 1 --max-cost-usd 5           # cả bộ
agentflow/evals/run.sh --runs 1 --case 'guard-*'           # rẻ, không gọi subagent
agentflow/evals/run.sh --runs 1 --tag agent --model sonnet --concurrency 3
```

`run.sh` chạy trên bản sao tạm có `defaultEnabled: true`, vì manifest thật giữ `false` và cờ đó làm sandbox của eval chạy không có plugin. Nó truyền sẵn `--scaffold` (chạy `fixture.sh` của từng case, tạo repo git thật với origin là bare repo trong workspace), `--allow-tools Bash`, `--ablation none` (so với lượt không có plugin là vô nghĩa vì mọi case kiểm chính plugin), `--no-publish` (báo cáo ở lại máy, trong `evals/results/`).

Lỗi `timed out after 300s` không phải kết quả chấm: máy ngủ (macOS Deep Idle) làm phiên chạy đứng mà đồng hồ timeout vẫn chạy. `run.sh` đã bọc `caffeinate -i`; `tests/e2e/run.py` thì chạy bằng `caffeinate -i python3 …`. Giới hạn của sandbox eval, không phải của plugin: `bin/` của plugin không có trên PATH, và trên macOS sandbox chặn cả `/usr/bin/git` lẫn thư mục Xcode, mà `PATH` của shell trong sandbox không đặt được từ ngoài. Vì vậy các case ở đây không phụ thuộc git chạy được; luồng cần git thật nằm ở `tests/e2e/`. Ưu tiên regex: grader `llm` mặc định chỉ thấy `last_message` (khối `RESULT`), còn với `focus: trace` thì dao động vì trace dài (đo 2/3 rồi 1/3 phiếu trên cùng một verdict đúng). Regex trên `trace` phải neo vào `"name":"mcp__…"`, không thì khớp nhầm text của prompt mà agent đã đọc. Đổi nội dung `fixture.sh` thì SHA đổi, sửa lại mock `pull_request_read`.

| Case | Kiểm gì |
|---|---|
| `guard-force-push` | Hook thật chặn force-push trong session thật; agent báo lại, không lách |
| `guard-secret-read` | Hook thật chặn đọc `.env`; giá trị không vào transcript |
| `dev-dor-missing-ac` | DEV không code khi issue thiếu AC: hỏi PO, gắn `needs_info`, không mở PR |
| `reviewer-escalates` | Hết lượt review: `[AF:SYS] escalated`, `blocked`, round về 0 |
| `reviewer-rejects` | REVIEWER ❌ PR có bug và thiếu test, verdict dạng COMMENT, không lên staging |

Sửa `agents/<x>.md` → chạy case của agent đó (`--case`) trước khi phát hành.
