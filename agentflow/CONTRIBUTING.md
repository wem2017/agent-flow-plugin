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

Vì cài ở **user scope**, một lần update là **mọi project trên máy đều nhận** — không cần lặp lại từng repo.

**Mẹo dev nhanh:** đang lặp liên tục và ngại bump version mỗi lần thì `claude plugin uninstall agentflow@agent-flow-plugins` rồi `install` lại — ép copy snapshot mới kể cả cùng version. Bump version vẫn là cách chuẩn cho release thật.

**Phân phối cho team / máy khác.** `directory` source chỉ chạy trên máy bạn (đường dẫn local). Muốn người khác nhận được update, chuyển sang **`github` source**:

1. Push repo marketplace này lên GitHub.
2. Mỗi release: bump `version`, commit, rồi `claude plugin tag ./agentflow` tạo git tag `agentflow--v<version>` (lệnh này verify `plugin.json` khớp với entry trong `marketplace.json`).
3. Teammate: `claude plugin marketplace add <owner/repo>` một lần; sau đó mỗi lần cập nhật chạy `claude plugin marketplace update agent-flow-plugins` + `claude plugin update agentflow@agent-flow-plugins` + restart.
