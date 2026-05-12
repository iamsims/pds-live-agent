"""FastMCP server exposing PDS node tools over MCP.

Run standalone:
    python -m pydantic_code.tools.mcp_server                 # stdio (default)
    python -m pydantic_code.tools.mcp_server --transport sse  # SSE on :8001

The agent in ``pydantic_code.live_finder`` connects to this server via
``MCPServerStdio`` — it spawns this module as a subprocess automatically.

Tools (5):
    1. pds_list_missions        — mission list for a node (no HTTP for hardcoded nodes)
    2. pds_list_dataset_dirs    — list sub-dirs under a path (cheap HTTP)
    3. pds_probe_datasets       — probe specific paths for PDS labels (recursive leaf-find)
    4. pds_inspect_collections  — scan PDS4 bundle subdirs for collection labels
    5. pds_resolve_volume       — find which child of a volume-set carries which DATA_SET_ID
"""

from __future__ import annotations

import functools
import inspect

from fastmcp import FastMCP

from pydantic_code.tools.inspect_collections import pds_inspect_collections
from pydantic_code.tools.list_dataset_dirs import pds_list_dataset_dirs
from pydantic_code.tools.list_missions import pds_list_missions
from pydantic_code.tools.probe_datasets import pds_probe_datasets
from pydantic_code.tools.resolve_volume import pds_resolve_volume

mcp = FastMCP("pds-tools")


# ------------------------------------------------------------------
# Cross-tool kwarg absorber
# ------------------------------------------------------------------
#
# Calling agents (and the FastMCP Cloud inspector UI) sometimes leak
# kwargs from one tool's call into the next — e.g. ``paths=[]`` from a
# prior ``pds_probe_datasets`` call ends up forwarded to
# ``pds_inspect_collections``. FastMCP's pydantic-backed validation
# rejects those with ``Unexpected keyword argument`` 422s.
#
# Rather than patching each tool by hand whenever a new leak surfaces,
# this decorator augments every tool's signature with the union of all
# sibling-tool kwargs. Extras are accepted, silently dropped, and never
# reach the underlying function. FastMCP's schema gen then advertises
# the augmented surface, and pydantic's validate_call accepts the call.

_CROSS_TOOL_KWARGS: dict[str, tuple[type, object]] = {
    "path":            (str | None, None),
    "paths":           (list[str] | None, None),
    "filter":          (str | None, None),
    "max_subdirs":     (int | None, None),
    "volume_set_path": (str | None, None),
    "dataset_id_hint": (str | None, None),
    "sample":          (int | None, None),
}


def _absorb_cross_tool_kwargs(fn):
    """Add every kwarg in _CROSS_TOOL_KWARGS that fn doesn't natively take.

    Real parameters keep their original types / defaults. Extras become
    keyword-only with default None and are dropped before fn runs.
    """
    sig = inspect.signature(fn)
    have = set(sig.parameters)
    new_params = list(sig.parameters.values())
    extra_anns: dict[str, type] = {}
    for name, (ann, default) in _CROSS_TOOL_KWARGS.items():
        if name not in have:
            new_params.append(inspect.Parameter(
                name, inspect.Parameter.KEYWORD_ONLY,
                default=default, annotation=ann,
            ))
            extra_anns[name] = ann
    new_sig = sig.replace(parameters=new_params)

    if inspect.iscoroutinefunction(fn):
        @functools.wraps(fn)
        async def wrapper(**kwargs):
            return await fn(**{k: v for k, v in kwargs.items() if k in have})
    else:
        @functools.wraps(fn)
        def wrapper(**kwargs):
            return fn(**{k: v for k, v in kwargs.items() if k in have})

    wrapper.__signature__ = new_sig
    # Pydantic reads __annotations__ via typing.get_type_hints — keep them
    # in sync with the augmented signature.
    wrapper.__annotations__ = {**fn.__annotations__, **extra_anns}
    return wrapper


# ------------------------------------------------------------------
# Tool 1: list missions (hardcoded, instant)
# ------------------------------------------------------------------

@mcp.tool(name="pds_list_missions")
@_absorb_cross_tool_kwargs
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
@_absorb_cross_tool_kwargs
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
@_absorb_cross_tool_kwargs
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
@_absorb_cross_tool_kwargs
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


# ------------------------------------------------------------------
# Tool 5: resolve volume-set (find which child carries which DATA_SET_ID)
# ------------------------------------------------------------------

@mcp.tool(name="pds_resolve_volume")
@_absorb_cross_tool_kwargs
async def pds_resolve_volume_tool(
    volume_set_path: str,
    node: str = "rms",
    dataset_id_hint: str | None = None,
    sample: int = 8,
) -> dict:
    """Probe a volume-set's children to find which one carries which DATA_SET_ID.

    Volume-sets on RMS (COUVIS_0xxx, COISS_2xxx) and volume series on ATM
    (jnomwr_*, MROM_*, cocirs_*) contain many sibling volumes with different
    DATA_SET_IDs (e.g. raw vs calibrated, EDR vs DDR). This tool lists every
    child and probes up to `sample` of them, ordered to prefer children whose
    name resembles `dataset_id_hint`. Returns per-child dataset_ids plus a
    `best_match` path when any sampled child contains a fuzzy-match to the hint.

    Args:
        volume_set_path: Parent directory (volume-set or volume series).
        node: PDS node identifier ("geo", "ppi", "lroc", "rms", "sbn", "atm", "img").
        dataset_id_hint: Substring or full DATA_SET_ID you're looking for (slash- and
            case-insensitive match). When provided, child ordering and `best_match`
            both use this.
        sample: Maximum number of children to probe (default 8, max 20).
    """
    result = await pds_resolve_volume(
        volume_set_path=volume_set_path,
        node=node,
        dataset_id_hint=dataset_id_hint,
        sample=sample,
    )
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
