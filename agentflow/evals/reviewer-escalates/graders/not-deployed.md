---
type: regex
target: trace
pattern: '"name":"mcp__plugin_agentflow_github__[a-z_]+".{0,300}\[AF:REVIEW\] deployed'
match: not_contains
---
