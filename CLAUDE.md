# Repository guide for Claude

This is a multi-node PDS (Planetary Data System) dataset-discovery agent. The
agent talks to 6 NASA PDS discipline nodes (GEO, PPI, LROC, RMS, SBN, ATM) via
5 shared MCP tools served by [tools/mcp_server.py](tools/mcp_server.py).

## Where the prompts live

The single-node system prompt is **dynamically composed** at runtime by
[`_build_single_node_prompt`](live_finder/pds_finder.py) from two sources:

1. **General scaffolding** (universal across nodes) — hardcoded in the builder:
   - Intro line
   - PDS3 vs PDS4 conventions
   - Tool list (the 5 MCP tools)
   - Critical rules (every-query-needs-a-candidate, prefer calibrated, etc.)

2. **Node-specific blocks** (per-node) — read from `NodeConfig` in
   [tools/node_registry.py](tools/node_registry.py):
   - `display_name`, `base_url`
   - `workflow_notes` — directory layout + caveats (HTTP 403, hybrid trees, …)
   - `abbreviations` — mission/instrument abbreviation table
   - `workflow_steps` — the numbered Step-1/Step-2/… plan the agent follows

The multi-node routing prompt (`_MULTI_NODE_SYSTEM_PROMPT`) is separate and
lives in the same file.

## Per-node optimization protocol — IMPORTANT

When tuning the agent's behaviour for **one specific node** (e.g. fixing an
SBN failure mode, adding an LROC abbreviation, refining the RMS workflow):

- **DO** edit only that node's entry in [tools/node_registry.py](tools/node_registry.py).
  The relevant fields are `workflow_notes`, `abbreviations`, `workflow_steps`,
  and `missions`. There is one `_<NODE>_WORKFLOW_STEPS` constant per node —
  edit only the one for the node you're tuning.
- **DO NOT** modify `_build_single_node_prompt` or `_MULTI_NODE_SYSTEM_PROMPT`
  in [live_finder/pds_finder.py](live_finder/pds_finder.py) for a per-node
  optimization. Those are universal scaffolding and changes there affect every
  node.
- **DO NOT** add per-node `if node == "..."` branches to the builder. If a
  node needs custom behaviour, encode it in that node's `workflow_steps`
  string in the registry instead.

The builder is intentionally a flat template with no per-node branching —
keep it that way. New per-node behaviour goes into the registry, not the
builder.

### Only touch the general prompt when

- The change applies to **every** node (e.g. updating the tool list when a new
  shared MCP tool is added, refining the universal PDS3-vs-PDS4 description,
  or changing a critical rule that should bind all nodes).
- You are explicitly asked to change cross-node behaviour.

If you're unsure whether a change is per-node or universal, ask.

## Adding a new node

1. Add a `_<NEW>_MISSIONS`, `_<NEW>_ABBREVIATIONS`, `_<NEW>_WORKFLOW`, and
   `_<NEW>_WORKFLOW_STEPS` set of constants in
   [tools/node_registry.py](tools/node_registry.py).
2. Add a new entry to `NODE_REGISTRY`.
3. The builder, the MCP tools, and the dispatcher all pick it up automatically
   — no other files need edits unless the new node has a tool-level quirk
   (e.g. a non-Apache directory listing format) that the existing tools
   can't handle.
