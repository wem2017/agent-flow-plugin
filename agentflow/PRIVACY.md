# Privacy

AgentFlow chạy trên máy của bạn, bằng token của bạn. Plugin không có server riêng, không có telemetry, không gửi gì cho tác giả plugin.

| Dữ liệu | Đi đâu | Khi nào |
|---|---|---|
| Issue, PR, comment, label, trạng thái board, log CI | GitHub (`api.github.com`, GitHub MCP tại `api.githubcopilot.com/mcp/`) | Mọi lệnh làm việc với board |
| Nội dung file thiết kế | Figma MCP (`mcp.figma.com`) | Chỉ khi `design.figma: true` và bạn đã OAuth |
| Tên repo, số issue, tiêu đề ticket, link | Telegram Bot API (`api.telegram.org`) | Chỉ khi `notify.telegram: true` |
| Code và nội dung agent đọc | Anthropic, theo điều khoản tài khoản Claude Code của bạn | Như mọi session Claude Code |

**Lưu trên máy**

- Token: block `env` trong `.claude/settings.local.json` của từng repo (gitignored, mode 600).
- Journal friction: `~/.claude/agentflow/journal.jsonl`, một dòng cho mỗi friction, chuỗi giống token bị thay bằng `<secret>` trước khi ghi. Xoá file bất cứ lúc nào.
- Log build/test: `/tmp/af-<n>*.log`.

**Lưu ý**: agent dùng token của bạn nên mọi comment trên GitHub đứng tên bạn. Guard chặn gọi tool có tham số chứa chuỗi giống token thật, nhưng chỉ nhận ra các định dạng phổ biến. Xem [`DESIGN-NOTES.md`](DESIGN-NOTES.md) §Giới hạn đã biết.
