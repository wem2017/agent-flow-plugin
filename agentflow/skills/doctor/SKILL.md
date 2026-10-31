---
name: doctor
description: Kiểm tra nhanh AgentFlow trên repo này — config, token + scope, board + mapping cột, field, label, issue type, base branch + branch protection, nhánh staging + pipeline, surfaces, workflow board, GitHub MCP, Figma MCP, hook guard, Telegram — và nói đúng cách sửa từng lỗi. Chỉ đọc; gọn hơn chạy lại /agentflow:init.
disable-model-invocation: true
allowed-tools: Bash(agentflow-board doctor*) Bash(agentflow-journal stats*) Bash(agentflow-settings show*) Bash(git check-ignore*)
---

Chỉ đọc. Chạy lần lượt, gom kết quả thành **một** bảng ✓ / ⚠ / ✗ (≤ 25 dòng), mỗi ✗ kèm đúng một cách sửa.

1. **Config + GitHub** (script làm hết phần nặng):

   ```bash
   agentflow-board doctor
   ```

2. **GitHub MCP**: nạp `get_me` bằng ToolSearch rồi gọi. Fail mà bước 1 qua → `/mcp` → `plugin:agentflow:github` → Reconnect (không phải lỗi token). Thiếu tool `projects_*` → token thiếu scope `project`, hoặc `X-MCP-Toolsets` trong `scripts/mcp-headers.py` bị sửa.
3. **Figma** (chỉ khi `design.figma: true`): tool MCP `figma` có trong session? Không có / lỗi auth → `/mcp` → figma → Authenticate.
4. **Hook guard**:

   ```bash
   printf '%s' '{"tool_name":"Bash","tool_input":{"command":"git push --force"},"cwd":"'"$PWD"'"}' \
     | python3 "${CLAUDE_PLUGIN_ROOT}/scripts/guard.py" 2>/dev/null; echo "exit $?"
   ```

   Phải `exit 2`. Khác → hook không hoạt động: kiểm `python3`, plugin đã enable chưa.
5. **Permission mode**: `agentflow-settings show` → `permissions.defaultMode` — `bypassPermissions` ⇒ loop chạy không hỏi; khác ⇒ loop sẽ dừng hỏi quyền (ghi ⚠, không phải lỗi).
6. **Worktree**: `git check-ignore -q .claude/worktrees/` — chưa ignore → ✗ (worktree của agent sẽ lọt vào `git status`).
7. **Journal**: `agentflow-journal stats` — ≥ 5 entry mới → ⚠ gợi `/agentflow:learn`.

Kết thúc một dòng: `OK — sẵn sàng /agentflow:run` hoặc `<k> lỗi — sửa theo bảng rồi chạy lại /agentflow:doctor`.
