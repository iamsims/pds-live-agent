"""Unified pydantic-ai PDS dataset finder — live or catalog mode.

Pick a configuration via the ``kind`` argument:

    build_finder(kind="live")
        → connects via stdio to ``pydantic_code.mcp_server`` (subprocess);
          the served tools fetch directories from any supported PDS node live.

    build_finder(kind="live", node="ppi")
        → same as above but with a PPI-focused system prompt (no routing step).

    build_finder(kind="catalog")
        → connects via streamable HTTP to a FastMCP cloud server fronting
          ``akd_ext.tools.pds.pds_catalog`` (uses
          ``PDS_CATALOG_MCP_URL`` + ``FAST_MCP_AUTH`` from the environment).

Both modes share the same model, output schema, and run settings — only the
system prompt and MCP server differ, so any difference in eval results comes
from the tool layer (live HTTP vs pre-scraped catalog) rather than the agent
harness.

Usage:
    >>> from pydantic_code.finder import build_finder
    >>> agent = build_finder(kind="live", node="ppi")
    >>> async with agent:
    ...     result = await agent.run("Cassini magnetospheric plasma data")
    >>> for c in result.output.candidates:
    ...     print(c.dataset_id, c.title, c.node)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.mcp import MCPServerStdio, MCPServerStreamableHTTP
from pydantic_ai.settings import ModelSettings


FinderKind = Literal["live", "catalog"]


# ---------------------------------------------------------------------------
# FinderConfig — the single abstraction each mode module provides
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FinderConfig:
    """Everything a finder mode must supply."""

    system_prompt: str
    mcp_server: MCPServerStdio | MCPServerStreamableHTTP
    output_type: type[BaseModel]


def _get_config(kind: FinderKind, **kwargs) -> FinderConfig:
    """Lazy-import the config from the appropriate mode module."""
    if kind == "live":
        from pydantic_code.live_finder.pds_finder import get_finder_config

        return get_finder_config(node=kwargs.get("node"))
    elif kind == "catalog":
        from pydantic_code.catalog_finder.pds_catalog_finder import get_finder_config

        return get_finder_config(
            url=kwargs.get("catalog_url"),
            headers=kwargs.get("catalog_headers"),
        )
    else:
        raise ValueError(f"Unknown FinderKind: {kind!r}")


# ---------------------------------------------------------------------------
# Shared output schema — union of fields the two finders surface.
# Kept here (not in mode modules) so the comparator gets a single type.
# ---------------------------------------------------------------------------


class DatasetCandidate(BaseModel):
    """One ranked candidate from either finder.

    Most fields are optional because the two modes surface different attributes:

      * live mode populates ``path`` (relative to the node's base URL) plus
        whatever the inspected label exposes (``dataset_id``, ``pds_version``,
        ``mission``, ``title``, ``node``).
      * catalog mode populates ``dataset_id``, ``title``, ``mission``,
        ``node``, ``pds_version`` from the catalog entry.

    Fields the agent doesn't have data for should be left as ``None``.
    """

    dataset_id: str | None = Field(
        default=None,
        description=(
            "Canonical PDS3 DATA_SET_ID or PDS4 logical_identifier. "
            "Live: pulled from inspected label fields. "
            "Catalog: pulled from the matched catalog entry."
        ),
    )
    path: str | None = Field(
        default=None,
        description=(
            "Path relative to the node's base URL (live mode only). "
            "Leave None in catalog mode."
        ),
    )
    title: str | None = Field(default=None, description="Dataset title from label or catalog entry")
    mission: str | None = Field(default=None, description="Top-level mission")
    node: str | None = Field(
        default=None,
        description="Owning PDS Discipline Node (atm/geo/img/naif/ppi/rms/sbn) — catalog mode",
    )
    pds_version: str | None = Field(default=None, description="'PDS3' or 'PDS4'")
    reasoning: str = Field(description="Why this dataset matches the query")


class FindDatasetOutput(BaseModel):
    """Output for either finder mode."""

    candidates: list[DatasetCandidate] = Field(
        default_factory=list,
        description="Datasets that match the query, ordered most-relevant-first",
    )
    summary: str = Field(description="Short summary of the search and what was found")


# ---------------------------------------------------------------------------
# Unified factory + convenience runner
# ---------------------------------------------------------------------------


def build_finder(
    kind: FinderKind,
    *,
    node: str | None = None,
    model: str = "openai:gpt-5.2",
    reasoning_effort: Literal["low", "medium", "high"] = "high",
    catalog_url: str | None = None,
    catalog_headers: dict[str, str] | None = None,
) -> Agent[None, FindDatasetOutput]:
    """Build a pydantic-ai Agent in live or catalog mode.

    The two modes share model, output schema, and run settings; only the
    system prompt and MCP server are swapped.

    Use inside ``async with agent:`` — that context starts the MCP transport
    once and reuses it for every ``agent.run(...)`` call inside the block.

    Args:
        kind: ``"live"`` or ``"catalog"``.
        node: PDS node identifier (live mode only). When specified, builds a
            single-node agent with a focused prompt. When None, builds a
            multi-node agent that routes via ``pds_select_node``.
        model: pydantic-ai model string (kept identical between modes).
        reasoning_effort: For reasoning models. Kept identical between modes.
        catalog_url: Override ``$PDS_CATALOG_MCP_URL`` (catalog mode only).
        catalog_headers: Override the default Bearer-from-env header
            (catalog mode only).
    """
    config = _get_config(kind, node=node, catalog_url=catalog_url, catalog_headers=catalog_headers)

    return Agent(
        model,
        toolsets=[config.mcp_server],
        output_type=FindDatasetOutput,
        system_prompt=config.system_prompt,
        model_settings=ModelSettings(extra_body={"reasoning_effort": reasoning_effort}),
        retries=2,
    )


async def run_finder(
    kind: FinderKind,
    query: str,
    **build_kwargs,
) -> FindDatasetOutput:
    """Run one query through the finder of the chosen kind.

    Opens and closes a fresh MCP transport per call. For batches of queries,
    build the agent yourself and reuse a single ``async with agent:`` block
    so the transport is opened once.
    """
    agent = build_finder(kind, **build_kwargs)
    async with agent:
        result = await agent.run(query)
    return result.output
