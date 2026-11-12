#!/usr/bin/env python3
"""Stateful stand-in for the GitHub MCP server (stdio JSON-RPC), for tests/e2e/run.py. State lives in a JSON file, so the
harness can read what the agents did; every call is logged there. PR heads come from the bare repo, as on GitHub."""

import json
import os
import subprocess
import sys

STATE = os.environ.get("AF_E2E_STATE")
BARE = os.environ.get("AF_E2E_BARE")
# Input schemas recorded from the real server (tools/list of api.githubcopilot.com/mcp/, 2026-10-31).
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "github_tools.json"), encoding="utf-8") as _fh:
    TOOLS = json.load(_fh)


def load():
    with open(STATE, encoding="utf-8") as fh:
        return json.load(fh)


def save(state):
    tmp = STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, STATE)


def head_sha(branch):
    res = subprocess.run(["git", "-C", BARE, "rev-parse", "--verify", "-q", "refs/heads/" + branch], capture_output=True, text=True)
    return res.stdout.strip() or None


def issue_view(st):
    i = st["issue"]
    return {"number": i["number"], "title": i["title"], "state": i["state"], "body": i["body"], "labels": [{"name": n} for n in i["labels"]],
            "assignees": [{"login": a} for a in i["assignees"]], "html_url": "https://github.com/acme/app/issues/%d" % i["number"]}


def item_view(st):
    i = st["issue"]
    return {"id": "PVTI_42", "content": {"number": i["number"], "title": i["title"], "state": i["state"], "type": "Issue", "repository": "acme/app", "assignees": [{"login": a} for a in i["assignees"]]},
            "fields": [{"name": "Status", "value": {"name": st["status"]}}, {"name": "Labels", "value": i["labels"]}, {"name": "Size", "value": {"name": "S"}}]}


def pr_view(st):
    pr = st["pr"]
    return {"number": pr["number"], "state": pr["state"], "draft": pr["draft"], "merged": False, "title": pr["title"], "body": pr["body"], "mergeable_state": "clean",
            "head": {"ref": pr["head"], "sha": head_sha(pr["head"])}, "base": {"ref": pr["base"]}, "html_url": "https://github.com/acme/app/pull/%d" % pr["number"]}


def call(name, a, st):
    method = a.get("method")
    if name == "get_me":
        return {"login": "agentflow-bot", "id": 1}
    if name == "issue_read":
        if method == "get_comments":
            return st["issue"]["comments"]
        if method == "get_labels":
            return [{"name": n} for n in st["issue"]["labels"]]
        return issue_view(st)
    if name == "issue_write":
        for key in ("body", "title", "state"):
            if a.get(key) is not None:
                st["issue"][key] = a[key]
        if a.get("labels") is not None:
            st["issue"]["labels"] = a["labels"]
        if a.get("assignees") is not None:
            st["issue"]["assignees"] = a["assignees"]
        return issue_view(st)
    if name == "add_issue_comment" and st.get("pr") and str(a.get("issue_number")) == str(st["pr"]["number"]):
        st["pr"]["comments"].append({"id": 500 + len(st["pr"]["comments"]), "body": a.get("body", ""), "author_association": "OWNER", "user": {"login": "agentflow-bot"}})
        return {"id": 500 + len(st["pr"]["comments"]), "html_url": "https://github.com/acme/app/pull/57#issuecomment-%d" % len(st["pr"]["comments"])}
    if name == "add_issue_comment":
        st["issue"]["comments"].append({"id": len(st["issue"]["comments"]) + 1, "body": a.get("body", ""), "author_association": "OWNER", "user": {"login": "agentflow-bot"}})
        return {"id": len(st["issue"]["comments"]), "html_url": "https://github.com/acme/app/issues/42#issuecomment-%d" % len(st["issue"]["comments"])}
    if name == "projects_get":
        if method == "get_project":
            return {"id": "PVT_1", "title": "E2E", "number": 3}
        return item_view(st)
    if name == "projects_list":
        return {"items": [item_view(st)], "pageInfo": {"hasNextPage": False, "endCursor": None}}
    if name == "projects_write":
        field = a.get("updated_field") or {}
        if method == "update_project_item" and field.get("name") == "Status":
            st["status"] = field.get("value")
            st["status_history"].append(field.get("value"))
        return item_view(st)
    if name == "create_pull_request":
        st["pr"] = {"number": 57, "state": "open", "draft": bool(a.get("draft")), "title": a.get("title", ""), "body": a.get("body", ""), "head": a.get("head"), "base": a.get("base"), "reviews": [], "comments": []}
        return pr_view(st)
    if name in ("pull_request_read", "update_pull_request", "pull_request_review_write", "add_reply_to_pull_request_comment") and not st.get("pr"):
        raise ValueError("pull request not found")
    if name == "pull_request_read":
        pr = st["pr"]
        if method == "get_reviews":
            return pr["reviews"]
        if method in ("get_comments", "get_review_comments"):
            return pr["comments"]
        if method in ("get_status", "get_check_runs"):
            return {"state": "success", "statuses": [], "check_runs": []}
        if method == "get_commits":
            return []
        if method in ("get_diff", "get_files"):
            res = subprocess.run(["git", "-C", BARE, "diff", "%s...%s" % (pr["base"], pr["head"])] + (["--stat"] if method == "get_files" else []), capture_output=True, text=True)
            return res.stdout
        return pr_view(st)
    if name == "update_pull_request":
        for key in ("draft", "title", "body", "state"):
            if a.get(key) is not None:
                st["pr"][key] = a[key]
        return pr_view(st)
    if name == "pull_request_review_write":
        st["pr"]["reviews"].append({"id": len(st["pr"]["reviews"]) + 1, "state": str(a.get("event", "COMMENT")) + "ED", "event": a.get("event"), "body": a.get("body", ""), "submitted_at": "2026-10-31T00:00:00Z"})
        return {"id": len(st["pr"]["reviews"]), "html_url": "https://github.com/acme/app/pull/57#pullrequestreview-%d" % len(st["pr"]["reviews"])}
    if name == "search_pull_requests":
        pr = st.get("pr")
        hit = pr and any(r.get("state") == "CHANGES_REQUESTED" for r in pr["reviews"])
        return {"total_count": 1 if hit else 0, "items": [pr_view(st)] if hit else []}
    if name == "add_reply_to_pull_request_comment":
        for thread in st["pr"].get("threads", []):
            if thread["comments"][0]["id"] == int(a.get("commentId") or 0):
                thread["comments"].append({"id": 1000 + len(st["calls"]), "body": a.get("body", ""), "author_association": "OWNER",
                                           "user": {"login": "agentflow-bot"}, "created_at": "2026-10-31T01:00:00Z"})
                return {"id": thread["comments"][-1]["id"]}
        raise ValueError("review comment %s not found" % a.get("commentId"))
    if name == "actions_list":
        log = st.get("job_log")
        return {"total_count": 1 if log else 0, "workflow_runs": [{"id": 900, "name": "staging", "conclusion": "failure", "head_branch": "staging"}] if log else [],
                "jobs": [{"id": 901, "name": "build", "conclusion": "failure"}] if log else []}
    if name == "get_job_logs":
        return {"logs": st.get("job_log") or ""}
    return {"ok": True}  # merge_pull_request, actions_run_trigger: reaching here is what the harness fails on


def _gql_comment(c):
    return {"databaseId": c["id"], "author": {"login": c["user"]["login"]}, "authorAssociation": c.get("author_association", "OWNER"),
            "body": c.get("body", ""), "createdAt": c.get("created_at", "2026-10-31T00:00:00Z")}


def graphql(query, st):
    """The two queries of `agentflow-board feedback`, answered from the same state the MCP side writes."""
    pr = st.get("pr")
    node = None
    if pr:
        node = {"number": pr["number"], "state": pr["state"].upper(), "isDraft": pr["draft"], "headRefName": pr["head"],
                "url": "https://github.com/acme/app/pull/%d" % pr["number"], "repository": {"nameWithOwner": "acme/app"},
                "headRepository": {"nameWithOwner": "acme/app"}}
    if "closedByPullRequestsReferences" in query:
        return {"repository": {"issue": {"body": st["issue"]["body"], "closedByPullRequestsReferences": {"nodes": [node] if node else []},
                                         "timelineItems": {"nodes": []}}}}
    if "reviewThreads" in query and node:
        threads = [{"isResolved": t.get("resolved", False), "isOutdated": False, "path": t["path"], "line": t["line"], "originalLine": t["line"],
                    "root": {"nodes": [{"databaseId": t["comments"][0]["id"]}]}, "comments": {"nodes": [_gql_comment(c) for c in t["comments"]]}}
                   for t in pr.get("threads", [])]
        reviews = [{"databaseId": r["id"], "author": {"login": (r.get("user") or {}).get("login", "agentflow-bot")},
                    "authorAssociation": r.get("author_association", "OWNER"), "state": r["state"], "body": r.get("body", ""),
                    "submittedAt": r.get("submitted_at")} for r in pr["reviews"]]
        comments = [_gql_comment(c) for c in pr["comments"] if c.get("user")]
        return {"repository": {"pullRequest": dict(node, reviewThreads={"nodes": threads}, reviews={"nodes": reviews}, comments={"nodes": comments})}}
    raise ValueError("unsupported query")


def main():
    for line in sys.stdin:
        msg = json.loads(line)
        if "id" not in msg:
            continue
        result = {}
        if msg["method"] == "initialize":
            result = {"protocolVersion": msg["params"]["protocolVersion"], "capabilities": {"tools": {}}, "serverInfo": {"name": "fake-github", "version": "1"}}
        elif msg["method"] == "tools/list":
            result = {"tools": [{"name": t, "description": "GitHub: " + t, "inputSchema": schema} for t, schema in TOOLS.items()]}
        elif msg["method"] == "tools/call":
            name, args = msg["params"]["name"], msg["params"].get("arguments") or {}
            st = load()
            st["calls"].append({"tool": name, "args": args})
            try:
                text, error = json.dumps(call(name, args, st), ensure_ascii=False), False
            except (ValueError, AttributeError, KeyError, TypeError) as exc:  # the agent must see it, not a dead connection
                text, error = "%s: %s" % (type(exc).__name__, exc), True
            save(st)
            result = {"content": [{"type": "text", "text": text}], "isError": error}
        print(json.dumps({"jsonrpc": "2.0", "id": msg["id"], "result": result}), flush=True)


if __name__ == "__main__":
    main()
