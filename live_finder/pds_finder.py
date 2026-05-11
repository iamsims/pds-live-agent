"""Generalized multi-node PDS live finder agent.

Supports GEO, PPI, LROC, IMG, RMS, SBN, ATM, and NAIF nodes. Two operating modes:

1. **Multi-node** (node=None): Agent gets a routing prompt and uses
   ``pds_select_node`` to determine which node to query. Used when the
   caller doesn't know the target node upfront.

2. **Single-node** (node in SUPPORTED_NODES): Agent gets a focused prompt
   with node-specific context baked in. Saves one tool call (no routing step).

The MCP server (``pydantic_code.tools.mcp_server``) serves the same 5 tools
regardless of mode — all tools accept a ``node`` parameter.

NOTE: SBN's holdings index has historically been intermittent (HTTP 403). The
SBN workflow now tries the normal tools first; if list_dataset_dirs returns
status='forbidden', the agent falls back to the abbreviation table.
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
    "EDR/CDR/RDR products\n"
    "  - IMG (JPL Imaging Node): legacy planetary imaging — Cassini ISS, Voyager ISS, "
    "Galileo SSI, Mariner missions, Viking Orbiter/Lander, Magellan SAR, MESSENGER MDIS, "
    "NEAR MSI, Stardust, Deep Impact\n"
    "  - RMS (Ring-Moon Systems): Saturn rings (Cassini ISS/UVIS/VIMS, Voyager), "
    "Uranus/Jupiter/Neptune rings, ring occultations, irregular satellites\n"
    "  - SBN (Small Bodies Node): comets, asteroids, KBOs, dust; Rosetta, "
    "OSIRIS-REx, Hayabusa, Lucy, DART, Stardust, Deep Impact, NEAR\n"
    "  - ATM (Atmospheres): planetary atmospheres + surface meteorology — "
    "Mars (MCS/MAVEN/REMS/MEDA), Venus (Pioneer Venus), Jupiter (Galileo Probe), "
    "Titan (Huygens), outer planets (Voyager IRIS), Saturn system (Cassini CIRS "
    "thermal spectra, Cassini RSS atmospheric occultations)\n"
    "  - NAIF (Navigation and Ancillary Information Facility): SPICE kernels — "
    "spacecraft ephemerides, attitude/orientation, frames, instrument geometry, "
    "and clocks. Use ONLY for geometry/pointing/timing queries\n\n"
    # ---- WORKFLOW ----
    "WORKFLOW:\n"
    "  Step 0: Determine which node is relevant from the query.\n"
    "          Call pds_select_node(node=...) to get node-specific context "
    "(missions, abbreviations, workflow tips).\n"
    "  Step 1: Call pds_list_missions(node=...) to see available missions.\n"
    "          For GEO/IMG/NAIF this returns mission directories. For PPI/RMS/SBN/ATM "
    "the names are filter keywords. For LROC, skip to list_dataset_dirs.\n"
    "  Step 2: Call pds_list_dataset_dirs(path=..., node=..., filter=...).\n"
    "          For flat nodes with many datasets (PPI ~767, ATM ~2000, RMS ~84), "
    "use filter= to narrow by keyword. For IMG, you may need a second list call "
    "to traverse mission-internal sub-trees (e.g. cassini → cassini_orbiter/, opus/, pds4/, public/).\n"
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
    "  - Specifically LROC camera images of the Moon (NAC/WAC) → LROC\n"
    "  - Legacy planetary imaging (Cassini ISS, Voyager ISS, Galileo SSI, Mariner, "
    "Viking, Magellan SAR, MESSENGER MDIS) — when the data is camera images and the "
    "query doesn't fit GEO/RMS/LROC scope → IMG. Note: Cassini ISS ring observations "
    "go to RMS, not IMG; Mars surface imaging via HiRISE/CTX goes to GEO.\n"
    "  - Saturn/Uranus/Jupiter/Neptune RINGS, ring occultations, irregular "
    "satellites (small icy moons), Cassini ISS/UVIS/VIMS ring observations → RMS\n"
    "  - Comets, asteroids, KBOs, interplanetary dust, mission targets like "
    "Bennu/Itokawa/Ryugu/67P/Eros, Lucy Trojans, DART → SBN\n"
    "  - Planetary atmospheres (temperature/composition/aerosols/clouds), "
    "surface meteorology (wind, pressure, RH, dust opacity), atmospheric "
    "occultations, Mars Climate Sounder, Huygens Titan descent, Cassini CIRS "
    "thermal spectra (Saturn/Titan/icy satellites), Cassini RSS occultations → ATM\n"
    "  - SPICE kernels, spacecraft trajectory/ephemerides, instrument pointing, "
    "frames, leapseconds, spacecraft clocks → NAIF (only when the query is about "
    "geometry/pointing/timing — not measured science data)\n\n"
    # ---- NOTE ON SBN ----
    "NOTE ON SBN:\n"
    "  SBN's holdings index may intermittently return HTTP 403. Use the normal tool "
    "workflow for SBN. If list_dataset_dirs returns status='forbidden', fall back to "
    "the abbreviation table (call pds_select_node + pds_list_missions, synthesise "
    "candidates, and flag in reasoning that the ID is inferred, not verified).\n\n"
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
    """Build a focused single-node system prompt by injecting registry blocks.

    The general scaffolding (intro / PDS3-vs-PDS4 / tool list / critical rules) is
    universal and lives here. Everything node-specific (directory layout,
    abbreviation table, numbered workflow steps) is read from the registry.

    To tune behaviour for ONE node, edit that node's entry in
    ``pydantic_code.tools.node_registry`` — do not modify this function.
    """
    config = get_node_config(node)

    return (
        # ---- Intro ----
        f"You are a dataset-discovery assistant for the NASA PDS "
        f"{config.display_name} node at {config.base_url}\n\n"

        # ---- Node-specific: directory layout / caveats ----
        f"Directory layout and workflow:\n{config.workflow_notes}\n\n"

        # ---- Node-specific: abbreviation table ----
        f"{config.abbreviations}\n\n"

        # ---- Universal: PDS3 vs PDS4 conventions ----
        "PDS3 vs PDS4:\n"
        "  - PDS3 directory names are ALL-CAPS-style hyphenated identifiers "
        "(e.g. mex-m-hrsc-5-refdr-dtm-v1). Leaf marker: voldesc.cat or voldesc.sfd.\n"
        "  - PDS4 bundle directories begin with `urn-nasa-pds-`. "
        "Leaf marker: bundle*.xml or bundle*.lblx. Collections live in subdirectories.\n"
        "  - Hybrid: some directories have BOTH PDS3 and PDS4 labels.\n\n"

        # ---- Universal: tool list ----
        f"YOUR TOOLS (4 tools — always pass node='{node}'):\n"
        f"  1. pds_list_missions(node='{node}') — returns mission directories "
        "with descriptions. No HTTP.\n"
        f"  2. pds_list_dataset_dirs(path, node='{node}', filter=...) — lists "
        "sub-directory names under a path. Cheap HTTP, no label parsing.\n"
        f"  3. pds_probe_datasets(paths, node='{node}') — probes specific "
        "directories for PDS labels. Accepts a list of paths (max 20).\n"
        f"  4. pds_inspect_collections(path, node='{node}') — scans PDS4 "
        "bundle subdirs for collection labels.\n\n"

        # ---- Node-specific: numbered workflow ----
        f"WORKFLOW:\n{config.workflow_steps}\n"

        # ---- Universal: critical rules ----
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


# ---------------------------------------------------------------------------
# Layered mode: Stage 1 (live HTTP walk) + Stage 2 (node-specific faceted API)
#
# Two-stage flow:
#   1. ROUTER agent (tool-less) classifies the query to ONE node.
#   2. Python builds the WORKER prompt as
#         _build_single_node_prompt(node) + STAGE_2_APPENDIX_TEMPLATE.format(...)
#      so Stage 1 (the existing single-node prompt) is preserved verbatim and a
#      universal Stage-2 appendix is appended with a per-node tool block.
#
# Per CLAUDE.md, _build_single_node_prompt is universal scaffolding and is NOT
# modified here — we only compose around it. Per-node behaviour lives in either
# the registry (Stage 1) or LAYER3_TOOLS_BY_NODE (Stage 2). No if/elif on node.
# ---------------------------------------------------------------------------


class RouterDecision(BaseModel):
    """Structured output for the layered-mode router agent."""

    primary_node: str | None = Field(
        default=None,
        description=(
            "Primary PDS node id chosen for the query. One of "
            "'geo', 'ppi', 'lroc', 'img', 'rms', 'sbn', 'atm', 'naif'. "
            "Return null only when the query is too vague to map to a single "
            "node confidently (in which case confidence MUST be 'low')."
        ),
    )
    secondary_node: str | None = Field(
        default=None,
        description=(
            "Optional second-best node id from the same set, when the query "
            "plausibly overlaps two nodes. Leave null if only one node fits."
        ),
    )
    confidence: str = Field(
        description="One of 'high', 'medium', 'low'. Use 'low' for vague queries.",
    )
    reasoning: str = Field(
        description=(
            "One- or two-sentence explanation of which keywords or domain "
            "cues drove the choice."
        ),
    )


ROUTER_SYSTEM_PROMPT = (
    "You are a PDS Node Router. Your ONLY job is to classify a natural-language "
    "dataset query into the single best NASA PDS discipline node. You have NO "
    "tools, do NOT browse anything, and do NOT return dataset candidates — only "
    "a routing decision.\n\n"
    "NODE SELECTION GUIDE (one line each):\n"
    "  - GEO  — Mars / Venus / Mercury / Moon surface geology, geochemistry, "
    "topography, gravity, radar sounding, thermal emission, imaging "
    "spectroscopy. Includes Mars HiRISE and CTX imaging.\n"
    "  - PPI  — Magnetic fields, plasma, particles, solar wind, magnetospheres, "
    "ionospheres, radio/plasma waves, energetic particles.\n"
    "  - LROC — Specifically NAC/WAC camera images of the Moon from the Lunar "
    "Reconnaissance Orbiter (LROC).\n"
    "  - IMG  — Legacy planetary camera imaging at NON-ring targets: Cassini "
    "ISS (non-rings), Voyager ISS, Galileo SSI, Mariner, Viking Orbiter/Lander, "
    "Magellan SAR, MESSENGER MDIS, NEAR MSI.\n"
    "  - RMS  — Saturn / Uranus / Jupiter / Neptune RINGS, ring occultations, "
    "irregular satellites. Includes Cassini ISS/UVIS/VIMS ring observations.\n"
    "  - SBN  — Comets, asteroids, KBOs, interplanetary dust, small-body "
    "missions (OSIRIS-REx, Hayabusa, Hayabusa2, Rosetta, Lucy, DART, Stardust, "
    "Deep Impact, NEAR).\n"
    "  - ATM  — Planetary atmospheres (temperature, composition, aerosols, "
    "clouds), surface meteorology (wind, pressure, RH, dust opacity), "
    "atmospheric occultations: MCS, MAVEN, REMS/MEDA, Huygens, Cassini CIRS, "
    "Cassini RSS occultations.\n"
    "  - NAIF — SPICE kernels only: spacecraft ephemerides, attitude, frames, "
    "instrument geometry, clocks. Use ONLY when the query is about "
    "geometry/pointing/timing, NEVER for measured science data.\n\n"
    "DISAMBIGUATION (common edge cases):\n"
    "  - Cassini ISS images of Saturn's rings -> RMS (NOT IMG).\n"
    "  - Mars HiRISE / CTX surface images -> GEO (NOT IMG).\n"
    "  - Mars MCS / MAVEN atmosphere / dust opacity -> ATM (NOT GEO).\n"
    "  - LRO NAC/WAC lunar imaging -> LROC; other lunar science -> GEO.\n"
    "  - Spacecraft trajectory / pointing / SPICE -> NAIF, even when the "
    "instrument's science data lives at a different node.\n\n"
    "RULES:\n"
    "  1. Pick EXACTLY ONE primary node.\n"
    "  2. Set secondary_node only if a second node is plausibly applicable "
    "(e.g. an instrument's data lives at one node but the science theme "
    "overlaps another). Otherwise leave it null.\n"
    "  3. If the query is too vague to map to a single node confidently, "
    "return primary_node=null with confidence='low' instead of guessing.\n"
    "  4. Output JSON with primary_node, secondary_node, confidence, "
    "reasoning. Do not add any other fields.\n"
)


# Per-node Stage 2 tool blocks. Each is a plain-text block listing the deeper
# faceted-search tools available AFTER Stage 1 has located the right bundle or
# collection. One tool per line with a short parameter hint and one-line
# purpose. No literal '{' or '}' — the appendix is rendered via str.format.

_GEO_LAYER3_TOOLS = (
    "  - ODE_search_products(target=..., instrument=..., bbox=..., pt=..., "
    "product_type=...): faceted product search across GEO/ODE holdings. "
    "Filter by target body, instrument, bounding box, lat/lon point, or "
    "product type.\n"
    "  - ODE_count_products(target=..., instrument=..., bbox=...): cheap count "
    "before pulling a large result set.\n"
    "  - ODE_list_instruments(target=...): enumerate instrument codes valid "
    "for a target.\n"
    "  - ODE_list_feature_classes(target=...) / ODE_list_feature_names("
    "target=..., feature_class=...): gazetteer lookup for named surface "
    "features (craters, maria, etc.).\n"
    "  - ODE_get_feature_bounds(target=..., feature_name=...): bounding box "
    "for a named feature; feed the bbox into ODE_search_products.\n"
)

_IMG_LAYER3_TOOLS = (
    "  - IMG_search(target=..., instrument=..., mission=..., time_range=..., "
    "filters=...): IMG faceted product search.\n"
    "  - IMG_get_facets(field=...): enumerate valid facet values (instruments, "
    "missions, targets, product types) for the IMG catalog.\n"
    "  - IMG_get_product(product_id=...): fetch metadata for one IMG product.\n"
    "  - IMG_count(target=..., instrument=..., ...): count matches without "
    "pulling rows.\n"
)

_RMS_LAYER3_TOOLS = (
    "  - OPUS_search(target=..., instrument=..., time_range=..., "
    "ring_geometry=..., observation_type=...): RMS OPUS faceted product "
    "search at the observation/granule level.\n"
    "  - OPUS_count(...): count results before pulling them.\n"
    "  - OPUS_get_metadata(opus_id=...): metadata for one observation.\n"
    "  - OPUS_get_files(opus_id=..., product_type=...): file list for one "
    "observation, optionally filtered by product type (raw / calibrated / "
    "preview / geometry).\n"
)

_SBN_LAYER3_TOOLS = (
    "  - SBN_search_object(target_name=..., target_type=...): look up data by "
    "small-body name (comet, asteroid, KBO).\n"
    "  - SBN_search_coordinates(ra=..., dec=..., radius=..., epoch=...): "
    "spatial search of small-body observations near a sky position.\n"
    "  - SBN_list_sources(): enumerate SBN sub-archives / mirrors when the PSI "
    "tree is unavailable (e.g. UMD mirror for Rosetta / Stardust / Deep "
    "Impact / comets).\n"
)

# Shared PDS4 registry fallback for nodes without a bespoke deep-search API
# (PPI, ATM, NAIF, LROC) and also the safe default for any unknown node.
_PDS4_FALLBACK = (
    "  - PDS4_search_bundles(keywords=..., investigation=..., instrument=..., "
    "target=...): cross-node PDS4 registry bundle search.\n"
    "  - PDS4_search_collections(bundle_lid=..., keywords=..., ...): collection "
    "search; reuse the Stage 1 bundle LID as a filter when possible.\n"
    "  - PDS4_search_products(collection_lid=..., keywords=..., ...): "
    "product-level search inside a collection.\n"
    "  - PDS4_search_investigations / PDS4_search_instruments / "
    "PDS4_search_instrument_hosts / PDS4_search_targets: context-product "
    "lookups when user-facing names need to be resolved to LIDs.\n"
    "  - PDS4_get_product(lid=...): fetch one product label by LID.\n"
    "  - PDS4_crawl_context_product(lid=...): walk a context product's "
    "associations to find related bundles/collections.\n"
)

LAYER3_TOOLS_BY_NODE: dict[str, str] = {
    "geo":  _GEO_LAYER3_TOOLS,
    "img":  _IMG_LAYER3_TOOLS,
    "rms":  _RMS_LAYER3_TOOLS,
    "sbn":  _SBN_LAYER3_TOOLS,
    "ppi":  _PDS4_FALLBACK,
    "atm":  _PDS4_FALLBACK,
    "naif": _PDS4_FALLBACK,
    "lroc": _PDS4_FALLBACK,
}


STAGE_2_APPENDIX_TEMPLATE = (
    "\n"
    "===========================================================\n"
    "STAGE 2 — DEEPER NODE-SPECIFIC SEARCH (escalation only)\n"
    "===========================================================\n\n"
    "Everything above is STAGE 1: the 4 live-HTTP tools "
    "(pds_list_missions / pds_list_dataset_dirs / pds_probe_datasets / "
    "pds_inspect_collections), the per-node workflow, and the Critical Rules "
    "ALL belong to Stage 1. Stage 1 reaches bundle/collection level by "
    "walking the node's directory tree. Stage 2 below is a SECOND set of "
    "tools for refining or rescuing Stage 1 — do NOT call any Stage 2 tool "
    "unless one of the escalation triggers below fires.\n\n"
    "WHEN TO ESCALATE TO STAGE 2 (any one is enough):\n"
    "  (a) The query asks for SPECIFIC observations, granules, or product "
    "IDs — not just a dataset. Example: 'Cassini ISS images of Mimas between "
    "2009 and 2010' needs per-observation filtering.\n"
    "  (b) Stage 1 has located the right bundle/collection but you still "
    "need to narrow by GEOMETRY, TIME, or a SPATIAL filter (bbox, lat/lon, "
    "ring longitude, target body, observation type).\n"
    "  (c) Stage 1 produced AMBIGUOUS candidates that a faceted query can "
    "disambiguate (e.g. multiple instruments with similar names, multiple "
    "processing levels).\n"
    "  (d) Stage 1 cannot reach the node's holdings index (e.g. SBN returns "
    "HTTP 403, a directory listing is unavailable). Use the Stage 2 API as a "
    "fallback path to candidates.\n\n"
    "STAGE 2 TOOLS (this node):\n"
    "{layer3_tools}\n"
    "STAGE 2 RULES:\n"
    "  1. When you already have a bundle/collection LID from Stage 1, REUSE "
    "it as a filter in the Stage 2 call. Stage 2 is refinement, not a fresh "
    "search.\n"
    "  2. Spend the MINIMUM number of additional calls. If a single faceted "
    "call answers the question, stop.\n"
    "  3. If Stage 2 finds nothing or errors out, FALL BACK to the Stage 1 "
    "candidates and note in `reasoning` that Stage 2 was attempted and "
    "returned no refinement.\n"
    "  4. The 8-tool-call budget from Stage 1's Critical Rule 5 is the "
    "budget for BOTH stages combined. Do NOT reset the counter when entering "
    "Stage 2.\n"
    "  5. Every candidate's `reasoning` field must explicitly name which "
    "stage produced it (e.g. 'Stage 1: located bundle X by directory walk' "
    "or 'Stage 2: narrowed to product Y via ODE_search_products bbox "
    "filter').\n"
)


def _build_layered_prompt(node: str) -> str:
    """Compose the layered (Stage 1 + Stage 2) worker prompt for one node.

    Stage 1 is the existing single-node prompt produced by
    ``_build_single_node_prompt(node)``. Stage 2 is a universal appendix with
    a per-node tool block injected from ``LAYER3_TOOLS_BY_NODE``. Nodes
    without a bespoke faceted API (ppi/atm/naif/lroc) get the shared PDS4
    registry fallback.

    Per CLAUDE.md, this function does NOT modify the Stage 1 builder; it only
    appends. There is no per-node branching here — anything node-specific
    lives in ``node_registry`` (Stage 1) or ``LAYER3_TOOLS_BY_NODE`` (Stage 2).
    """
    stage1 = _build_single_node_prompt(node)
    layer3 = LAYER3_TOOLS_BY_NODE.get(node.lower(), _PDS4_FALLBACK)
    return stage1 + STAGE_2_APPENDIX_TEMPLATE.format(layer3_tools=layer3)


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
