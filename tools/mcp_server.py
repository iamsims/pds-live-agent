"""FastMCP server exposing PDS node tools over MCP.

Run standalone:
    python -m pydantic_code.tools.mcp_server                 # stdio (default)
    python -m pydantic_code.tools.mcp_server --transport sse  # SSE on :8001

The agent in ``pydantic_code.live_finder`` connects to this server via
``MCPServerStdio`` — it spawns this module as a subprocess automatically.

Tools (5):
    0. pds_select_node          — get node-specific context (abbreviations, workflow)
    1. pds_list_missions        — mission list for a node (no HTTP for hardcoded nodes)
    2. pds_list_dataset_dirs    — list sub-dirs under a path (cheap HTTP)
    3. pds_probe_datasets       — probe specific paths for PDS labels (recursive leaf-find)
    4. pds_inspect_collections  — scan PDS4 bundle subdirs for collection labels
"""

from __future__ import annotations

from fastmcp import FastMCP

from pydantic_code.tools.inspect_collections import pds_inspect_collections
from pydantic_code.tools.list_dataset_dirs import pds_list_dataset_dirs
from pydantic_code.tools.list_missions import pds_list_missions
from pydantic_code.tools.node_registry import get_node_config, list_available_nodes
from pydantic_code.tools.probe_datasets import pds_probe_datasets

mcp = FastMCP("pds-tools")


# ------------------------------------------------------------------
# Tool 0: select node (get node-specific context)
# ------------------------------------------------------------------

@mcp.tool(name="pds_select_node")
def pds_select_node_tool(node: str) -> dict:
    """Select a PDS node and get its workflow context.

    Call this FIRST to get node-specific guidance (missions, abbreviations,
    workflow tips). Then use the other tools with the same node parameter.

    Args:
        node: PDS node identifier. One of: "geo", "ppi", "lroc", "rms", "sbn", "atm".
    """
    try:
        config = get_node_config(node)
    except ValueError:
        return {
            "error": f"Unknown node: {node!r}",
            "available_nodes": list_available_nodes(),
        }
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


# ------------------------------------------------------------------
# Tool 1: list missions (hardcoded, instant)
# ------------------------------------------------------------------

@mcp.tool(name="pds_list_missions")
def pds_list_missions_tool(node: str = "geo") -> dict:
    """List all known missions on a PDS node with descriptions.

    Returns mission names and their instruments. No HTTP call needed.

    For GEO: names are top-level directory paths (e.g. mex/, mro/).
    For PPI/RMS/SBN/ATM: names are filter keywords to use with list_dataset_dirs
             (e.g. filter='MESS' for MESSENGER, filter='cassini' for PPI;
              filter='COISS' for RMS Cassini ISS; filter='MROM' for ATM
              Mars Climate Sounder; filter='orex' for SBN OSIRIS-REx).
    For LROC: returns an empty list — use list_dataset_dirs directly.

    Args:
        node: PDS node identifier ("geo", "ppi", "lroc", "rms", "sbn", "atm"). Default "geo".
    """
    result = pds_list_missions(node=node)
    return result.model_dump()


# ------------------------------------------------------------------
# Tool 2: list dataset directories (cheap HTTP)
# ------------------------------------------------------------------

@mcp.tool(name="pds_list_dataset_dirs")
async def pds_list_dataset_dirs_tool(
    path: str,
    node: str = "geo",
    filter: str | None = None,
) -> dict:
    """List sub-directory names under a path on a PDS node.

    Cheap HTTP call — fetches the directory listing only, no label parsing.
    Each directory gets a pds_hint ('PDS3', 'PDS4', or null) inferred from
    its naming convention.

    Use this after list_missions to see what datasets exist under a mission
    (e.g. path="mex/" for GEO), or directly for flat nodes:
      - PPI:  path="data/" with filter="cassini"
      - LROC: path="data/" (only 3 datasets, no filter needed)
      - RMS:  path="holdings/volumes/" with filter="COISS" (PDS3),
              path="pds4/bundles/" (PDS4)
      - ATM:  path="PDS/data/" with filter="MROM" (PDS3),
              path="PDS/data/PDS4/" (PDS4)
      - SBN:  path="holdings/" with filter="<mission_key>" (may 403 intermittently;
              agent falls back to abbreviation table per workflow notes).

    Args:
        path: Directory path to list (e.g. "mex/" for GEO, "data/" for PPI).
        node: PDS node identifier ("geo", "ppi", "lroc", "rms", "sbn", "atm"). Default "geo".
        filter: Optional case-insensitive substring filter on directory names.
            Useful for flat nodes with many entries (e.g. PPI has ~767 datasets).
    """
    result = await pds_list_dataset_dirs(path=path, node=node, filter=filter)
    return result.model_dump()


# ------------------------------------------------------------------
# Tool 3: probe datasets (recursive leaf-finding)
# ------------------------------------------------------------------

@mcp.tool(name="pds_probe_datasets")
async def pds_probe_datasets_tool(paths: list[str], node: str = "geo") -> dict:
    """Probe specific dataset directories for PDS labels.

    For each path, finds the leaf node containing voldesc.cat/sfd (PDS3) or
    bundle*.xml/lblx (PDS4) by recursing up to one level deep. Returns the
    dataset_id, title, PDS version, and slimmed label fields for each.

    Accepts multiple paths to batch probes in one call (max 20).
    Hybrid directories (both PDS3 and PDS4) produce multiple entries.

    Args:
        paths: List of dataset directory paths to probe
               (e.g. ["mex/mex-m-hrsc-5-refdr-dtm-v1/"] for GEO,
                ["data/cassini-caps-calibrated/"] for PPI).
        node: PDS node identifier ("geo", "ppi", "lroc", "rms", "sbn", "atm"). Default "geo".
    """
    result = await pds_probe_datasets(paths=paths, node=node)
    return result.model_dump()


# ------------------------------------------------------------------
# Tool 4: inspect collections (PDS4 bundle drill-down)
# ------------------------------------------------------------------

@mcp.tool(name="pds_inspect_collections")
async def pds_inspect_collections_tool(
    path: str,
    node: str = "geo",
    max_subdirs: int = 20,
) -> dict:
    """Scan subdirs of a PDS4 bundle for collection labels.

    Walks the immediate sub-directories of the given bundle path (skipping
    document/, index/, catalog/, browse/, checksums/) and returns every
    collection label found with its logical_identifier and title.

    Use this after probe_datasets confirms a PDS4 bundle exists, and you
    need collection-level identifiers.

    Args:
        path: PDS4 bundle directory path on the node.
        node: PDS node identifier ("geo", "ppi", "lroc", "rms", "sbn", "atm"). Default "geo".
        max_subdirs: Cap on sub-dirs to walk for collections (default 20).
    """
    result = await pds_inspect_collections(path=path, max_subdirs=max_subdirs, node=node)
    return result.model_dump()


if __name__ == "__main__":
    import argparse
    import os

    parser = argparse.ArgumentParser(description="Run PDS tools MCP server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default=os.getenv("MCP_TRANSPORT", "stdio"),
        help="Transport type (default: stdio, or MCP_TRANSPORT env var)",
    )
    parser.add_argument(
        "--host",
        default=os.getenv("MCP_HOST", "127.0.0.1"),
        help="Host to bind to for SSE (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("MCP_PORT", "8001")),
        help="Port for SSE transport (default: 8001)",
    )
    args = parser.parse_args()

    if args.transport == "sse":
        mcp.run(transport="sse", host=args.host, port=args.port)
    else:
        mcp.run()
