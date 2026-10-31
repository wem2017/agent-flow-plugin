---
name: learn
description: Tự học cho AgentFlow — gom friction từ journal (review/QC fail, feedback của người, call lỗi, retry, convention bị sửa) và từ bài học bạn truyền vào, khử trùng thành vài bài học, đề xuất minimal diff vào source của plugin, bạn duyệt rồi mới ghi, bump version, validate và phát hành để lần chạy sau làm đúng hơn.
argument-hint: "[bài học tự do] [--release] [--no-release]"
disable-model-invocation: true
---

Bạn **dạy plugin**: biến friction thành thay đổi nhỏ nhất trong prompt/script của plugin. Bài học **chỉ đi vào plugin SOURCE** — không bao giờ sửa `${CLAUDE_PLUGIN_ROOT}` (bản cache khoá theo version, update là mất).

## 0. Resolve SOURCE

```bash
ID=$(jq -r '.plugins|keys[]|select(startswith("agentflow@"))' ~/.claude/plugins/installed_plugins.json | head -1)
MKT=${ID#*@}
ROOT=$(jq -r --arg m "$MKT" '.[$m].source | if .source=="directory" then .path else empty end' ~/.claude/plugins/known_marketplaces.json)
SUB=$(jq -r '.plugins[]|select(.name=="agentflow").source' "$ROOT/.claude-plugin/marketplace.json" 2>/dev/null)
SRC="$ROOT/${SUB#./}"; test -f "$SRC/.claude-plugin/plugin.json" && echo "SRC=$SRC" || echo "NO_SOURCE"
```

`NO_SOURCE` (marketplace dạng github, máy không giữ source) → **dừng**: đề nghị mở issue/PR trên repo của plugin, kèm bài học đã soạn. Version cache ≠ version source → báo một dòng (lần release này ship cả backlog).

`--release` → bỏ qua §1–§5, nhảy §6 từ bước 2 (không có diff mới để áp, version đã bump).

## 1. Gom

- `agentflow-journal list` (entry `new`) + `$ARGUMENTS` (bỏ flag).
- Trống cả hai → mine session hiện tại: người phải sửa lại agent, call phải thử ≥ 2 lần, lệnh check sai, convention bị chỉnh. Vẫn không có gì → hỏi: "Bài học lần này là gì?"
- Cần bằng chứng thêm → đọc **đúng** verdict `[AF:REVIEW] ❌` / `[AF:QC] ❌` / comment người mà entry trỏ tới (repo + issue), không đọc lan.

## 2. Chưng cất

Gộp entry cùng gốc thành **≤ 5 bài học**, mỗi bài một dòng: `agent <role> nên X thay vì Y — bằng chứng: <id journal, #issue>`. Loại:
- **Chỉ đúng với một repo** (tên lệnh, path, convention riêng) → không phải bài học plugin: đề xuất sửa `agentflow.yaml` / `CLAUDE.md` của repo đó (một dòng), rồi `dismissed`.
- **Sự cố môi trường một lần** (mạng, token hết hạn) → `dismissed`.
- Mơ hồ, không chỉ ra được hành vi khác đi → hỏi một câu làm rõ, không đoán.

## 3. Gate — DỪNG và xác nhận nếu bài học đụng

- **Non-goal** trong `$SRC/DESIGN-NOTES.md` §Non-goals → đây là *đổi thiết kế*, chỉ làm khi người xác nhận tường minh.
- **Schema**: key của `agentflow.yaml`, ngữ nghĩa stage, dòng đầu comment `[AF:…]`, key của state block, tên label key → bump **minor** + `schema` trong `agentflow.yaml` + `scripts/afconfig.py` (`SCHEMA`) + `references/protocol.md` §1; mọi repo phải chạy lại `/agentflow:init`.
- Thêm key config: phải trả lời được "vì sao không suy từ git / không là hằng số plugin?".

## 4. Định tuyến (một bài học → một file chính)

| Bài học về… | File |
|---|---|
| Cách implement, branch, PR, rework, DoR defense | `agents/dev.md` |
| Tiêu chí review, mức chặn vs gợi ý | `agents/reviewer.md` |
| Cách verify AC, phân định lỗi, checklist test tay | `agents/qc.md` |
| Stage, label, board call, state block, comment, thứ tự ghi, escalation, git, token hygiene, journal | `references/protocol.md` |
| Hàng đợi, thứ tự, model, song song, guard, SYS transition | `references/dispatch.md` |
| Figma / design | `references/design.md` |
| Hành vi một lệnh | `skills/<lệnh>/SKILL.md` |
| Lệnh nguy hiểm lọt qua / chặn nhầm | `scripts/guard.py`, `scripts/shellparse.py` (+ thêm case vào `tests/test_guard.py`) |
| Setup / chẩn đoán board | `bin/agentflow-board`, `skills/init/…` |
| Vì sao thiết kế như vậy | `DESIGN-NOTES.md` (không phải file runtime) |

## 5. Soạn diff — ngân sách token là luật

- Đọc file đích trước. Sửa **ít nhất có thể**: một dòng, một mục list, sửa một câu. Đã có ý tương tự → làm rõ câu đó, không thêm câu mới.
- Mỗi dòng thêm vào `agents/*`, `references/*`, `skills/*` bị trả giá ở **mọi** lần chạy. Trần theo **ký tự** nằm ở `tests/test_contract.py` (`BUDGETS`), không theo dòng vì một dòng có thể dài vài trăm ký tự. Vượt → phải gộp/xoá câu khác trong cùng lượt, không nâng trần.
- Dòng chỉ giải thích *vì sao* → `DESIGN-NOTES.md`; file runtime chỉ giữ mệnh lệnh.
- Một fact một chỗ: `grep -rn` trước khi thêm.

Trình **một lần**: danh sách bài học → file → diff → mức bump (`patch` mặc định; thêm năng lực → `minor`). Chờ duyệt. Chưa duyệt chưa ghi gì.

## 6. Ghi, phát hành, đóng journal

1. Áp diff vào `$SRC`. Bump `version` trong `$SRC/.claude-plugin/plugin.json` (một lần cho cả lượt).
2. `claude plugin validate "$SRC"` — fail → giữ edit, in lỗi, dừng.
3. `python3 -I -m unittest discover -s "$SRC/tests"` phải pass hết trước khi phát hành. Sửa guard hoặc script → thêm case mới vào đúng file test.
4. `agentflow-journal mark <id…> --as applied --ref v<NEW>` (và `--as dismissed` cho entry bị loại).
5. Trừ khi `--no-release`: kiểm `git -C "$SRC" status --porcelain` (file bẩn ngoài lượt này → liệt kê, hỏi), rồi hỏi một lần và chạy `claude plugin marketplace update "$MKT" && claude plugin update "$ID"`; xác nhận version mới trong `~/.claude/plugins/installed_plugins.json`.
6. Báo: version cũ → mới, file đổi, bài học đã áp. Nhắc **restart Claude Code**. Schema đổi → nhắc chạy lại `/agentflow:init` ở mỗi repo. Hỏi (không tự làm) có commit `$SRC` với message `learn: <tóm tắt> (v<NEW>)` không. Không bao giờ push.
