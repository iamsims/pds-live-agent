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
# Tool filtering — only expose the 5 catalog tools from the remote MCP server
# ---------------------------------------------------------------------------

_ALLOWED_CATALOG_TOOLS = frozenset(
    [
        "pds_catalog_search_tool",
        "pds_catalog_get_dataset_tool",
        "pds_catalog_list_missions_tool",
        "pds_catalog_list_targets_tool",
        "pds_catalog_stats_tool",
    ]
)


def _catalog_tool_filter(ctx, tool_def) -> bool:
    """Only allow the 5 PDS catalog tools through to the agent."""
    return tool_def.name in _ALLOWED_CATALOG_TOOLS


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

# Kept lean — tool signatures come from the MCP server; the prompt focuses
# on workflow and reasoning strategy.

_PDS_NODES = ["atm", "geo", "img", "naif", "ppi", "rms", "sbn"]

PDS_CATALOG_FINDER_SYSTEM_PROMPT = (
    "You are a dataset-discovery assistant for the NASA PDS catalog "
    "(" + ", ".join(_PDS_NODES) + " nodes, ~12k datasets).\n\n"
    "Tools are provided via MCP. You MUST call at least one search tool "
    "before returning results.\n\n"
    "Interpret the user's science question, infer the relevant mission(s) "
    "and instrument(s), then search using mission/instrument keywords — not "
    "raw science terms alone. Return both PDS4 and PDS3 versions when available. "
    "Only return candidates you've seen in tool results — never invent IDs. "
    "Stay under ~10 tool calls. If nothing matches, return an empty list.\n"
)


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


def _resolve_url(url: str | None) -> str:
    if url:
        return url
    env = os.environ.get("PDS_CATALOG_MCP_URL")
    if env:
        return env
    raise RuntimeError(
        "PDS catalog MCP URL not configured. Pass url=... to "
        "build_pds_catalog_finder() or set PDS_CATALOG_MCP_URL in the environment."
    )


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
    reasoning_effort: str = "low",
    headers: dict[str, str] | None = None,
) -> Agent[None, PDSCatalogFindDatasetOutput]:
    """Build a pydantic-ai Agent that talks to the FastMCP catalog server.

    The agent must be used inside ``async with agent.run_mcp_servers():`` —
    the context manager opens the MCP connection once and closes it on exit.
    Re-entering for every query is wasteful; for a batch of queries, wrap
    the whole batch in a single ``async with``.

    Args:
        url: FastMCP server URL. Defaults to ``$PDS_CATALOG_MCP_URL``.
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
