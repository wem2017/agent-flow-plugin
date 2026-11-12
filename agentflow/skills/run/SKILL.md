---
name: run
description: Chạy AgentFlow loop trên board của repo này — nhặt mọi ticket agent xử lý được (sửa theo góp ý, QC người fail, review, rework, rồi việc mới ở Ready theo Priority), chain SA thiết kế → DEV (code + flow automation + deploy staging + chạy flow) → SA review song song qua worktree, dừng ở cổng của người hoặc khi chạm trần số ticket.
argument-hint: "[--max N] [--parallel N] [--only sa|dev]"
disable-model-invocation: true
---

Bạn là **orchestrator** cho lượt chạy này. Đọc, theo thứ tự:

1. `${CLAUDE_PLUGIN_ROOT}/references/protocol.md`
2. `${CLAUDE_PLUGIN_ROOT}/references/dispatch.md` — boot, hàng đợi, bảng hành động, spawn, guard, dừng, báo cáo.

## Tham số (`$ARGUMENTS`)

- `--max N` → ghi đè `run.max_tasks` cho lượt này.
- `--parallel N` → ghi đè `run.parallel` (1 = tuần tự).
- `--only sa|dev` → chỉ spawn agent đó, theo dòng khớp **đầu tiên** của bảng §3 (dòng của agent khác ⇒ bỏ qua ticket, không xét dòng sau). SYS *done* / *qc-manual-pass* vẫn chạy; SYS dẫn tới DEV (*feedback*, *qc-failed*, *requeue*) chỉ khi có `dev`. Vd: SA thiết kế trước cả hàng Ready.

## Vòng lặp

```
boot (dispatch §1)
lặp:
  đọc hàng đợi (§2) → bảng hành động (§3) → sắp xếp (§4)
  bỏ ticket đang in-flight hoặc đã xong trong lượt này
  rỗng và không còn agent đang chạy → thoát vòng
  lấy tối đa `parallel` ticket → SYS transition nếu cần → spawn đồng thời (§5)
  xử lý từng kết quả (§6); ticket còn đi tiếp được thì spawn ngay bước kế, không đọc lại cả board
  chạm trần (§7) → thoát vòng
dọn worktree (§7) → báo cáo (§8)
```

Đọc lại cả board chỉ khi còn slot trống và các ticket đang chain đã dừng — không poll lại sau mỗi spawn.

## Chạy liên tục

Lệnh này chạy **một lượt** rồi dừng. Tự chạy định kỳ: `/loop 30m /agentflow:run` (hoặc `/loop /agentflow:run` để tự canh nhịp). Gợi ý `/clear` giữa các phiên dài để context không phình.

## Luật

- Không hỏi người giữa lượt; không viết code; không sửa file ngoài `.claude/worktrees/` (do subagent) và state trên GitHub.
- Không đụng ticket ở `backlog`, không kéo ticket ra khỏi `ready_to_merge` ngoài hai trường hợp ở bảng §3.
- Ghi journal (`--role run`) khi: no-progress guard kích hoạt, call MCP phải thử lại ≥2 lần, hoặc hàng đợi lọc sai (ticket đáng lẽ thấy mà không thấy).
