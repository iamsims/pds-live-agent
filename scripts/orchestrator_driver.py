"""Driver for the tool-optimization plan.

Invokes the 5 MCP tool functions directly (no transport) so the
orchestrator (me, the model) can step through each tool call.

Usage:
    python scripts/orchestrator_driver.py <tool> <json-args>

Tools (matching mcp_server.py):
    select_node       {"node": "geo"}
    list_missions     {"node": "geo"}
    list_dataset_dirs {"path": "mex/", "node": "geo", "filter": null}
    probe_datasets    {"paths": ["mex/mex-m-hrsc-5-refdr-dtm-v1/"], "node": "geo"}
    inspect_collections {"path": "...", "node": "geo", "max_subdirs": 20}

Also tracks an approximate HTTP-fetch counter via the loguru logs from
the underlying tools (see _http_count() — counts URL fetches in stderr).

Output is JSON to stdout; logs go to stderr.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from typing import Any

from loguru import logger

# Quiet noisy logs unless DRIVER_VERBOSE=1
import os
if not os.environ.get("DRIVER_VERBOSE"):
    logger.remove()
    logger.add(sys.stderr, level="WARNING")

from pydantic_code.tools.inspect_collections import pds_inspect_collections
from pydantic_code.tools.list_dataset_dirs import pds_list_dataset_dirs
from pydantic_code.tools.list_missions import pds_list_missions
from pydantic_code.tools.node_registry import get_node_config, list_available_nodes
from pydantic_code.tools.probe_datasets import pds_probe_datasets
from pydantic_code.tools.resolve_volume import pds_resolve_volume


def select_node(node: str) -> dict[str, Any]:
    try:
        config = get_node_config(node)
    except ValueError:
        return {"error": f"Unknown node: {node!r}", "available": list_available_nodes()}
    return {
        "node": config.node_id,
        "display_name": config.display_name,
        "base_url": config.base_url,
        "data_root": config.data_root,
        "has_mission_layer": config.has_mission_layer,
        "mission_count": len(config.missions),
        "workflow_notes": config.workflow_notes,
        "abbreviations": config.abbreviations,
    }


async def _dispatch(tool: str, args: dict[str, Any]) -> Any:
    if tool == "select_node":
        return select_node(**args)
    if tool == "list_missions":
        return pds_list_missions(**args).model_dump()
    if tool == "list_dataset_dirs":
        return (await pds_list_dataset_dirs(**args)).model_dump()
    if tool == "probe_datasets":
        return (await pds_probe_datasets(**args)).model_dump()
    if tool == "inspect_collections":
        return (await pds_inspect_collections(**args)).model_dump()
    if tool == "resolve_volume":
        return (await pds_resolve_volume(**args)).model_dump()
    raise SystemExit(f"unknown tool: {tool!r}")


def main() -> None:
    if len(sys.argv) < 3:
        print(__doc__)
        raise SystemExit(2)
    tool = sys.argv[1]
    args = json.loads(sys.argv[2])
    t0 = time.time()
    result = asyncio.run(_dispatch(tool, args))
    dt = time.time() - t0
    print(json.dumps({"tool": tool, "args": args, "elapsed_s": round(dt, 2), "result": result}, indent=2, default=str))


if __name__ == "__main__":
    main()
