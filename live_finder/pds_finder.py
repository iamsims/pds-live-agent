"""PDS live finder agent — single-node and layered modes.

Supports GEO, PPI, LROC, IMG, RMS, SBN, ATM, and NAIF nodes. Two operating modes:

1. **Single-node**: Caller specifies ``node``. The agent gets a focused
   prompt with that node's context baked in (directory layout, abbreviations,
   workflow steps). Used when the target node is known upfront.

2. **Layered**: A tool-less router agent classifies the query to one node,
   then a single-node worker runs with that node's prompt plus an extra
   Stage 2 toolset of deeper faceted-search tools (ODE / OPUS / IMG / SBN /
   PDS4). See ``LayeredFinder`` and ``run_layered_query``.

The MCP server (``pydantic_code.tools.mcp_server``) serves 5 stateless tools
that all take a ``node`` parameter.

NOTE: SBN's holdings index has historically been intermittent (HTTP 403). The
SBN workflow now tries the normal tools first; if list_dataset_dirs returns
status='forbidden', the agent falls back to the abbreviation table.
"""

from __future__ import annotations

import asyncio
import os
from contextlib import AsyncExitStack
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.mcp import MCPServerStreamableHTTP
from pydantic_ai.settings import ModelSettings

from pydantic_code.tools.node_registry import SUPPORTED_NODES, get_node_config

# ---------------------------------------------------------------------------
# Single-node system prompt builder
# ---------------------------------------------------------------------------


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
        f"YOUR TOOLS (5 tools — always pass node='{node}'):\n"
        f"  1. pds_list_missions(node='{node}') — returns mission directories "
        "with descriptions. No HTTP.\n"
        f"  2. pds_list_dataset_dirs(path, node='{node}', filter=...) — lists "
        "sub-directory names under a path. Cheap HTTP, no label parsing.\n"
        f"  3. pds_probe_datasets(paths, node='{node}') — probes specific "
        "directories for PDS labels. Accepts a list of paths (max 20).\n"
        f"  4. pds_inspect_collections(path, node='{node}') — scans PDS4 "
        "bundle subdirs for collection labels.\n"
        f"  5. pds_resolve_volume(volume_set_path, node='{node}', "
        "dataset_id_hint=..., sample=8) — when a parent directory contains many\n"
        "     numbered sibling volumes (RMS COISS_2xxx, COUVIS_0xxx, ATM\n"
        "     MROM_*, jnomwr_*, cocirs_*, IMG mrox_*, MSGRMDS_*), this probes\n"
        "     hint-ranked children in one call and returns per-child\n"
        "     dataset_ids plus a `best_match` field. Use it instead of\n"
        "     probing volumes one at a time when you know the target id or\n"
        "     a discriminating substring of it.\n\n"

        # ---- Node-specific: numbered workflow ----
        f"WORKFLOW:\n{config.workflow_steps}\n"

        # ---- Universal: critical rules ----
        "CRITICAL RULES:\n"
        "  1. EVERY query requires at least one candidate. Never dismiss a query "
        "as 'not a dataset request' — every paper-derived query has at least one\n"
        "     supporting PDS dataset somewhere in this node's archive, and your job\n"
        "     is to surface the closest match (with `reasoning` explaining the link).\n"
        "  2. Prefer CALIBRATED/REDUCED data over raw/EDR for science queries.\n"
        "     When a probed voldesc exposes `dataset_ids` with multiple entries,\n"
        "     match the question's data need to the PRODUCT-TYPE token inside each\n"
        "     id (typically the third or fourth dash-separated token). Common ones:\n"
        "         EDR / RAW     = raw observations\n"
        "         CDR / CALIB   = generic calibrated data\n"
        "         RDR / TRDR / MRDR / MTRDR / BDR / SCVDR = reduced / derived imagery or spectra\n"
        "         DDR / LDR     = derived / digital terrain / level-5 products\n"
        "         SSB           = solar / stellar occultation (Cassini UVIS)\n"
        "         SPEC / CUBE / WAV = spectra / spectral cubes / waveforms\n"
        "         QUBE          = VIMS spectral data cube (the VIMS-flavoured \"EDR\")\n"
        "     If the query mentions 'occultation' return the SSB id; 'spectra' →\n"
        "     SPEC; 'calibrated radiance' → CALIB/CDR; 'mosaic / map / derived' →\n"
        "     DDR/MRDR/MTRDR. When two product types both fit the question (e.g.\n"
        "     SPEC + SSB for an occultation spectra query), return both candidates.\n"
        "     Do NOT just return the scalar `dataset_id` and drop the rest — that\n"
        "     field is only the first id in the voldesc and is often the wrong\n"
        "     product type for a given query.\n"
        "  3. For PDS4, use inspect_collections ONLY for top 2-3 bundles. "
        "Return COLLECTION-level LID when :data or :calibrated exists.\n"
        "  4. When the SAME data is available as both PDS3 and PDS4, return BOTH "
        "identifiers — emit one candidate per identifier. Most published papers "
        "cite the PDS3 dataset_id (e.g. MESS-E_V_H_SW-MAG-3-CDR-CALIBRATED-V1.0, "
        "LRO-L-LROC-5-RDR-V1.0); the PDS4 collection LID is the modern equivalent. "
        "Do NOT silently drop the PDS3 form.\n"
        "  5. Stay under 20 tool calls per query. Soft cap: 15. Hard cap: 20.\n"
        "  6. Only return paths you've actually probed — never guess.\n"
        "  7. ANTI-THRASHING. Never re-issue a tool call with the same name and the\n"
        "     same key arguments (path, paths, filter) that you've already issued in\n"
        "     this trace. The result will be identical — it wastes the budget and\n"
        "     blocks progress. If you're tempted to re-probe the same set of paths,\n"
        "     either move to a different tool (inspect_collections, resolve_volume)\n"
        "     or commit to `final_result` with the best candidate you have so far.\n"
        "  8. STOP-AT-LEVEL. The output `path` field should point at a dataset or\n"
        "     bundle directory (containing voldesc.cat or bundle*.xml), NOT at a\n"
        "     deeper product / DATA / EXTRAS / BROWSE / SHAPEFILE / DTM sub-folder.\n"
        "     Feature-level retrieval (a specific image of a specific crater) is\n"
        "     out of scope for this finder; return the dataset and explain in\n"
        "     `reasoning` how it covers the feature.\n"
        "  9. After 15 tool calls without converging, ALWAYS prefer emitting your\n"
        "     current best candidate(s) over running another exploratory call.\n"
        "     A grounded near-match with a clear reasoning note is more useful\n"
        "     than a 20-call trace that times out with no `final_result`.\n"
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
    "  - ode_search_products_tool(target=..., instrument=..., bbox=..., "
    "pt=..., product_type=...): faceted product search across GEO/ODE "
    "holdings. Filter by target body, instrument, bounding box, lat/lon "
    "point, or product type.\n"
    "  - ode_count_products_tool(target=..., instrument=..., bbox=...): cheap "
    "count before pulling a large result set.\n"
    "  - ode_list_instruments_tool(target=...): enumerate instrument codes "
    "valid for a target.\n"
    "  - ode_list_feature_classes_tool(target=...) / "
    "ode_list_feature_names_tool(target=..., feature_class=...): gazetteer "
    "lookup for named surface features (craters, maria, etc.).\n"
    "  - ode_get_feature_bounds_tool(target=..., feature_name=...): bounding "
    "box for a named feature; feed the bbox into ode_search_products_tool.\n"
)

_IMG_LAYER3_TOOLS = (
    "  - img_search_tool(target=..., instrument=..., mission=..., "
    "time_range=..., filters=...): IMG faceted product search.\n"
    "  - img_get_facets_tool(field=...): enumerate valid facet values "
    "(instruments, missions, targets, product types) for the IMG catalog.\n"
    "  - img_get_product_tool(product_id=...): fetch metadata for one IMG "
    "product.\n"
    "  - img_count_tool(target=..., instrument=..., ...): count matches "
    "without pulling rows.\n"
)

_RMS_LAYER3_TOOLS = (
    "  - opus_search_tool(target=..., instrument=..., time_range=..., "
    "ring_geometry=..., observation_type=...): RMS OPUS faceted product "
    "search at the observation/granule level.\n"
    "  - opus_count_tool(...): count results before pulling them.\n"
    "  - opus_get_metadata_tool(opus_id=...): metadata for one observation.\n"
    "  - opus_get_files_tool(opus_id=..., product_type=...): file list for "
    "one observation, optionally filtered by product type (raw / calibrated "
    "/ preview / geometry).\n"
)

_SBN_LAYER3_TOOLS = (
    "  - sbn_search_object_tool(target_name=..., target_type=...): look up "
    "data by small-body name (comet, asteroid, KBO).\n"
    "  - sbn_search_coordinates_tool(ra=..., dec=..., radius=..., "
    "epoch=...): spatial search of small-body observations near a sky "
    "position.\n"
    "  - sbn_list_sources_tool(): enumerate SBN sub-archives / mirrors when "
    "the PSI tree is unavailable (e.g. UMD mirror for Rosetta / Stardust / "
    "Deep Impact / comets).\n"
)

# Shared PDS4 registry fallback for nodes without a bespoke deep-search API
# (PPI, ATM, NAIF, LROC) and also the safe default for any unknown node.
_PDS4_FALLBACK = (
    "  - pds4search_bundles_tool(keywords=..., investigation=..., "
    "instrument=..., target=...): cross-node PDS4 registry bundle search.\n"
    "  - pds4search_collections_tool(bundle_lid=..., keywords=..., ...): "
    "collection search; reuse the Stage 1 bundle LID as a filter when "
    "possible.\n"
    "  - pds4search_products_tool(collection_lid=..., keywords=..., ...): "
    "product-level search inside a collection.\n"
    "  - pds4search_investigations_tool / pds4search_instruments_tool / "
    "pds4search_instrument_hosts_tool / pds4search_targets_tool: context-"
    "product lookups when user-facing names need to be resolved to LIDs.\n"
    "  - pds4get_product_tool(lid=...): fetch one product label by LID.\n"
    "  - pds4crawl_context_product_tool(lid=...): walk a context product's "
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


# Per-node allow-list for the Stage 2 MCP server. The worker only sees the
# tools in this frozenset for its node — the others are filtered out before
# the agent ever learns they exist.
_PDS4_FALLBACK_ALLOWED = frozenset({
    "pds4search_bundles_tool",
    "pds4search_collections_tool",
    "pds4search_products_tool",
    "pds4search_investigations_tool",
    "pds4search_instruments_tool",
    "pds4search_instrument_hosts_tool",
    "pds4search_targets_tool",
    "pds4get_product_tool",
    "pds4crawl_context_product_tool",
})

LAYER3_ALLOWED_TOOLS: dict[str, frozenset[str]] = {
    "geo":  frozenset({
        "ode_search_products_tool", "ode_count_products_tool",
        "ode_list_instruments_tool", "ode_list_feature_classes_tool",
        "ode_list_feature_names_tool", "ode_get_feature_bounds_tool",
    }),
    "img":  frozenset({
        "img_search_tool", "img_get_facets_tool",
        "img_get_product_tool", "img_count_tool",
    }),
    "rms":  frozenset({
        "opus_search_tool", "opus_count_tool",
        "opus_get_metadata_tool", "opus_get_files_tool",
    }),
    "sbn":  frozenset({
        "sbn_search_object_tool", "sbn_search_coordinates_tool",
        "sbn_list_sources_tool",
    }),
    "ppi":  _PDS4_FALLBACK_ALLOWED,
    "atm":  _PDS4_FALLBACK_ALLOWED,
    "naif": _PDS4_FALLBACK_ALLOWED,
    "lroc": _PDS4_FALLBACK_ALLOWED,
}


STAGE_2_APPENDIX_TEMPLATE = (
    "\n"
    "===========================================================\n"
    "STAGE 2 — DEEPER NODE-SPECIFIC SEARCH (escalation only)\n"
    "===========================================================\n\n"
    "Everything above is STAGE 1: the 5 live-HTTP tools "
    "(pds_list_missions / pds_list_dataset_dirs / pds_probe_datasets / "
    "pds_inspect_collections / pds_resolve_volume), the per-node workflow, "
    "and the Critical Rules ALL belong to Stage 1. Stage 1 reaches "
    "bundle/collection level by "
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
    "  4. The 20-tool-call budget from Stage 1's Critical Rule 5 is the "
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
# Schemas
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
# Stage 1 MCP server (hosted streamable HTTP)
# ---------------------------------------------------------------------------
#
# Stage 1 = the deployed pds-node-mcp instance, which exposes the 5 live
# directory-walking tools (pds_list_missions, pds_list_dataset_dirs,
# pds_probe_datasets, pds_inspect_collections, pds_resolve_volume).
# Previously a local stdio subprocess; now hosted so every consumer hits
# the same canonical instance.

_DEFAULT_STAGE1_URL = "https://fuzzy-aquamarine-swordtail.fastmcp.app/mcp"


def _build_mcp(
    *,
    url: str | None = None,
    headers: dict[str, str] | None = None,
) -> MCPServerStreamableHTTP:
    """Connect to the hosted Stage 1 MCP server over streamable HTTP.

    Auth: ``Authorization: Bearer <FAST_MCP_AUTH>`` is set automatically
    when that env var is present. Override via ``PDS_STAGE1_MCP_URL`` for
    staging / local mirrors, or pass ``url`` / ``headers`` directly.

    timeout=30: pydantic-ai's default of 5s is too aggressive for FastMCP
    Cloud cold starts. A serverless instance that's been idle can take
    20-30s to boot on the first request; with the 5s default the first
    queries of a batch reliably time out before the server is ready.
    """
    resolved_url = url or os.environ.get("PDS_STAGE1_MCP_URL") or _DEFAULT_STAGE1_URL
    if headers is None:
        token = os.environ.get("FAST_MCP_AUTH")
        headers = {"Authorization": f"Bearer {token}"} if token else None
    return MCPServerStreamableHTTP(url=resolved_url, headers=headers, timeout=30)


# Hosted FastMCP server that exposes the Stage 2 deeper-search tools
# (ode_*, opus_*, img_*, sbn_*, pds4*). Defaults match the production
# deployment; override via env vars for staging or local mirrors.
_DEFAULT_STAGE2_URL = "https://natural-bronze-stingray.fastmcp.app/mcp"


def _build_stage2_mcp(
    *,
    url: str | None = None,
    headers: dict[str, str] | None = None,
) -> MCPServerStreamableHTTP:
    """Connect to the hosted Stage 2 MCP server (streamable HTTP).

    Auth: ``Authorization: Bearer <FAST_MCP_AUTH>`` is set automatically when
    that env var is present (same convention as catalog mode). Pass ``headers``
    explicitly to override. See ``_build_mcp`` for the timeout rationale.
    """
    resolved_url = url or os.environ.get("PDS_STAGE2_MCP_URL") or _DEFAULT_STAGE2_URL
    if headers is None:
        token = os.environ.get("FAST_MCP_AUTH")
        headers = {"Authorization": f"Bearer {token}"} if token else None
    return MCPServerStreamableHTTP(url=resolved_url, headers=headers, timeout=30)


def _build_stage2_toolset_for(node: str, **stage2_kwargs):
    """Build a per-node filtered Stage 2 toolset.

    The Stage 2 MCP exposes all 26 layered tools; ``.filtered(...)`` hides
    everything not in ``LAYER3_ALLOWED_TOOLS[node]`` so the worker only ever
    sees its node's faceted-search tools.
    """
    allowed = LAYER3_ALLOWED_TOOLS.get(node.lower(), _PDS4_FALLBACK_ALLOWED)
    return _build_stage2_mcp(**stage2_kwargs).filtered(
        lambda ctx, td: td.name in allowed
    )


def build_layered_finder(
    node: str,
    *,
    model: str = "openai:gpt-5.2",
    reasoning_effort: Literal["low", "medium", "high"] = "high",
    stage2_url: str | None = None,
    stage2_headers: dict[str, str] | None = None,
) -> Agent[None, "PDSLiveFindDatasetOutput"]:
    """Build a layered worker agent for a single node.

    Stage 1 toolset: the existing stdio MCP (5 live HTTP tools).
    Stage 2 toolset: the hosted FastMCP server, filtered to the per-node
    allow-list in ``LAYER3_ALLOWED_TOOLS``.

    Routing (picking the node) is the caller's responsibility — wrap this
    in a router-driven runner that calls the router agent first, then passes
    the resulting node here.
    """
    stage1 = _build_mcp()
    stage2 = _build_stage2_toolset_for(node, url=stage2_url, headers=stage2_headers)

    return Agent(
        model,
        toolsets=[stage1, stage2],
        output_type=PDSLiveFindDatasetOutput,
        system_prompt=_build_layered_prompt(node),
        model_settings=ModelSettings(extra_body={"reasoning_effort": reasoning_effort}),
        retries=2,
    )


def build_router_agent(model: str = "openai:gpt-5.2") -> Agent[None, RouterDecision]:
    """Build the tool-less routing agent.

    Returns a ``RouterDecision`` with ``primary_node``, ``secondary_node``,
    ``confidence``, and ``reasoning``. No MCP attached — pure classification.
    """
    return Agent(
        model,
        output_type=RouterDecision,
        system_prompt=ROUTER_SYSTEM_PROMPT,
    )


# ---------------------------------------------------------------------------
# Layered runner — optimized batch path
#
# Naive use is `async with build_layered_finder(node):` per query, which
# respawns the Stage 1 stdio subprocess AND opens a new HTTP MCP every
# call. For batches that's N x subprocess startup + N x handshake.
#
# LayeredFinder opens MCP transports lazily and caches one worker per
# touched node. A single `async with LayeredFinder()` covers any number of
# `.run(q)` calls; only the first query that visits a node pays the MCP
# spin-up cost.
# ---------------------------------------------------------------------------


class LayeredFinder:
    """Reusable layered-mode runner with persistent MCP transports.

    Use as an async context manager so MCP cleanup is deterministic:

        async with LayeredFinder() as lf:
            for q in queries:
                decision, output = await lf.run(q)

    The router is built once. Workers are built and entered lazily — the
    first query that routes to a given node pays the MCP startup cost; all
    subsequent queries for that node reuse the open transports.
    """

    def __init__(
        self,
        *,
        model: str = "openai:gpt-5.2",
        reasoning_effort: Literal["low", "medium", "high"] = "high",
        stage2_url: str | None = None,
        stage2_headers: dict[str, str] | None = None,
        fallback_node: str = "geo",
    ) -> None:
        self._model = model
        self._effort = reasoning_effort
        self._stage2_url = stage2_url
        self._stage2_headers = stage2_headers
        self._fallback = fallback_node
        self._router: Agent[None, RouterDecision] | None = None
        self._workers: dict[str, Agent[None, PDSLiveFindDatasetOutput]] = {}
        self._stack: AsyncExitStack | None = None

    async def __aenter__(self) -> "LayeredFinder":
        self._stack = AsyncExitStack()
        await self._stack.__aenter__()
        self._router = build_router_agent(model=self._model)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        assert self._stack is not None
        try:
            await self._stack.__aexit__(exc_type, exc, tb)
        finally:
            self._workers.clear()
            self._router = None
            self._stack = None

    async def route(self, query: str) -> RouterDecision:
        """Run the router only — no Stage 1 or Stage 2 MCPs touched."""
        assert self._router is not None, "Use inside 'async with LayeredFinder()'"
        return (await self._router.run(query)).output

    async def _get_worker(self, node: str) -> Agent[None, PDSLiveFindDatasetOutput]:
        node = node.lower()
        if node not in self._workers:
            assert self._stack is not None
            agent = build_layered_finder(
                node,
                model=self._model,
                reasoning_effort=self._effort,
                stage2_url=self._stage2_url,
                stage2_headers=self._stage2_headers,
            )
            await self._stack.enter_async_context(agent)
            self._workers[node] = agent
        return self._workers[node]

    async def warm(self, nodes: list[str] | None = None) -> None:
        """Pre-build workers and hit each MCP transport with a no-op RPC.

        Stage 1 (sequential): ``_get_worker(node)`` for every node. The
        MCP transport's ``__aenter__`` registers anyio cancel scopes that
        MUST be exited from the SAME task that entered them — so we
        enter them one at a time from the caller's task (the same task
        that will eventually run ``__aexit__``). Parallelizing this with
        ``asyncio.gather`` triggers a "cancel scope in different task"
        RuntimeError at shutdown.

        Stage 2 (parallel): ``list_tools()`` against every transport. These
        are pure HTTP requests with no scope ownership, so we can fire
        them in parallel for a real ``tools/list`` RPC that confirms each
        FastMCP Cloud container is awake.

        FastMCP cold-start is per-container, not per-transport, so even
        sequential entry only pays the cold start once per server (~20-30s
        each for stage1 + stage2); the remaining 14 transports reuse the
        warm container and open in <1s.

        ``nodes=None`` warms every node in the registry.
        """
        assert self._stack is not None, "Use inside 'async with LayeredFinder()'"
        targets = [n.lower() for n in (nodes if nodes is not None else SUPPORTED_NODES)]
        for node in targets:
            await self._get_worker(node)

        async def _list(ts):
            list_fn = getattr(ts, "list_tools", None)
            if callable(list_fn):
                try:
                    await list_fn()
                except Exception:  # noqa: BLE001
                    pass

        pings = []
        for node in targets:
            worker = self._workers[node]
            for ts in getattr(worker, "toolsets", ()) or ():
                pings.append(_list(ts))
        if pings:
            await asyncio.gather(*pings)

    async def run(
        self,
        query: str,
    ) -> tuple[RouterDecision, PDSLiveFindDatasetOutput]:
        """Route then run the worker. Returns (decision, output)."""
        decision = await self.route(query)
        node = decision.primary_node or self._fallback
        worker = await self._get_worker(node)
        result = await worker.run(query)
        return decision, result.output

    async def run_traced(
        self,
        query: str,
        *,
        router_usage=None,
        worker_usage=None,
    ) -> tuple[RouterDecision, PDSLiveFindDatasetOutput, list, list]:
        """Like ``run()`` but also returns the worker's full message history
        plus per-call usage objects.

        If ``router_usage`` / ``worker_usage`` are passed in (instances of
        pydantic-ai's ``RunUsage``), pydantic-ai accumulates into them in
        place — so the caller still sees tokens spent before a mid-run
        failure (e.g. context overflow). The same instances are also
        returned in the result tuple's last element.

        Returns:
            ``(decision, output, worker_messages, [router_usage, worker_usage])``.
            Convert each with ``run_eval._usage_to_dict`` and combine with
            ``run_eval._sum_usage``.
        """
        from pydantic_ai.usage import RunUsage

        assert self._router is not None, "Use inside 'async with LayeredFinder()'"
        if router_usage is None:
            router_usage = RunUsage()
        if worker_usage is None:
            worker_usage = RunUsage()
        router_result = await self._router.run(query, usage=router_usage)
        decision = router_result.output
        node = decision.primary_node or self._fallback
        worker = await self._get_worker(node)
        worker_result = await worker.run(query, usage=worker_usage)
        return (
            decision,
            worker_result.output,
            list(worker_result.all_messages()),
            [router_usage, worker_usage],
        )


async def run_layered_query(
    query: str,
    *,
    model: str = "openai:gpt-5.2",
    reasoning_effort: Literal["low", "medium", "high"] = "high",
    stage2_url: str | None = None,
    stage2_headers: dict[str, str] | None = None,
    fallback_node: str = "geo",
) -> tuple[RouterDecision, PDSLiveFindDatasetOutput]:
    """Single-shot layered query. Opens and closes one transport set.

    For multiple queries, instantiate ``LayeredFinder`` directly so the
    MCP transports are reused across queries.
    """
    async with LayeredFinder(
        model=model,
        reasoning_effort=reasoning_effort,
        stage2_url=stage2_url,
        stage2_headers=stage2_headers,
        fallback_node=fallback_node,
    ) as lf:
        return await lf.run(query)


async def run_layered_batch(
    queries: list[str],
    *,
    model: str = "openai:gpt-5.2",
    reasoning_effort: Literal["low", "medium", "high"] = "high",
    stage2_url: str | None = None,
    stage2_headers: dict[str, str] | None = None,
    fallback_node: str = "geo",
) -> list[tuple[RouterDecision, PDSLiveFindDatasetOutput]]:
    """Run a batch of queries reusing one set of MCP transports.

    Pays the MCP spin-up cost only for the first query that visits each
    node — every subsequent query for the same node reuses the open
    transports. For N queries spanning M unique nodes this drops you from
    N subprocess spawns to M.
    """
    results: list[tuple[RouterDecision, PDSLiveFindDatasetOutput]] = []
    async with LayeredFinder(
        model=model,
        reasoning_effort=reasoning_effort,
        stage2_url=stage2_url,
        stage2_headers=stage2_headers,
        fallback_node=fallback_node,
    ) as lf:
        for q in queries:
            results.append(await lf.run(q))
    return results


# ---------------------------------------------------------------------------
# Finder config factory (used by finder.py dispatcher)
# ---------------------------------------------------------------------------


def get_finder_config(node: str):
    """Return the live mode configuration for the unified finder.

    Args:
        node: PDS node identifier. Required — there is no multi-node mode.
            For runtime classification of an unknown-node query, use
            ``LayeredFinder`` / ``run_layered_query`` which routes via the
            tool-less ``build_router_agent()``.
    """
    from pydantic_code.finder import FinderConfig

    if not node:
        raise ValueError(
            "get_finder_config requires a node. Multi-node mode was removed; "
            "use LayeredFinder / run_layered_query for runtime node classification."
        )

    return FinderConfig(
        system_prompt=_build_single_node_prompt(node),
        mcp_server=_build_mcp(),
        output_type=PDSLiveFindDatasetOutput,
    )
