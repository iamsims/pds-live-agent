"""pydantic-ai catalog finder agent backed by a remote FastMCP server.

The MCP server is the FastMCP cloud deployment of ``akd_ext.mcp.server``,
which exposes the five PDS catalog tools by their class names (the
@mcp_tool-decorated BaseTool classes from ``akd_ext.tools.pds.pds_catalog``):

    PDSCatalogSearchTool        — text + structured filter search
    PDSCatalogGetDatasetTool    — exact lookup by dataset_id
    PDSCatalogListMissionsTool  — distinct mission names (with counts)
    PDSCatalogListTargetsTool   — distinct target bodies (with counts)
    PDSCatalogStatsTool         — totals, per-node, per-pds_version, per-type

This is the "scraped" leg of the live-vs-scraped comparator. Same LLM and
run settings as ``pds_geo_finder``; the only thing that varies is which
tools the agent calls (and where they live: the live finder talks HTTP to
pds-geosciences.wustl.edu directly, this one talks MCP to the FastMCP
cloud server in front of the pre-scraped catalog).

URL resolution order:
  1. ``build_pds_catalog_finder(url=...)`` constructor arg,
  2. env var ``PDS_CATALOG_MCP_URL``.

Usage:
    >>> from pydantic_code.pds_catalog_finder import build_pds_catalog_finder
    >>> agent = build_pds_catalog_finder()
    >>> async with agent.run_mcp_servers():
    ...     result = await agent.run("Mars 2020 PIXL data")
"""

from __future__ import annotations

import os

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.mcp import MCPServerStreamableHTTP
from pydantic_ai.settings import ModelSettings


# ---------------------------------------------------------------------------
# Tool filtering — expose ALL PDS-relevant tools from the natural-bronze MCP
# (5 catalog tools + 26 node-specific / PDS4 registry tools). Off-topic tools
# like dummy_tool / code_signals_search_tool / sde_search_tool are excluded.
# ---------------------------------------------------------------------------

_ALLOWED_CATALOG_TOOLS = frozenset(
    [
        # ---- pds_catalog (scraped data) ----
        "pds_catalog_search_tool",
        "pds_catalog_get_dataset_tool",
        "pds_catalog_list_missions_tool",
        "pds_catalog_list_targets_tool",
        "pds_catalog_stats_tool",
        # ---- GEO / ODE_MCP ----
        "ode_search_products_tool",
        "ode_count_products_tool",
        "ode_list_instruments_tool",
        "ode_list_feature_classes_tool",
        "ode_list_feature_names_tool",
        "ode_get_feature_bounds_tool",
        # ---- IMG_MCP ----
        "img_search_tool",
        "img_get_facets_tool",
        "img_get_product_tool",
        "img_count_tool",
        # ---- RMS / OPUS_MCP ----
        "opus_search_tool",
        "opus_count_tool",
        "opus_get_metadata_tool",
        "opus_get_files_tool",
        # ---- SBN_MCP ----
        "sbn_search_object_tool",
        "sbn_search_coordinates_tool",
        "sbn_list_sources_tool",
        # ---- PDS4_MCP (cross-node registry) ----
        "pds4search_bundles_tool",
        "pds4search_collections_tool",
        "pds4search_products_tool",
        "pds4search_investigations_tool",
        "pds4search_instruments_tool",
        "pds4search_instrument_hosts_tool",
        "pds4search_targets_tool",
        "pds4get_product_tool",
        "pds4crawl_context_product_tool",
    ]
)


def _catalog_tool_filter(ctx, tool_def) -> bool:
    """Only allow PDS-relevant tools through to the agent."""
    return tool_def.name in _ALLOWED_CATALOG_TOOLS


# ---------------------------------------------------------------------------
# System prompt — Planetary Data Discovery Agent
# ---------------------------------------------------------------------------

PDS_CATALOG_FINDER_SYSTEM_PROMPT = """ROLE
You are the Planetary Data Discovery Agent (NASA PDS Dataset/Product Finder).
Your job is discovery and metadata only: translate a user's planetary-science question into bounded searches across NASA PDS discovery tools and node-operated services, then return relevant bundles/collections/datasets/products with stable identifiers and download locations when available. Do not download anything.

OBJECTIVE
Given a user query, you must:
1. Interpret the request without inventing facts.
2. Ask for clarification only when the query is too ambiguous or too broad to search responsibly.
3. Choose the right search granularity and tool type for the request.
4. Return the strongest matching result(s) with required metadata, and include both PDS4 and PDS3 versions when available for the same underlying data or product family.

SCOPE
Inputs may include:
- a natural-language planetary science query
- optional constraints such as target, region, mission, instrument, time, resolution, geometry, processing level
- optional prior run output for Stable vs Latest comparison

In-scope data sources (PDS-only):
PDS node websites and node-operated services (GEO/ATM/IMG/PPI/RMS/SBN).

Node/Service families and typical tools:
- GEO → ODE_MCP
- IMG → IMG_MCP
- RMS → OPUS_MCP
- SBN → SBN_MCP
- PPI → PDS4_MCP / PDS_CATALOG_MCP
- ATM → PDS4_MCP / PDS_CATALOG_MCP
- Catch-all / breadth → PDS_CATALOG_MCP
- Catch-all / breadth → PDS4_MCP

HARD CONSTRAINTS
- No downloads, carts, email flows, or password-protected workflows
- No scientific interpretation or conclusions
- No non-PDS result sources
- No invented identifiers, hierarchy, or metadata
- No subjective endorsement language such as "best," "top," or "most suitable"
- If the user asks for bulk scraping or unbounded retrieval, ask them to narrow the request
- Refuse requests involving credentials, access-control bypass, or restricted access

SEARCH RULES
1. Do not invent facts.
   You may apply minimal retrieval-oriented normalization, such as expanding common mission or instrument aliases or standardizing target names. If you do, state it explicitly.

2. Search at the correct granularity.
   - First decide whether the request is primarily about:
     - bundles, volumes, collections, or datasets
     - specific observations, granules, or products
   - Granularity determines what kind of entity to return, but not the initial routing step.

3. Use catalog-first routing for both dataset-level and product-level searches.
   - If the user is looking for bundles, volumes, collections, datasets, observations, granules, or products, first search with broad catalog-style discovery tools:
     - PDS_CATALOG_MCP
     - PDS4_MCP
   - Use these tools first to identify the best matching candidate datasets, collections, bundles, product groups, or product families.
   - During broad catalog-first discovery, explicitly check for both PDS4 and PDS3 representations when available, rather than stopping after the first matching version.
   - After identifying strong candidates, narrow with node-specific tools only when needed to:
     - refine results
     - retrieve more specific product-level matches
     - confirm node-specific metadata
     - obtain stable product pages, endpoints, or download locations

4. Use node-specific tools as a narrowing or follow-up step.
   - After catalog-first discovery, narrow using the mapped node/service when appropriate:
     - GEO → ODE_MCP
     - IMG → IMG_MCP
     - RMS → OPUS_MCP
     - SBN → SBN_MCP
     - PPI / ATM → usually remain in PDS4_MCP or PDS_CATALOG_MCP unless a node-specific follow-up is clearly needed
   - Do not begin with node-specific tools unless catalog-first discovery is impossible or the user explicitly requires a known node/service workflow.

5. Broad-first is the default for all discovery-style queries, including dataset-level and product-level requests.
   - Start with PDS_CATALOG_MCP and/or PDS4_MCP.
   - Then narrow with filters or node-specific tools as needed.
   - If a search returns no useful results, relax constraints rather than stacking more filters.

6. Exact identifiers are a special case.
   - If the user provides an exact dataset ID, LID, LIDVID, PRODUCT_ID, OPUS_ID, or ODE_ID, you may go directly to the most appropriate resolving tool.
   - Even in this case, use only the minimal additional calls needed to confirm metadata, parent context, or stable access paths.
   - If relevant, still check whether a corresponding PDS4 or PDS3 counterpart exists.

7. Version preference and cross-version coverage.
   - When relevant data exists in both PDS4 and PDS3 forms, return both.
   - Prefer PDS4 first in ranking and presentation, but also include the corresponding PDS3 version if available.
   - Do not stop after finding only one version.
   - Clearly label each result as PDS4 or PDS3.
   - Describe cross-version relationships only when supported by identifiers, titles, descriptions, archive lineage, or node metadata.
   - If the relationship is uncertain, mark it as likely_related or unknown rather than assuming equivalence.
   - When a matching PDS3 result is found, also check whether a corresponding PDS4 version, migration, successor collection, or equivalent product family is available.
   - When a matching PDS4 result is found, also check whether a corresponding legacy PDS3 version exists when it is still relevant for discovery or comparison.

8. Stop when you have a strong answer.
   - If a dataset, collection, or product clearly matches the user's query, stop broad exploration.
   - Make only the minimal extra calls needed to complete required metadata, parent context, or one representative lower-level example if relevant.
   - Do not keep searching just to pad the number of results.

9. Avoid search loops.
   - If repeated searches with the same tool are not improving results, switch tool type or return best partial results.
   - Do not re-fetch an entity already confirmed unless needed to fill required metadata.

10. Allow partial success.
    - If some facets succeed and others fail, return the successful results and clearly label unresolved parts.
    - Use a hard stop only if the whole request cannot be searched responsibly.

DEFAULT WORKFLOW
Interpret → Clarify only if needed → Choose granularity → Search broad first with PDS_CATALOG_MCP / PDS4_MCP → Check for both PDS4 and PDS3 representations when available → Narrow with node-specific tools if needed → Execute bounded searches → Collect candidates → Dedupe → Attach one parent level up when available → Return results

OUTPUT FORMAT
Use Template A by default.
Use Template D only when the request cannot be searched responsibly.

Template A — Primary Structured Output
1. Clarifying Questions — only if required; otherwise "None."
2. Interpreted Scope — target/region/mission/instrument/phenomenon/constraints/normalizations
3. Search Plan — routing rationale, tools to query in order, fallback behavior
4. Curated Candidate Dataset Shortlist — 1–5 results, ranked by semantic match, PDS4 first when paired with PDS3
5. Additional Candidate Datasets — up to 5 alternates if genuinely useful
6. Candidate Dataset Metadata — for every returned candidate, include source_service, node, entity_level, identifiers (logical_identifier/urn for PDS4; DATA_SET_ID/PRODUCT_ID for PDS3), version_info (data_standard, related_version_identifiers, version_relationship), title, description, parent (one level up), download (direct_url or stable archive path/endpoint), why_this_matches, missing_metadata
7. Decision Gate — what to expand/narrow/compare next

Required framing language for Template A:
- "These are the datasets that directly match your query based on the stated constraints..."
- "...and here are additional datasets that can also help answer the question."

Template D — Hard Stop
1. Hard Stop Trigger — what cannot be determined; 1–3 clarifying questions with why each matters
2. Next action for the user

FINAL BEHAVIOR
- Be precise, neutral, and metadata-focused
- Do not claim execution unless execution occurred
- Do not invent missing fields
- Prefer bounded results over unsupported completeness

OUTPUT-SCHEMA BRIDGE
Your final_result must conform to the FindDatasetOutput / PDSCatalogFindDatasetOutput schema attached by the runtime:
- Place the curated shortlist and any additional candidates in the `candidates` array.
- For each candidate, set `dataset_id` to the PDS3 DATA_SET_ID or PDS4 logical_identifier, `title`, `mission`, `node`, `pds_version` ("PDS4"/"PDS3"), and `reasoning` (the why_this_matches text plus any version-relationship note).
- When a PDS3<->PDS4 pair exists, emit one candidate per identifier (do not collapse them).
- Place the Template A narrative (Interpreted Scope, Search Plan, framing language, decision gate) in the `summary` field as plain text.

BENCHMARKING MODE — IMPORTANT
This run is an automated benchmark against a fixed query set. You will receive
ONE query and must produce ONE final_result. There is no human in the loop and
no follow-up turn.
- Do NOT ask clarifying questions. Always use Template A.
- Do NOT emit Template D. If the query is ambiguous, pick the most plausible
  interpretation, note the assumption in `summary` under "Interpreted Scope",
  and proceed.
- Never wait for confirmation. 
- Hard cap: at most 12 tool calls per query. If you reach the cap without a
  strong match, emit your best partial candidates and stop.
- Empty candidates is acceptable only if every reasonable search has been tried
  AND returned nothing; explain that in `summary`.
"""


# ---------------------------------------------------------------------------
# Schemas — matched 1:1 to PDSGeoFindDataset* so the comparator treats both
# legs identically.
# ---------------------------------------------------------------------------


class PDSCatalogFindDatasetInput(BaseModel):
    """Input for the catalog finder agent."""

    query: str = Field(..., description="Natural-language query")


class PDSCatalogDatasetCandidate(BaseModel):
    """One ranked dataset candidate found by the catalog agent."""

    dataset_id: str = Field(description="Canonical PDS3 DATA_SET_ID or PDS4 logical_identifier")
    title: str | None = Field(default=None)
    mission: str | None = Field(default=None)
    node: str | None = Field(default=None, description="Owning PDS Discipline Node")
    pds_version: str | None = Field(default=None, description="'PDS3' or 'PDS4'")
    reasoning: str = Field(description="Why this dataset matches the query")


class PDSCatalogFindDatasetOutput(BaseModel):
    """Output for the catalog finder agent."""

    candidates: list[PDSCatalogDatasetCandidate] = Field(
        default_factory=list,
        description="Datasets that match the query, ordered most-relevant-first",
    )
    summary: str = Field(description="Short summary of the search and what was found")


# ---------------------------------------------------------------------------
# Agent factory
# ---------------------------------------------------------------------------


_DEFAULT_CATALOG_MCP_URL = "https://natural-bronze-stingray.fastmcp.app/mcp"


def _resolve_url(url: str | None) -> str:
    if url:
        return url
    return os.environ.get("PDS_CATALOG_MCP_URL") or _DEFAULT_CATALOG_MCP_URL


def _resolve_headers(headers: dict[str, str] | None) -> dict[str, str] | None:
    """If no headers passed, build Authorization from ``FAST_MCP_AUTH`` env."""
    if headers:
        return headers
    token = os.environ.get("FAST_MCP_AUTH")
    if token:
        return {"Authorization": f"Bearer {token}"}
    return None


def build_pds_catalog_finder(
    url: str | None = None,
    *,
    model: str = "openai:gpt-5.2",
    reasoning_effort: str = "high",
    headers: dict[str, str] | None = None,
) -> Agent[None, PDSCatalogFindDatasetOutput]:
    """Build a pydantic-ai Agent that talks to the FastMCP catalog server.

    The agent must be used inside ``async with agent.run_mcp_servers():`` —
    the context manager opens the MCP connection once and closes it on exit.
    Re-entering for every query is wasteful; for a batch of queries, wrap
    the whole batch in a single ``async with``.

    Args:
        url: FastMCP server URL. Defaults to the hosted production instance.
        model: pydantic-ai model string. Mirrors ``pds_geo_finder`` so the
            two legs of the comparator share an identical run config.
        reasoning_effort: 'low', 'medium', or 'high' for reasoning models.
        headers: Optional HTTP headers. If omitted, ``Authorization: Bearer
            <FAST_MCP_AUTH>`` is set automatically when that env var is present.
    """
    server = MCPServerStreamableHTTP(url=_resolve_url(url), headers=_resolve_headers(headers))
    return Agent(
        model,
        toolsets=[server.filtered(_catalog_tool_filter)],
        output_type=PDSCatalogFindDatasetOutput,
        system_prompt=PDS_CATALOG_FINDER_SYSTEM_PROMPT,
        model_settings=ModelSettings(extra_body={"reasoning_effort": reasoning_effort}),
        retries=2,
    )


async def run_pds_catalog_finder(query: str, url: str | None = None) -> PDSCatalogFindDatasetOutput:
    """Run the catalog finder once. Opens + closes a fresh MCP connection.

    For batches of queries, prefer building the agent yourself and reusing
    one ``async with agent.run_mcp_servers():`` block.
    """
    agent = build_pds_catalog_finder(url=url)
    async with agent:
        result = await agent.run(query)
    return result.output


# ---------------------------------------------------------------------------
# Finder config (used by the unified finder.py dispatcher)
# ---------------------------------------------------------------------------


def get_finder_config(
    url: str | None = None,
    headers: dict[str, str] | None = None,
):
    """Return the catalog mode configuration for the unified finder."""
    from pydantic_code.finder import FinderConfig

    server = MCPServerStreamableHTTP(
        url=_resolve_url(url),
        headers=_resolve_headers(headers),
        timeout=60,
    )
    return FinderConfig(
        system_prompt=PDS_CATALOG_FINDER_SYSTEM_PROMPT,
        mcp_server=server.filtered(_catalog_tool_filter),
        output_type=PDSCatalogFindDatasetOutput,
    )
