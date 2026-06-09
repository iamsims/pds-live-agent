"""Unified pydantic-ai PDS dataset finder — catalog mode.

    build_finder(kind="catalog")
        → connects via streamable HTTP to a FastMCP cloud server fronting
          ``akd_ext.tools.pds.pds_catalog`` (uses
          ``PDS_CATALOG_MCP_URL`` + ``FAST_MCP_AUTH`` from the environment).

For **live** dataset discovery use the layered (Stage 1 + Stage 2) finder in
``pydantic_code.live_finder.pds_finder`` — a router-driven ``LiveFinder``
that classifies the query to a node and runs that node's layered worker. See
``LiveFinder`` / ``run_live_query`` / ``run_live_batch``.

Usage:
    >>> from pydantic_code.finder import build_finder
    >>> agent = build_finder(kind="catalog")
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
from pydantic_ai.settings import ModelSettings


FinderKind = Literal["catalog"]


# ---------------------------------------------------------------------------
# FinderConfig — the single abstraction each mode module provides
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FinderConfig:
    """Everything a finder mode must supply.

    ``toolsets`` is a list so the agent can be given one or more MCP toolsets.
    """

    system_prompt: str
    toolsets: list
    output_type: type[BaseModel]


def _get_config(kind: FinderKind, **kwargs) -> FinderConfig:
    """Lazy-import the config from the appropriate mode module."""
    if kind == "catalog":
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
    kind: FinderKind = "catalog",
    *,
    model: str = "openai:gpt-5.2",
    reasoning_effort: Literal["low", "medium", "high"] = "high",
    catalog_url: str | None = None,
    catalog_headers: dict[str, str] | None = None,
) -> Agent[None, FindDatasetOutput]:
    """Build a pydantic-ai Agent in catalog mode.

    Use inside ``async with agent:`` — that context starts the MCP transport
    once and reuses it for every ``agent.run(...)`` call inside the block.

    For live dataset discovery use the router-driven ``LiveFinder`` /
    ``run_live_query`` in ``pydantic_code.live_finder.pds_finder`` instead.

    Args:
        kind: Only ``"catalog"`` is supported. Live discovery is handled by
            the layered finder in ``pydantic_code.live_finder.pds_finder``.
        model: pydantic-ai model string.
        reasoning_effort: For reasoning models.
        catalog_url: Override ``$PDS_CATALOG_MCP_URL``.
        catalog_headers: Override the default Bearer-from-env header.
    """
    config = _get_config(
        kind,
        catalog_url=catalog_url,
        catalog_headers=catalog_headers,
    )

    return Agent(
        model,
        toolsets=config.toolsets,
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
