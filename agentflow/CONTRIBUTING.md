# Phát triển AgentFlow

Marketplace `agent-flow-plugins` là **directory source** trỏ vào repo này: Claude Code đọc thẳng working tree, nhưng lúc `install`/`update` nó **copy snapshot** vào `~/.claude/plugins/cache/agent-flow-plugins/agentflow/<version>/` — khoá theo `version`. Sửa source không tự lan sang bản đang chạy.

## Vòng phát hành (đã tự động trong `/agentflow:learn`)

```bash
# sửa file trong agentflow/ → bump "version" trong agentflow/.claude-plugin/plugin.json
claude plugin validate ./agentflow
claude plugin marketplace update agent-flow-plugins
claude plugin update agentflow@agent-flow-plugins
# restart Claude Code
```

Không bump version thì `update` báo *already at latest* và không refresh. Lặp nhanh khi dev: `uninstall` rồi `install` lại.

## Test trước khi phát hành

```bash
python3 -I -m unittest discover -s agentflow/tests             # script + contract, không cần mạng, không tốn token
claude plugin validate ./agentflow
GITHUB_TOKEN=… python3 -I agentflow/bin/agentflow-board doctor --root <repo đã init>   # kiểm với GitHub thật
agentflow/evals/run.sh --runs 1 --max-cost-usd 5               # hành vi của agent, tốn token — xem evals/README.md
```

| Tầng | File | Kiểm gì |
|---|---|---|
| Guard | `tests/test_guard.py`, `tests/test_shellparse.py` | Bảng lệnh chặn/cho qua, role, hook thật |
| Script | `tests/test_afconfig.py`, `test_board.py`, `test_tools.py` | Parser YAML (đối chiếu PyYAML nếu có), forbidden, API giả, không lộ secret |
| Contract | `tests/test_contract.py` | Trần ký tự của prompt, tham chiếu `§`, path `${CLAUDE_PLUGIN_ROOT}`, lệnh `agentflow-board`, frontmatter, stage/label/`[AF:…]` khớp giữa file |
| E2E | `tests/e2e/run.py` | Nguyên `/agentflow:do` với git thật, hook thật, GitHub giả có trạng thái (schema ghi từ server thật): assert trên kết quả ở GitHub và git. Tốn token |
| Eval | `evals/` | Agent thật + MCP giả: DoR defense, review ❌, escalate, hook thật chặn force-push và đọc secret |

Sửa guard hoặc script → thêm case cho mỗi lỗ hổng/chặn nhầm vừa sửa. Sửa prompt của agent → chạy eval của agent đó (`--case`). CI (`.github/workflows/ci.yml`) chạy tầng không tốn token.

## Quy ước

- Prompt runtime (`agents/`, `references/`, `skills/`) là **chi phí token mỗi lần chạy**: mệnh lệnh ngắn, một fact một chỗ, lý do để ở `DESIGN-NOTES.md`. Trần ký tự của từng file nằm ở `tests/test_contract.py` (`BUDGETS`), không nâng trần khi chưa xoá được gì.
- Script: Python 3 stdlib, không dependency. Không bao giờ in token; header bí mật đưa qua stdin (`curl -K -`).
- Đổi key `agentflow.yaml`, ngữ nghĩa stage, dòng đầu `[AF:…]` hay key state block = **schema change**: tăng `schema` (template + `scripts/afconfig.py` + `references/protocol.md`), bump minor/major.

## Phân phối cho team

Push repo lên GitHub; mỗi release `claude plugin tag ./agentflow` (tạo tag `agentflow--v<version>`). Teammate: `claude plugin marketplace add <owner>/<repo>` một lần, sau đó `marketplace update` + `plugin update` + restart. Máy không giữ source thì `/agentflow:learn` dừng và đề nghị gửi bài học qua issue/PR.
