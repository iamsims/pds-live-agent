# PDS Dataset Discovery Agent

Agentic system for finding NASA Planetary Data System (PDS) datasets from natural-language research questions. Uses pydantic-ai agents with hosted MCP tool servers to navigate live PDS archive trees and faceted search APIs.

See [live_finder/README.md](live_finder/README.md) for setup and usage instructions.

## Codebase structure

### Core

| File | Purpose |
|---|---|
| `finder.py` | Unified agent factory — builds a pydantic-ai agent in `live` or `catalog` mode with shared output schema |
| `live_finder/pds_finder.py` | Live finder: router agent, worker agent, `LayeredFinder`, system prompt builder, MCP wiring |
| `catalog_finder/pds_catalog_finder.py` | Catalog finder: single-agent mode using pre-scraped catalog search (alpha/akd-labs approach) |
| `tools/node_registry.py` | Per-node configuration: workflow steps, abbreviations, missions, base URLs for all PDS nodes |

### MCP tools (`tools/`)

Stage 1 tools — live HTTP directory walking, served via `tools/mcp_server.py`:

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
| `scripts/test_nodes.py` | Per-node smoke tests and prompt tuning (blind eval against gold dataset) |

### Data

| File | Purpose |
|---|---|
| `data/gold_datasets.xlsx` | Gold dataset: 96 queries with expected PDS identifiers |
| `data/pds_node_classification.xlsx` | Node classification for queries across all PDS nodes |
