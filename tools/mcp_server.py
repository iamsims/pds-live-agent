"""FastMCP server exposing PDS Geosciences tools over MCP.

Run standalone:
    python -m pydantic_code.mcp_server                 # stdio (default)
    python -m pydantic_code.mcp_server --transport sse  # SSE on :8001

The agent in ``pydantic_code.pds_geo_finder`` connects to this server via
``MCPServerStdio`` — it spawns this module as a subprocess automatically.
"""

from __future__ import annotations

from fastmcp import FastMCP

from pydantic_code.tools.browse import pds_geo_browse_directory
from pydantic_code.tools.holdings import pds_geo_search_holdings
from pydantic_code.tools.inspect_with_collections import pds_geo_inspect_with_collections

mcp = FastMCP("pds-geo-tools")


@mcp.tool(name="pds_geo_search_holdings")
async def pds_geo_search_holdings_tool(query: str, limit: int = 20) -> dict:
    """Fuzzy-search the GEO node's holdings index. The index contains only
    canonical dataset IDs (e.g. MEX-M-HRSC-5-REFDR-DTM-V1.0) — not science
    topics or geographic names. Search with mission abbreviations and
    instrument names. Returns dataset IDs with a mission_hint.

    Args:
        query: Mission/instrument terms to match against dataset IDs.
        limit: Max results (default 20, max 50).
    """
    result = await pds_geo_search_holdings(query=query, limit=limit)
    return result.model_dump()


@mcp.tool(name="pds_geo_browse")
async def pds_geo_browse_tool(path: str = "") -> dict:
    """List sub-directories and files at a path on https://pds-geosciences.wustl.edu/.

    Args:
        path: Path relative to the GEO root. Empty string lists the top-level
            mission directories. Use a trailing slash for sub-directories.
            "../" segments are not allowed.
    """
    result = await pds_geo_browse_directory(path=path)
    return result.model_dump()


@mcp.tool(name="pds_geo_inspect_with_collections")
async def pds_geo_inspect_with_collections_tool(path: str, max_subdirs: int = 20) -> dict:
    """Inspect a path AND, when a PDS4 bundle is present, also fetch one level of collections.

    Returns the bundle/voldesc labels at the input path AND any
    collection_*.xml/.lblx labels found one directory below — both in a
    single tool call. For PDS3 volumes, returns voldesc labels and
    collections is empty.

    Args:
        path: Bundle (or volume) directory path on the GEO node.
        max_subdirs: Cap on bundle sub-dirs to walk for collections (default 20).
    """
    result = await pds_geo_inspect_with_collections(path=path, max_subdirs=max_subdirs)
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
