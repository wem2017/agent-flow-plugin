#!/usr/bin/env python3
"""headersHelper for the plugin's GitHub MCP server: prints the auth headers as JSON.

Token: the one `gh` uses (afconfig.github_token()). Runs at every (re)connect, so `gh auth login` /
`gh auth refresh` then `/mcp` → reconnect picks up the new token without restarting Claude Code.
Prints nothing but the JSON object.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import afconfig  # noqa: E402

TOOLSETS = "context,issues,pull_requests,labels,projects,actions"


def main():
    tok = afconfig.github_token()
    headers = {"X-MCP-Toolsets": TOOLSETS}
    if tok:
        headers["Authorization"] = "Bearer " + tok
    sys.stdout.write(json.dumps(headers))


if __name__ == "__main__":
    main()
