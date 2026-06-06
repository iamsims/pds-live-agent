# PDS Live Finder

A two-stage agentic dataset-discovery system for NASA's Planetary Data System (PDS). Given a natural-language research question, the finder locates relevant PDS datasets by navigating the live archive directory trees over HTTP.

All tools are **hosted on remote MCP servers** (FastMCP Cloud, streamable HTTP) — there is nothing to deploy locally. The agent connects to the hosted tools at runtime; you only need API keys.

| Server | URL | Tools |
|---|---|---|
| Stage 1 — Directory walking | `https://fuzzy-aquamarine-swordtail.fastmcp.app/mcp` | 5 tools: `pds_list_missions`, `pds_list_dataset_dirs`, `pds_probe_datasets`, `pds_inspect_collections`, `pds_resolve_volume` |
| Stage 2 — Faceted APIs | `https://natural-bronze-stingray.fastmcp.app/mcp` | ~20 tools: ODE, OPUS, IMG, SBN, PDS4 Registry (filtered per node) |

## Architecture

```
Query
  │
  ▼
┌─────────────────┐
│  Router Agent    │  Tool-less classifier — maps the query to a PDS
│  (no tools)      │  discipline node based on keywords and domain cues.
└────────┬────────┘
         │  node id
         ▼
┌─────────────────────────────────────────────────────┐
│  Worker Agent                                        │
│                                                      │
│  Stage 1: Directory Walking (5 tools)                │
│    pds_list_missions · pds_list_dataset_dirs          │
│    pds_probe_datasets · pds_inspect_collections       │
│    pds_resolve_volume                                 │
│                                                      │
│  Stage 2: Node-specific Faceted APIs                 │
│    ODE · OPUS · IMG · SBN · PDS4 Registry            │
│    (filtered per node — worker only sees its tools)   │
└──────────────────────────────────────────────────────┘
         │
         ▼
  Ranked dataset candidates (dataset_id, path, reasoning)
```

**Stage 1** walks the archive tree via the hosted MCP server, probing directories for PDS3 `voldesc.cat` or PDS4 `bundle*.xml` labels to identify datasets.

**Stage 2** refines or rescues Stage 1 results using deeper faceted-search APIs (e.g. ODE for spatial/instrument filtering, OPUS for ring observations). The worker escalates to Stage 2 only when needed (granule-level queries, spatial filters, ambiguous candidates, or when Stage 1 can't reach the archive).

## Quick start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Set environment variables

```bash
export OPENAI_API_KEY="sk-..."        # LLM API key (default model: openai:gpt-5.2)
export FAST_MCP_AUTH="your-token"      # Bearer token for the hosted MCP servers
```

### 3. Run a query

```python
import asyncio
from pydantic_code.live_finder.pds_finder import run_layered_query

async def main():
    decision, output = await run_layered_query(
        "What calibrated spectral data exists for Saturn's rings from Cassini UVIS?"
    )
    print(f"Routed to: {decision.primary_node} ({decision.confidence})")
    for c in output.candidates:
        print(f"  {c.dataset_id}  {c.path}")
        print(f"    {c.reasoning}")

asyncio.run(main())
```

The layered mode handles routing automatically — no need to specify a node. The router classifies the query, then the worker navigates the appropriate archive with Stage 1 + Stage 2 tools.

For batch usage, use `LayeredFinder` as an async context manager to reuse MCP connections across queries:

```python
from pydantic_code.live_finder.pds_finder import LayeredFinder

async with LayeredFinder() as lf:
    for q in queries:
        decision, output = await lf.run(q)
```

## Running the evaluation

```bash
.venv/bin/python -m pydantic_code.scripts.run_eval --limit 5
```

Output goes to `output/eval_<timestamp>/` with per-query results (`.jsonl`) and full agent traces (`.json`).

## Configuration

| Parameter | Default | Description |
|---|---|---|
| `model` | `openai:gpt-5.2` | Any pydantic-ai model string |
| `reasoning_effort` | `high` | `low` / `medium` / `high` (for reasoning models) |
| `fallback_node` | `geo` | Node used when the router returns `primary_node=null` |

Override MCP server URLs via environment variables:

| Variable | Default |
|---|---|
| `PDS_STAGE1_MCP_URL` | `https://fuzzy-aquamarine-swordtail.fastmcp.app/mcp` |
| `PDS_STAGE2_MCP_URL` | `https://natural-bronze-stingray.fastmcp.app/mcp` |
