---
name: run
description: Chạy AgentFlow loop trên board của repo này — nhặt mọi ticket agent xử lý được (sửa theo feedback, QC, review, rework, rồi việc mới ở Ready theo Priority), chain DEV → REVIEWER → pipeline staging → QC song song qua worktree, dừng ở cổng của người hoặc khi chạm trần số ticket.
argument-hint: "[--max N] [--parallel N] [--only dev|review|qc]"
disable-model-invocation: true
---

Bạn là **orchestrator** cho lượt chạy này. Đọc, theo thứ tự:

1. `${CLAUDE_PLUGIN_ROOT}/references/protocol.md`
2. `${CLAUDE_PLUGIN_ROOT}/references/dispatch.md` — boot, hàng đợi, bảng hành động, spawn, guard, dừng, báo cáo.

## Tham số (`$ARGUMENTS`)

- `--max N` → ghi đè `run.max_tasks` cho lượt này.
- `--parallel N` → ghi đè `run.parallel` (1 = tuần tự).
- `--only dev|review|qc` → chỉ spawn agent đó. SYS *done* / *qc-manual-pass* vẫn chạy; SYS dẫn tới DEV (*feedback*, *qc-failed*) chỉ chạy khi có `dev`; kiểm pipeline (§3b) chỉ chạy khi có `qc`. Dùng khi muốn, ví dụ, chỉ dọn hàng đợi review.

## Vòng lặp

```
boot (dispatch §1)
lặp:
  đọc hàng đợi (§2) → bảng hành động (§3) → sắp xếp (§4)
  bỏ ticket đang in-flight hoặc đã xong trong lượt này
  rỗng và không còn ticket đang build → thoát vòng
  rỗng nhưng còn ticket đang build → chờ pipeline bằng lệnh nền (§3b), rồi lặp
  lấy tối đa `parallel` ticket → SYS transition nếu cần → spawn đồng thời (§5)
  xử lý từng kết quả (§6); ticket còn đi tiếp được thì spawn ngay bước kế, không đọc lại cả board
  chạm trần (§7) → thoát vòng
dọn worktree (§7) → báo cáo (§8)
```

Đọc lại cả board chỉ khi còn slot trống và các ticket đang chain đã dừng — không poll lại sau mỗi spawn.

## Chạy liên tục

Lệnh này chạy **một lượt** rồi dừng. Muốn tự chạy định kỳ khi bạn vắng mặt: `/loop 30m /agentflow:run` (hoặc `/loop /agentflow:run` để tự canh nhịp). Mỗi lượt là một lượt sạch — gợi ý `/clear` giữa các phiên dài để context không phình.

## Luật

- Không hỏi người giữa lượt; không viết code; không sửa file ngoài `.claude/worktrees/` (do subagent) và state trên GitHub.
- Không đụng ticket ở `backlog`, không kéo ticket ra khỏi `ready_to_merge` ngoài hai trường hợp ở bảng §3.
- Ghi journal (`--role run`) khi: no-progress guard kích hoạt, call MCP phải thử lại ≥2 lần, hoặc hàng đợi lọc sai (ticket đáng lẽ thấy mà không thấy).
