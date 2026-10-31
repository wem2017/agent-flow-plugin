#!/usr/bin/env python3
"""AgentFlow SubagentStop check: an agent ends with the RESULT block (protocol §13), since that block is all the
orchestrator reads. Missing or malformed → the agent gets one more turn to write it. Never blocks twice."""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import afconfig  # noqa: E402

RESULT = re.compile(r"^RESULT:\s*(\S+)\s*·\s*(ok|waiting_human|needs_info|blocked|escalated|abort)\s*$", re.M)
HINT = "Kết thúc bằng đúng khối protocol §13: `RESULT: <stage hiện tại> · <ok|waiting_human|needs_info|blocked|escalated|abort>`, `PR: #<m> @<sha>` (nếu có), `NOTE: …`."


def verdict(data):
    """Return the reason to keep the agent running, or None."""
    if data.get("stop_hook_active") or not str(data.get("agent_type") or "").startswith("agentflow:"):
        return None
    match = RESULT.search(str(data.get("last_assistant_message") or ""))
    if not match:
        return "Thiếu khối RESULT. " + HINT
    if match.group(1) not in afconfig.STAGES:
        return "`%s` không phải stage hợp lệ (%s). %s" % (match.group(1), ", ".join(afconfig.STAGES), HINT)
    return None


def main():
    try:
        reason = verdict(json.load(sys.stdin))
    except ValueError:
        return
    if reason:
        print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))


if __name__ == "__main__":
    main()
