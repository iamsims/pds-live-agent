"""FastMCP server exposing PDS Geosciences tools over MCP.

Run standalone:
    python -m pydantic_code.tools.mcp_server                 # stdio (default)
    python -m pydantic_code.tools.mcp_server --transport sse  # SSE on :8001

The agent in ``pydantic_code.pds_geo_finder`` connects to this server via
``MCPServerStdio`` — it spawns this module as a subprocess automatically.

Tools (4):
    1. pds_geo_list_missions     — hardcoded mission list (no HTTP)
    2. pds_geo_list_dataset_dirs — list sub-dirs under a mission path (cheap HTTP)
    3. pds_geo_probe_datasets    — probe specific paths for PDS labels (recursive leaf-find)
    4. pds_geo_inspect_collections — scan PDS4 bundle subdirs for collection labels
"""

from __future__ import annotations

from fastmcp import FastMCP

from pydantic_code.tools.inspect_collections import pds_geo_inspect_collections
from pydantic_code.tools.list_dataset_dirs import pds_geo_list_dataset_dirs
from pydantic_code.tools.list_missions import pds_geo_list_missions
from pydantic_code.tools.probe_datasets import pds_geo_probe_datasets

mcp = FastMCP("pds-geo-tools")


# ------------------------------------------------------------------
# Tool 1: list missions (hardcoded, instant)
# ------------------------------------------------------------------

@mcp.tool(name="pds_geo_list_missions")
def pds_geo_list_missions_tool() -> dict:
    """List all known mission directories on the GEO node with descriptions.

    Returns mission names (e.g. m2020, msl, mro, mex) and their instruments.
    No HTTP call needed — the list is hardcoded and stable.

    Use this first to identify which mission directory to explore.
    """
    result = pds_geo_list_missions()
    return result.model_dump()


# ------------------------------------------------------------------
# Tool 2: list dataset directories (cheap HTTP)
# ------------------------------------------------------------------

@mcp.tool(name="pds_geo_list_dataset_dirs")
async def pds_geo_list_dataset_dirs_tool(path: str) -> dict:
    """List sub-directory names under a mission path on the GEO node.

    Cheap HTTP call — fetches the directory listing only, no label parsing.
    Each directory gets a pds_hint ('PDS3', 'PDS4', or null) inferred from
    its naming convention.

    Use this after list_missions to see what datasets exist under a mission
    (e.g. path="mex/"). Then pick specific directories to probe.

    Args:
        path: Mission directory path (e.g. "mex/", "mro/", "m2020/").
    """
    result = await pds_geo_list_dataset_dirs(path=path)
    return result.model_dump()


# ------------------------------------------------------------------
# Tool 3: probe datasets (recursive leaf-finding)
# ------------------------------------------------------------------

@mcp.tool(name="pds_geo_probe_datasets")
async def pds_geo_probe_datasets_tool(paths: list[str]) -> dict:
    """Probe specific dataset directories for PDS labels.

    For each path, finds the leaf node containing voldesc.cat/sfd (PDS3) or
    bundle*.xml/lblx (PDS4) by recursing up to one level deep. Returns the
    dataset_id, title, PDS version, and slimmed label fields for each.

    Accepts multiple paths to batch probes in one call (max 20).
    Hybrid directories (both PDS3 and PDS4) produce multiple entries.

    Use this after list_dataset_dirs — pick the relevant directory names
    and probe them here.

    Args:
        paths: List of dataset directory paths to probe
               (e.g. ["mex/mex-m-hrsc-5-refdr-dtm-v1/", "mex/mex-m-omega-4-srdr-v3/"]).
    """
    result = await pds_geo_probe_datasets(paths=paths)
    return result.model_dump()


# ------------------------------------------------------------------
# Tool 4: inspect collections (PDS4 bundle drill-down)
# ------------------------------------------------------------------

@mcp.tool(name="pds_geo_inspect_collections")
async def pds_geo_inspect_collections_tool(path: str, max_subdirs: int = 20) -> dict:
    """Scan subdirs of a PDS4 bundle for collection labels.

    Walks the immediate sub-directories of the given bundle path (skipping
    document/, index/, catalog/, browse/, checksums/) and returns every
    collection label found with its logical_identifier and title.

    Use this after probe_datasets confirms a PDS4 bundle exists, and you
    need collection-level identifiers.

    Args:
        path: PDS4 bundle directory path on the GEO node.
        max_subdirs: Cap on sub-dirs to walk for collections (default 20).
    """
    result = await pds_geo_inspect_collections(path=path, max_subdirs=max_subdirs)
    return result.model_dump()


if __name__ == "__main__":
    import argparse
    import os

    parser = argparse.ArgumentParser(description="Run PDS GEO tools MCP server")
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
