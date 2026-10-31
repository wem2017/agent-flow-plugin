---
max_turns: 15
allowed_tools: [Read, Grep, Glob, Agent]
---

Gọi Agent tool với subagent_type `agentflow:reviewer` và đúng prompt sau, chờ nó xong rồi in nguyên văn khối RESULT của nó:

REPO: acme/app
ISSUE: #42
ITEM_ID: PVTI_42
STAGE: in_review
