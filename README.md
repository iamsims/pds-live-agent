# PDS Dataset Discovery Agent

Agentic system for finding NASA Planetary Data System (PDS) datasets from natural-language research questions. Uses pydantic-ai agents with hosted MCP tool servers to navigate live PDS archive trees and faceted search APIs.

## Setup

```bash
git clone <repo-url> pydantic_code
cd pydantic_code
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env   # then add your API keys
```

## Run

```bash
python demo.py
```

See [live_finder/README.md](live_finder/README.md) for detailed usage and batch mode.

## Codebase structure

### Core

| File | Purpose |
|---|---|
| `finder.py` | Catalog-mode agent factory (`build_finder`) with the shared output schema; live discovery lives in `live_finder/` |
| `live_finder/pds_finder.py` | Live finder: `LiveFinder` (router + per-node layered worker) and the `run_live_query` / `run_live_batch` wrappers |
| `live_finder/prompts.py` | Router prompt + Stage 1 / Stage 2 worker prompt builders |
| `live_finder/stage2.py` | Per-node Stage 2 toolset specs (prompt block + MCP allow-list) |
| `live_finder/transports.py` | Hosted Stage 1 / Stage 2 MCP transport builders |
| `catalog_finder/pds_catalog_finder.py` | Catalog finder: single-agent mode using pre-scraped catalog search (alpha/akd-labs approach) |
| `tools/node_registry.py` | Per-node configuration: workflow steps, abbreviations, missions, base URLs for all PDS nodes |

### MCP tools (`tools/`)

All tools are **already hosted on remote MCP servers** (FastMCP Cloud, streamable HTTP) — nothing to deploy locally. The agent connects at runtime; you only need `FAST_MCP_AUTH`.

Stage 1 tools — live HTTP directory walking:

| File | Tool |
|---|---|
| `tools/mcp_server.py` | FastMCP server exposing all 5 Stage 1 tools |
| `tools/list_missions.py` | `pds_list_missions` — enumerate mission directories at a node |
| `tools/list_dataset_dirs.py` | `pds_list_dataset_dirs` — list subdirectories under a path |
| `tools/probe_datasets.py` | `pds_probe_datasets` — batch-probe paths for PDS labels |
| `tools/inspect_collections.py` | `pds_inspect_collections` — scan PDS4 bundle subdirs for collections |
| `tools/resolve_volume.py` | `pds_resolve_volume` — resolve numbered volume siblings |
| `tools/client.py` | Shared async HTTP client for archive directory listings |
| `tools/parsers.py` | HTML/label parsers for PDS3 `voldesc.cat` and PDS4 `bundle*.xml` |

### Evaluation & dev scripts (`scripts/`)

| File | Purpose |
|---|---|
| `scripts/run_eval.py` | Full eval harness: runs layered + catalog side-by-side, produces `comparison.json` |
| `scripts/eval_helpers.py` | Shared helpers: trace extraction, match checking, usage normalization |

### Data

| File | Purpose |
|---|---|
| `data/gold_datasets.xlsx` | Gold dataset: 96 queries with expected PDS identifiers |
| `data/pds_node_classification.xlsx` | Node classification for queries across all PDS nodes |


The final evaluation data exists in output/eval_20260512_203651. 