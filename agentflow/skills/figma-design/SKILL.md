---
name: figma-design
description: Pulls design context from Figma during UI work and maps it to an issue's acceptance criteria — gate on connections.figma, prefer the official Figma MCP server (get_metadata → get_design_context → get_variable_defs → get_screenshot → get_code_connect_map) with a PAT/REST fallback, then translate (never paste) the result into the implementation. Use when a DEV issue touches a visual surface and its AC references a Figma frame, file, or figma.com link.
---

# Figma Design Handoff

How the **DEV** agent fetches design context when an issue touches a visual surface (any `component/<surface>` whose declared surface in `surfaces:` has a UI — web, admin, mobile, …) and the AC references a Figma design.

**Design informs HOW a thing looks and lays out; the issue's AC defines WHAT must be true.** The two are not interchangeable — see *Handoff discipline*. Per Figma's own guidance, the MCP server only provides *structured context + a code starting point*; **you adapt it to this codebase — you never paste its output verbatim.**

## Gate before use

Figma is a connection like any other — read its wiring in `.claude/agentflow.yaml` first (see skill: `setup-agentflow` for the full connection/env spec). Do **not** call any Figma tool or REST endpoint unless `connections.figma.enabled: true` **and** at least one access path below is actually available:

- **Official Figma MCP server (preferred)** — available when the `figma` MCP server is connected and OAuth-authenticated. Verify with a `whoami` call (it returns the signed-in identity); if it errors, the server is not authenticated.
- **PAT fallback** — available when the var named by `connections.figma.auth.token_env` (e.g. `FIGMA_TOKEN`) is present, for the legacy Framelink server / REST path.

```bash
# Gate check — connection on?
yq '.connections.figma.enabled' .claude/agentflow.yaml      # → true
# then probe a path: official MCP (whoami) OR a present PAT for the fallback
[ -n "${FIGMA_TOKEN:-}" ] && echo "PAT path available" || echo "PAT absent — needs official MCP"
```

If the gate fails (disabled, or no path available) → **skip design lookups entirely** and build from the issue's AC. Note it in your `[DEV]` comment (e.g. `design lookup skipped: figma not configured — built from AC only`) so reviewers know the implementation was AC-driven. **Never block dev work waiting on an optional connection.**

## Path A — official Figma MCP server (preferred)

The official server (Figma's Dev Mode MCP) authenticates via **OAuth** — there is **no `FIGMA_TOKEN`/`FIGMA_API_KEY`/`X-Figma-Token`** on this path. It exposes stable, documented tools; **call them by their fully-qualified names** (do not "discover at runtime" — the names are stable). The design-to-code flow for a frame:

| Step | Tool | Use for |
|------|------|---------|
| 1. Outline a large design | `get_metadata` | Sparse XML of node IDs / names / types / sizes. Call with no `nodeId` to list the file's top-level pages, then drill in. Cheap — use it to find the right node before pulling full context. |
| 2. Pull design context | `get_design_context` | The primary design→code tool. Returns reference code (**React + Tailwind by default**), a screenshot, and metadata for the node. Treat it as *context to translate*, not code to paste. |
| 3. Map tokens | `get_variable_defs` | The variables/styles used in the selection (colors, spacing, typography), e.g. `{ 'color/primary': '#1A73E8' }`. Map these to the project's existing tokens. |
| 4. Visual check | `get_screenshot` | A PNG of the node to diff your implementation against for layout fidelity. |
| 5. Reuse real components | `get_code_connect_map` | Returns `{ nodeId: { componentName, source, snippet, … } }` — the actual code component a Figma node maps to. **Prefer the mapped component over fresh markup.** |

**Prompt the tools with project specifics** (Figma's "write effective prompts" guidance): name the project's framework, the target component directory, and the layout system, so the output matches this codebase rather than the React+Tailwind default. Examples to fold into how you call `get_design_context`:

- Framework: *"generate this selection in `<the project's framework>`"* (e.g. Vue, SwiftUI, plain HTML+CSS).
- Reuse: *"using components from `<surfaces.<surface>.path>/components`"*.
- Tokens not literals: when you want variables rather than code, ask explicitly — *"get the variable names and values for this selection"* (otherwise the agent may return code instead).

**Remote vs desktop:** the **remote** server (`https://mcp.figma.com/mcp`) is **link-based** — pass the figma.com frame/layer URL (or its `fileKey` + `nodeId`); it extracts the node-id itself. **Selection-based** prompting ("my current selection") works only with the **desktop** server. AgentFlow runs headless, so always pass an explicit URL/node from the AC, never "the selection".

**Code Connect:** if the project has Code Connect set up, set the framework label so the right mapping comes back (pass `clientFrameworks` matching the Code Connect label, e.g. `React`, `SwiftUI`). Authoring Code Connect mappings is out of scope for DEV here — defer to Figma's `figma-code-connect` skill if the project wants to add them.

## Path B — PAT / REST fallback (legacy)

<details>
<summary>Framelink server or Figma REST — for headless/enterprise setups that can't complete the OAuth flow. Uses a separate <code>FIGMA_TOKEN</code> PAT (declared independently under <code>env:</code>), NOT the official server.</summary>

This is a **separate integration** from the official server above. Use it only when the official MCP path is unavailable and `FIGMA_TOKEN` is set. The token goes in the `X-Figma-Token` **header**, never the URL.

```bash
# Whole file (structure + styles)
curl -s -H "X-Figma-Token: $FIGMA_TOKEN" \
  "https://api.figma.com/v1/files/$FILE_KEY" | jq '.document.children[].name'

# A specific frame/node (cheaper) — NODE_ID uses ':' here, not '-'
curl -s -H "X-Figma-Token: $FIGMA_TOKEN" \
  "https://api.figma.com/v1/files/$FILE_KEY/nodes?ids=$NODE_ID" | jq '.nodes'

# Rendered preview of one or more nodes (returns image URLs)
curl -s -H "X-Figma-Token: $FIGMA_TOKEN" \
  "https://api.figma.com/v1/images/$FILE_KEY?ids=$NODE_ID&format=png&scale=2"
```

Useful endpoints: `/v1/files/<FILE_KEY>` (full tree), `/v1/files/<FILE_KEY>/nodes?ids=<NODE_ID>` (one frame), `/v1/images/<FILE_KEY>?ids=<NODE_ID>` (rendered PNG/SVG). The legacy Framelink MCP server (`figma-developer-mcp`) reads the same `FIGMA_TOKEN` as `FIGMA_API_KEY` and exposes `mcp__figma__*` tools — discover those at runtime if that server is the one wired in `.mcp.json`.
</details>

## URL parsing

Designers paste links like:

```
https://www.figma.com/design/AbC123dEfGhIj/Checkout-Flow?node-id=1234-5678
                              └── FILE_KEY ──┘             └─ node-id ─┘
```

- **FILE_KEY** is the path segment right after `/design/` (older links use `/file/` — same position). For a branch URL `…/design/<key>/branch/<branchKey>/…`, use the **branchKey** as the file key.
- **node-id** in the URL is `-`-separated (`1234-5678`). The **official MCP tools accept both `1234-5678` and `1234:5678`**; the **REST API requires `:`** (`1234:5678`). Convert for the REST fallback:

```bash
FILE_KEY="AbC123dEfGhIj"
NODE_ID="${URL_NODE_ID//-/:}"   # 1234-5678 -> 1234:5678  (only needed for Path B/REST)
```

`connections.figma.files` may pre-list known files as `{ name, key }` entries. If the AC names a file by `name`, resolve its `key` there instead of asking for a URL. A bare URL with no `node-id` means the whole file/page — use `get_metadata` (or fetch top-level frames) and pick the one whose name matches the AC.

## What to extract for implementation

Turn each item into a concrete implementation note, then map the notes back to AC items:

| Pull from design | Use for |
|------------------|---------|
| Auto-layout direction, gap, padding, alignment | Flex/stack structure and spacing |
| Sizing (fixed / hug / fill), constraints | Width/height behavior, responsiveness |
| Colors, fills, effects (`get_variable_defs`) | Theming — match to existing tokens |
| Typography (family, size, weight, line-height) | Text styles — match to existing tokens |
| Component / layer names + `get_code_connect_map` | Which existing component to reuse |
| Variables / design tokens | Token references, not literals |

**Prefer the project's existing design tokens and components over hardcoded values.** If the design specifies `#1A73E8` and the project has a `--color-primary` token of the same value, reference the token. Hardcode only when no token exists, and flag it for follow-up.

Produce a short **implementation checklist** keyed to the AC, e.g.:

```
AC-2 (button states): default/hover/disabled fills from frame 1234:5678;
  map to existing Button component (get_code_connect_map → src/ui/Button.tsx);
  spacing 8px gap (token: space-2 via get_variable_defs).
```

## Handoff discipline

- **AC is authoritative for WHAT; design is authoritative for HOW it looks.** When they agree, implement to both.
- **When design and AC conflict** — the frame shows a field the AC does not mention, or the AC requires behavior the design omits — do **not** silently follow the design over the AC. Use the **clarification loop** (see skill: `project-board-protocol`): post a `[DEV→PO ?]` comment with up to 3 numbered questions, add label `needs-clarification`, swap state back to `flow:refined`, and stop.
- Cite the specific frame (`FILE_KEY` + `NODE_ID`) in your `[DEV]` comment so QC and PO can open the same node.
- Design changes after an issue is `flow:ready-for-dev` are an AC/scope change, not a free DEV decision — route them through PO the same way.

## Secret hygiene

On the official OAuth path there is **no Figma token to protect**. On the PAT fallback, `FIGMA_TOKEN` is a secret: reference it by `${FIGMA_TOKEN}` only, keep it in the `X-Figma-Token` header (never the URL), and never print, echo, log, or commit it. Full rules: skill `setup-agentflow` → *Secret hygiene*.
