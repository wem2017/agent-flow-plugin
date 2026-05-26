---
name: figma-design
description: How DEV pulls design context from Figma when an issue touches a visual surface — gate on connections.figma (enabled + auth.token_env FIGMA_TOKEN, see setup-agentflow), two access paths (figma MCP server preferred, REST fallback), Figma URL parsing, and a design-to-implementation handoff that maps frames to the issue AC. Read this before implementing any visually-specified component.
---

# Figma Design Handoff

This skill governs how the **DEV** agent fetches design context when an issue touches a visual surface (any `component/<surface>` whose declared surface in `surfaces:` has a UI — e.g. web, admin, mobile) and the AC references a Figma design. Design informs **HOW** a thing looks and lays out; the issue's AC defines **WHAT** must be true. The two are not interchangeable — see *Handoff discipline* below.

## Gate before use

Figma is a connection like any other — read its wiring in `.claude/agentflow.yaml` first (see skill: `setup-agentflow` for the full connection/env spec). Do **not** call Figma tools or the REST API unless **both** are true:

- `connections.figma.enabled: true`, **and**
- the var named by `connections.figma.auth.token_env` (`FIGMA_TOKEN`) is set in the environment.

```bash
# Gate check — run before any design lookup
test -n "$FIGMA_TOKEN" || echo "FIGMA_TOKEN unset — skipping design lookup"
```

If the gate fails, **skip design lookups entirely** and proceed from the issue's AC. Note in your `[DEV]` comment that design context was unavailable (e.g. `design lookup skipped: figma not configured`) so reviewers know the implementation was AC-driven only. Never block dev work waiting on a disabled connection.

`FIGMA_TOKEN` is a secret. Reference it by name only — never print, echo, log, or commit its value, and never place it in a URL (see *Secret hygiene*).

## Two access paths

### (a) figma MCP server — preferred

Use the server named by `connections.figma.mcp.server` (`figma` in `.mcp.json`), which runs `figma-developer-mcp --stdio` (Framelink) with `FIGMA_API_KEY=${FIGMA_TOKEN}`. The server stays inert until `FIGMA_TOKEN` is set; when the gate passes (`connections.figma.enabled` and every var in `connections.figma.mcp.requires_env` present), it exposes tools namespaced as `mcp__figma__*` that return a file or node's layout, styles, and a structured representation tuned for codegen.

**Discover the exact tool names at runtime** — do not hardcode them. List the available `mcp__figma__*` tools, then call the one that fetches a node/frame by `FILE_KEY` + `NODE_ID`. The MCP path is preferred because it returns design data already shaped for implementation (auto-layout, tokens, component names) rather than raw REST JSON you have to interpret.

### (b) REST fallback

Use REST when the MCP server is unavailable or you need a raw frame/image. The token goes in the `X-Figma-Token` **header**, never the URL.

```bash
# Whole file (structure + styles)
curl -s -H "X-Figma-Token: $FIGMA_TOKEN" \
  "https://api.figma.com/v1/files/$FILE_KEY" | jq '.document.children[].name'

# A specific frame/node (note: NODE_ID uses ':' here, not '-')
curl -s -H "X-Figma-Token: $FIGMA_TOKEN" \
  "https://api.figma.com/v1/files/$FILE_KEY/nodes?ids=$NODE_ID" | jq '.nodes'

# Rendered preview of one or more nodes (returns image URLs)
curl -s -H "X-Figma-Token: $FIGMA_TOKEN" \
  "https://api.figma.com/v1/images/$FILE_KEY?ids=$NODE_ID&format=png&scale=2"
```

Useful endpoints: `/v1/files/<FILE_KEY>` (full tree), `/v1/files/<FILE_KEY>/nodes?ids=<NODE_ID>` (one frame, cheaper), `/v1/images/<FILE_KEY>?ids=<NODE_ID>` (rendered PNG/SVG for visual comparison).

## URL parsing

Designers paste links like:

```
https://www.figma.com/design/AbC123dEfGhIj/Checkout-Flow?node-id=1234-5678
                              └── FILE_KEY ──┘             └─ node-id ─┘
```

- **FILE_KEY** is the path segment right after `/design/` (older links use `/file/` — same position).
- **node-id** in the URL is `-`-separated (`1234-5678`). The **API expects `:`** (`1234:5678`). Convert before passing to MCP tools or REST:

```bash
FILE_KEY="AbC123dEfGhIj"
NODE_ID="${URL_NODE_ID//-/:}"   # 1234-5678 -> 1234:5678
```

`connections.figma.files` may pre-list known files as `{ name, key }` entries. If the AC names a file by `name`, resolve its `key` there instead of asking for a URL. A bare URL with no `node-id` means the whole file/page — fetch the top-level frames and pick the one whose name matches the AC.

## What to extract for implementation

Pull from the frame and turn each item into a concrete implementation note, then map those notes back to AC items:

| Pull from design | Use for |
|------------------|---------|
| Auto-layout direction, gap, padding, alignment | Flex/stack structure and spacing |
| Sizing (fixed / hug / fill), constraints | Width/height behavior, responsiveness |
| Colors, fills, effects | Theming — match to existing tokens |
| Typography (family, size, weight, line-height) | Text styles — match to existing tokens |
| Component / layer names | Naming, and which existing component to reuse |
| Variables / design tokens | Token references, not literals |

**Prefer the project's existing design tokens and components over hardcoded values.** If the design specifies `#1A73E8` and the project has a `--color-primary` token of the same value, reference the token. Hardcode only when no token exists, and flag it for follow-up.

Produce a short **implementation checklist** keyed to the AC, e.g.:

```
AC-2 (button states): default/hover/disabled fills from frame 1234:5678;
  map to existing Button component variants; spacing 8px gap (token: space-2).
```

## Handoff discipline

- **AC is authoritative for WHAT; design is authoritative for HOW it looks.** When they agree, implement to both.
- **When design and AC conflict** — the frame shows a field the AC does not mention, or the AC requires behavior the design omits — do **not** silently follow the design over the AC. Use the **clarification loop** (see skill: `project-board-protocol`): post a `[DEV→PO ?]` comment with up to 3 numbered questions, add label `needs-clarification`, swap state back to `flow:refined`, and stop.
- Cite the specific frame (`FILE_KEY` + `NODE_ID`) in your `[DEV]` comment so QC and PO can open the same node.
- Design changes after an issue is `flow:ready-for-dev` are an AC/scope change, not a free DEV decision — route them through PO the same way.

## Secret hygiene

- `FIGMA_TOKEN` and `GITHUB_TOKEN` are secrets. Reference by `${ENV_NAME}` only.
- Never print, echo, or log a token value; never paste one into a URL or a comment; never commit one.
- Token in the `X-Figma-Token` header only — the curl examples above keep it out of the URL and out of shell history's argv where the header value is the only place it appears.
- Treat any image URL returned by `/v1/images` as short-lived and non-secret, but do not embed token-bearing requests in committed scripts.
