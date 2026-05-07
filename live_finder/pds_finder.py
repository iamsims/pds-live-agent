"""Generalized multi-node PDS live finder agent.

Supports GEO, PPI, and LROC nodes. Two operating modes:

1. **Multi-node** (node=None): Agent gets a routing prompt and uses
   ``pds_select_node`` to determine which node to query. Used when the
   caller doesn't know the target node upfront.

2. **Single-node** (node="geo"|"ppi"|"lroc"): Agent gets a focused prompt
   with node-specific context baked in. Saves one tool call (no routing step).

The MCP server (``pydantic_code.tools.mcp_server``) serves the same 5 tools
regardless of mode — all tools accept a ``node`` parameter.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.mcp import MCPServerStdio
from pydantic_ai.settings import ModelSettings

from pydantic_code.tools.node_registry import SUPPORTED_NODES, get_node_config

# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

_MULTI_NODE_SYSTEM_PROMPT = (
    "You are a dataset-discovery assistant for NASA's Planetary Data System (PDS).\n\n"
    "You have access to live PDS node directories via tools. Supported nodes:\n"
    "  - GEO (Geosciences): Mars, Venus, Mercury, Moon surface/subsurface, "
    "topography, gravity, geochemistry, spectroscopy\n"
    "  - PPI (Planetary Plasma Interactions): magnetospheres, solar wind, "
    "plasma, particles, fields, radio/plasma waves\n"
    "  - LROC (Lunar Reconnaissance Orbiter Camera): NAC/WAC lunar imaging, "
    "EDR/CDR/RDR products\n\n"
    # ---- WORKFLOW ----
    "WORKFLOW:\n"
    "  Step 0: Determine which node is relevant from the query.\n"
    "          Call pds_select_node(node=...) to get node-specific context "
    "(missions, abbreviations, workflow tips).\n"
    "  Step 1: Call pds_list_missions(node=...) to see available missions.\n"
    "          For GEO/PPI this returns mission names. For LROC, skip to list_dataset_dirs.\n"
    "  Step 2: Call pds_list_dataset_dirs(path=..., node=..., filter=...).\n"
    "          For flat nodes (PPI ~767 datasets), use filter= to narrow by keyword.\n"
    "  Step 3: Call pds_probe_datasets(paths=[...], node=...) with the most "
    "relevant directories.\n"
    "  Step 4: If PDS4 bundles are found and you need collection-level LIDs, "
    "call pds_inspect_collections(path=..., node=...).\n"
    "  Step 5: Return candidates with dataset_id, title, and reasoning.\n\n"
    # ---- NODE SELECTION GUIDE ----
    "NODE SELECTION GUIDE:\n"
    "  - Mars/Venus/Mercury/Moon surface geology, geochemistry, topography, "
    "gravity, radar sounding, thermal emission, imaging spectroscopy → GEO\n"
    "  - Magnetic fields, plasma, particles, solar wind, magnetospheres, "
    "radio/plasma waves, energetic particles → PPI\n"
    "  - Specifically LROC camera images of the Moon (NAC/WAC) → LROC\n\n"
    # ---- PDS3 vs PDS4 ----
    "PDS3 vs PDS4:\n"
    "  - PDS3 directory names are ALL-CAPS-style hyphenated identifiers "
    "(e.g. mex-m-hrsc-5-refdr-dtm-v1). Leaf marker: voldesc.cat or voldesc.sfd.\n"
    "  - PDS4 bundle directories begin with `urn-nasa-pds-`. "
    "Leaf marker: bundle*.xml or bundle*.lblx. Collections live in subdirectories.\n"
    "  - Hybrid: some directories have BOTH PDS3 and PDS4 labels.\n\n"
    # ---- CRITICAL RULES ----
    "CRITICAL RULES:\n"
    "  1. EVERY query requires you to return dataset candidates. Queries come from "
    "published scientific papers and always imply specific PDS datasets. NEVER "
    "dismiss a query as 'interpretation' or 'conceptual'. Always return at "
    "least one candidate.\n"
    "  2. Prefer CALIBRATED and REDUCED data products over raw/EDR when the "
    "query implies scientific analysis.\n"
    "  3. For PDS4 datasets, use inspect_collections ONLY for the top 2-3 most "
    "relevant bundles. Return the COLLECTION-level LID when a :data or "
    ":calibrated collection exists.\n"
    "  4. When the SAME data is available as both PDS3 and PDS4, return BOTH "
    "identifiers — emit one candidate per identifier. Most published papers cite "
    "the PDS3 dataset_id (e.g. MESS-E_V_H_SW-MAG-3-CDR-CALIBRATED-V1.0, "
    "LRO-L-LROC-5-RDR-V1.0); the PDS4 collection LID is the modern equivalent. "
    "Do NOT silently drop the PDS3 form.\n"
    "  5. Stay under 8 tool calls per query.\n"
    "  6. Only return paths you've actually probed — never guess.\n"
    "  7. Always pass the correct node= parameter to every tool call.\n"
)


def _build_single_node_prompt(node: str) -> str:
    """Build a focused single-node system prompt (no routing step needed)."""
    config = get_node_config(node)

    # Base structure
    prompt = (
        f"You are a dataset-discovery assistant for the NASA PDS "
        f"{config.display_name} node at {config.base_url}\n\n"
    )

    # Node-specific workflow and abbreviations
    if config.workflow_notes:
        prompt += f"Directory layout and workflow:\n{config.workflow_notes}\n\n"
    if config.abbreviations:
        prompt += f"{config.abbreviations}\n\n"

    # PDS3 vs PDS4 conventions
    prompt += (
        "PDS3 vs PDS4:\n"
        "  - PDS3 directory names are ALL-CAPS-style hyphenated identifiers "
        "(e.g. mex-m-hrsc-5-refdr-dtm-v1). Leaf marker: voldesc.cat or voldesc.sfd.\n"
        "  - PDS4 bundle directories begin with `urn-nasa-pds-`. "
        "Leaf marker: bundle*.xml or bundle*.lblx. Collections live in subdirectories.\n"
        "  - Hybrid: some directories have BOTH PDS3 and PDS4 labels.\n\n"
    )

    # Tool descriptions
    prompt += (
        f"YOUR TOOLS (4 tools — always pass node='{node}'):\n"
        f"  1. pds_list_missions(node='{node}') — returns mission directories "
        "with descriptions. No HTTP.\n"
        f"  2. pds_list_dataset_dirs(path, node='{node}', filter=...) — lists "
        "sub-directory names under a path. Cheap HTTP, no label parsing.\n"
        f"  3. pds_probe_datasets(paths, node='{node}') — probes specific "
        "directories for PDS labels. Accepts a list of paths (max 20).\n"
        f"  4. pds_inspect_collections(path, node='{node}') — scans PDS4 "
        "bundle subdirs for collection labels.\n\n"
    )

    # Workflow (node-aware)
    if config.has_mission_layer:
        prompt += (
            "WORKFLOW:\n"
            f"  Step 1: If you know the mission directory from the abbreviation table, "
            f"skip directly to list_dataset_dirs(path='<mission>/', node='{node}').\n"
            f"          Otherwise call pds_list_missions(node='{node}') first.\n"
            f"  Step 2: Call pds_list_dataset_dirs for the relevant mission directory. "
            "Scan names and pds_hints to identify promising datasets.\n"
            f"  Step 3: Call pds_probe_datasets with the most relevant paths (batch up to 20).\n"
            f"  Step 4: If PDS4 bundles found, call pds_inspect_collections on top 2-3.\n"
            f"  Step 5: Return candidates.\n\n"
            "Most queries can be answered in 3 tool calls: "
            "list_dataset_dirs → probe_datasets → inspect_collections.\n\n"
        )
    elif config.missions:
        # Flat node with a mission keyword list (e.g. PPI)
        prompt += (
            "WORKFLOW:\n"
            f"  Step 1: Call pds_list_missions(node='{node}') to see all available missions "
            "and their filter keywords.\n"
            f"  Step 2: Identify which mission(s) are relevant to the query.\n"
            f"  Step 3: Call pds_list_dataset_dirs(path='{config.data_root}', node='{node}', "
            "filter='<mission_name>') using the mission name as filter keyword.\n"
            f"  Step 4: Call pds_probe_datasets with the most relevant paths (batch up to 20).\n"
            f"  Step 5: If PDS4 bundles found, call pds_inspect_collections on top 2-3.\n"
            f"  Step 6: Return candidates.\n\n"
        )
    else:
        # Flat node with no mission list (e.g. LROC)
        prompt += (
            "WORKFLOW:\n"
            f"  Step 1: Call pds_list_dataset_dirs(path='{config.data_root}', node='{node}'"
            ", filter='<keyword>') to find datasets.\n"
            f"  Step 2: Call pds_probe_datasets with the most relevant paths.\n"
            f"  Step 3: If PDS4 bundles found, call pds_inspect_collections.\n"
            f"  Step 4: Return candidates.\n\n"
        )

    # Critical rules
    prompt += (
        "CRITICAL RULES:\n"
        "  1. EVERY query requires at least one candidate. Never dismiss a query.\n"
        "  2. Prefer CALIBRATED/REDUCED data over raw/EDR for science queries.\n"
        "  3. For PDS4, use inspect_collections ONLY for top 2-3 bundles. "
        "Return COLLECTION-level LID when :data or :calibrated exists.\n"
        "  4. When the SAME data is available as both PDS3 and PDS4, return BOTH "
        "identifiers — emit one candidate per identifier. Most published papers "
        "cite the PDS3 dataset_id (e.g. MESS-E_V_H_SW-MAG-3-CDR-CALIBRATED-V1.0, "
        "LRO-L-LROC-5-RDR-V1.0); the PDS4 collection LID is the modern equivalent. "
        "Do NOT silently drop the PDS3 form.\n"
        "  5. Stay under 8 tool calls per query.\n"
        "  6. Only return paths you've actually probed — never guess.\n"
    )

    return prompt


# ---------------------------------------------------------------------------
# Schemas (same as pds_geo_finder for compatibility)
# ---------------------------------------------------------------------------


class PDSLiveFindDatasetInput(BaseModel):
    """Input for the live finder agent."""

    query: str = Field(
        ...,
        description="Natural-language query, e.g. 'Mars 2020 PIXL data', 'Cassini magnetosphere'.",
    )


class PDSLiveDatasetCandidate(BaseModel):
    """One ranked dataset candidate found by the live agent."""

    path: str = Field(description="Path relative to the node's base URL")
    dataset_id: str | None = Field(
        default=None,
        description="Canonical PDS3 DATA_SET_ID or PDS4 logical_identifier",
    )
    title: str | None = Field(default=None, description="Dataset title from the label")
    pds_version: str | None = Field(default=None, description="'PDS3' or 'PDS4'")
    mission: str | None = Field(default=None, description="Top-level mission directory")
    node: str | None = Field(default=None, description="PDS node identifier")
    reasoning: str = Field(description="Why this dataset matches the query")


class PDSLiveFindDatasetOutput(BaseModel):
    """Output for the live finder agent."""

    candidates: list[PDSLiveDatasetCandidate] = Field(
        default_factory=list,
        description="Datasets that match the query, ordered most-relevant-first",
    )
    summary: str = Field(description="Short summary of the search and what was found")


# ---------------------------------------------------------------------------
# MCP server (stdio subprocess)
# ---------------------------------------------------------------------------

_PACKAGE_ROOT = str(Path(__file__).resolve().parent.parent.parent)


def _build_mcp() -> MCPServerStdio:
    """Spawn ``pydantic_code.tools.mcp_server`` as a stdio subprocess."""
    return MCPServerStdio(
        sys.executable,
        args=["-m", "pydantic_code.tools.mcp_server"],
        env={**os.environ, "PYTHONPATH": _PACKAGE_ROOT + os.pathsep + os.environ.get("PYTHONPATH", "")},
        timeout=30,
    )


# ---------------------------------------------------------------------------
# Finder config factory (used by finder.py dispatcher)
# ---------------------------------------------------------------------------


def get_finder_config(node: str | None = None):
    """Return the live mode configuration for the unified finder.

    Args:
        node: If specified, builds a single-node agent with a focused prompt.
            If None, builds a multi-node agent with routing via pds_select_node.
    """
    from pydantic_code.finder import FinderConfig

    if node:
        system_prompt = _build_single_node_prompt(node)
    else:
        system_prompt = _MULTI_NODE_SYSTEM_PROMPT

    return FinderConfig(
        system_prompt=system_prompt,
        mcp_server=_build_mcp(),
        output_type=PDSLiveFindDatasetOutput,
    )
