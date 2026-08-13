# Phát triển & cập nhật plugin AgentFlow

Marketplace ở đây là **`directory` source** trỏ vào chính repo này, nên nó **đọc thẳng working tree** — sửa file trong `agentflow/` là bản nguồn đã đổi ngay, **không cần commit git**. Nhưng lúc `install`/`update`, Claude Code **copy một snapshot** vào cache (`~/.claude/plugins/cache/agent-flow-plugins/agentflow/<version>/`), khoá theo **`version`**: sửa source **không tự** lan sang bản đang chạy, phải update thủ công.

> **Quy tắc vàng:** mỗi lần có thay đổi muốn phát hành, **bump `version` trong `agentflow/.claude-plugin/plugin.json`** trước khi update. Không bump thì `claude plugin update` báo *"already at latest"* và **không refresh** cache — update là no-op.

**Vòng lặp cập nhật (dev trên máy này):**

```bash
# 1. sửa code trong agentflow/…
# 2. bump version trong agentflow/.claude-plugin/plugin.json   (vd 0.1.0 → 0.1.1)
claude plugin validate ./agentflow                    # (khuyến nghị) validate manifest trước
claude plugin marketplace update agent-flow-plugins   # đọc lại source, nhận version mới
claude plugin update agentflow@agent-flow-plugins      # kéo version mới vào cache
# 3. restart Claude Code để load
```

> **Lưu ý một khoảng mù.** `claude plugin validate` kiểm **shape của manifest**, nhưng không biết gì
> về hành vi — hành vi của plugin này sống hoàn toàn trong prose: tên MCP method, 6 tên Status column,
> comment prefix, `disallowedTools`… Nó cũng **không** kiểm được `${GITHUB_TOKEN}` trong `.mcp.json`
> có resolve hay không (biến trống thì server vẫn load, chỉ fail lúc connect — xem `commands/init.md`
> §1a). Nó cũng **không đọc** `.claude-plugin/marketplace.json` khi bạn trỏ vào
> `./agentflow` (file đó nằm ngoài). Chạy `claude plugin validate . --strict` **thêm một lần nữa** cho
> marketplace, và khi sửa mô tả plugin thì sửa **cả hai** file bằng tay — chính khoảng mù này đã để
> card marketplace drift qua 2 version mà không ai bắt được.

> **Đừng dùng `settings` trong `plugin.json` để ship `permissions`.** Đã thử trên Claude Code
> 2.1.227: một plugin khai báo `settings.permissions.allow` vẫn **không** làm command đó được allow.
> Đường đã verify là `/agentflow:init` Step 8.2 sinh + merge vào `.claude/settings.json` của repo.

> **Command của plugin chỉ tồn tại dưới dạng `/agentflow:<name>`.** Tên trần trả về *Unknown command*.
> Thêm một command mới → dùng dạng đầy đủ trong mọi tài liệu và mọi thông điệp in ra cho user.

Vì cài ở **user scope**, một lần update là **mọi project trên máy đều nhận** — không cần lặp lại từng repo.

> Vòng lặp này đã được tự động hoá bằng command **`/agentflow:improve`** — capture bài học từ usage thực tế, fold vào đúng file tri thức trong source (duyệt diff trước khi ghi), bump version, rồi chạy đúng các bước trên.

**Mẹo dev nhanh:** đang lặp liên tục và ngại bump version mỗi lần thì `claude plugin uninstall agentflow@agent-flow-plugins` rồi `install` lại — ép copy snapshot mới kể cả cùng version. Bump version vẫn là cách chuẩn cho release thật.

**Phân phối cho team / máy khác.** `directory` source chỉ chạy trên máy bạn (đường dẫn local). Muốn người khác nhận được update, chuyển sang **`github` source**:

1. Push repo marketplace này lên GitHub.
2. Mỗi release: bump `version`, commit, rồi `claude plugin tag ./agentflow` tạo git tag `agentflow--v<version>` (lệnh này verify `plugin.json` khớp với entry trong `marketplace.json`).
3. Teammate: `claude plugin marketplace add <owner/repo>` một lần; sau đó mỗi lần cập nhật chạy `claude plugin marketplace update agent-flow-plugins` + `claude plugin update agentflow@agent-flow-plugins` + restart.
