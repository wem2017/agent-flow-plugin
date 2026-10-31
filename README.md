# agent-flow-plugin

Marketplace Claude Code chứa plugin [AgentFlow](agentflow/README.md): team agent DEV · Reviewer · QC tự chạy ticket trên GitHub Projects board tới cổng của con người.

```bash
claude plugin marketplace add wem2017/agent-flow-plugin
cd <repo của bạn>
claude plugin install agentflow@agent-flow-plugins --scope local
claude plugin enable  agentflow@agent-flow-plugins --scope local
# mở Claude Code trong repo, rồi:
/agentflow:init
```

Yêu cầu, cách dùng: [`agentflow/README.md`](agentflow/README.md). Phát triển plugin: [`agentflow/CONTRIBUTING.md`](agentflow/CONTRIBUTING.md). Dữ liệu đi đâu: [`agentflow/PRIVACY.md`](agentflow/PRIVACY.md).

License: [MIT](LICENSE).
