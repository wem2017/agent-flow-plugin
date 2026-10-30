# Phát triển AgentFlow

Marketplace `agent-flow-plugins` là **directory source** trỏ vào repo này: Claude Code đọc thẳng working tree, nhưng lúc `install`/`update` nó **copy snapshot** vào `~/.claude/plugins/cache/agent-flow-plugins/agentflow/<version>/` — khoá theo `version`. Sửa source không tự lan sang bản đang chạy.

## Vòng phát hành (đã tự động trong `/agentflow:learn`)

```bash
# sửa file trong agentflow/ → bump "version" trong agentflow/.claude-plugin/plugin.json → thêm mục CHANGELOG.md
claude plugin validate ./agentflow
claude plugin marketplace update agent-flow-plugins
claude plugin update agentflow@agent-flow-plugins
# restart Claude Code
```

Không bump version thì `update` báo *already at latest* và không refresh. Lặp nhanh khi dev: `uninstall` rồi `install` lại.

## Test trước khi phát hành

```bash
python3 -I agentflow/bin/agentflow-board --help                # parse được
GITHUB_TOKEN=… python3 -I agentflow/bin/agentflow-board doctor --root <repo đã init>
AGENTFLOW_JOURNAL=/tmp/j.jsonl python3 -I agentflow/bin/agentflow-journal add other "test"
```

Sửa `scripts/guard.py` → `python3 -I agentflow/tests/test_guard.py` phải pass hết; thêm case mới cho mỗi lỗ hổng/chặn nhầm vừa sửa.

## Quy ước

- Prompt runtime (`agents/`, `references/`, `skills/`) là **chi phí token mỗi lần chạy**: mệnh lệnh ngắn, một fact một chỗ, lý do để ở `DESIGN-NOTES.md`. Trần dòng: agent ≤ 110, `protocol.md` ≤ 170, còn lại ≤ 200.
- Script: Python 3 stdlib, không dependency. Không bao giờ in token; header bí mật đưa qua stdin (`curl -K -`).
- Đổi key `agentflow.yaml`, ngữ nghĩa stage, dòng đầu `[AF:…]` hay key state block = **schema change**: tăng `schema` (template + `scripts/afconfig.py` + `references/protocol.md`), bump minor/major.

## Phân phối cho team

Push repo lên GitHub; mỗi release `claude plugin tag ./agentflow` (tạo tag `agentflow--v<version>`). Teammate: `claude plugin marketplace add <owner>/<repo>` một lần, sau đó `marketplace update` + `plugin update` + restart. Máy không giữ source thì `/agentflow:learn` dừng và đề nghị gửi bài học qua issue/PR.
