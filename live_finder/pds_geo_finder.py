"""GEO-node dataset finder agent — now delegates to the generalized pds_finder.

This module is kept for backward compatibility. All new code should use
``pds_finder.get_finder_config(node="geo")`` instead.

The schemas (PDSGeoFindDatasetOutput, PDSGeoDatasetCandidate, etc.) are
still exported so that existing callers and the eval runner continue to work.
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from .pds_finder import (
    _build_mcp,
    _build_single_node_prompt,
)


# ---------------------------------------------------------------------------
# System prompt — generated from the single-node builder for "geo"
# ---------------------------------------------------------------------------

PDS_GEO_FINDER_SYSTEM_PROMPT = _build_single_node_prompt("geo")


# ---------------------------------------------------------------------------
# Schemas (kept for backward compat — alias the new generalized schemas)
# ---------------------------------------------------------------------------


class PDSGeoFindDatasetInput(BaseModel):
    """Input for the PDS Geo finder agent."""

    query: str = Field(
        ...,
        description=(
            "Natural-language query, e.g. 'Mars 2020 PIXL data', "
            "'Cassini imaging of Saturn', 'lunar gravity from GRAIL'."
        ),
    )


class PDSGeoDatasetCandidate(BaseModel):
    """One ranked dataset candidate found by the agent."""

    path: str = Field(description="Path relative to https://pds-geosciences.wustl.edu/")
    dataset_id: str | None = Field(
        default=None,
        description=(
            "Canonical identifier extracted from the inspected label, when known. "
            "PDS3: VOLUME.DATA_SET_ID. "
            "PDS4: Identification_Area.logical_identifier."
        ),
    )
    title: str | None = Field(
        default=None,
        description=(
            "Dataset title from the label (PDS4 Identification_Area.title or "
            "PDS3 VOLUME.VOLUME_SET_NAME), if known"
        ),
    )
    pds_version: str | None = Field(default=None, description="'PDS3' or 'PDS4' if known")
    mission: str | None = Field(default=None, description="Top-level mission directory the dataset lives under")
    reasoning: str = Field(description="Why this dataset matches the query")


class PDSGeoFindDatasetOutput(BaseModel):
    """Output for the PDS Geo finder agent."""

    candidates: list[PDSGeoDatasetCandidate] = Field(
        default_factory=list,
        description="Datasets that match the query, ordered most-relevant-first",
    )
    summary: str = Field(description="Short summary of the search and what was found")


# ---------------------------------------------------------------------------
# MCP server + Agent (kept for backward compat direct usage)
# ---------------------------------------------------------------------------

def _build_geo_mcp():
    """Spawn ``pydantic_code.tools.mcp_server`` as a stdio subprocess."""
    return _build_mcp()


pds_geo_mcp_server = _build_geo_mcp()

pds_geo_finder_agent: Agent[None, PDSGeoFindDatasetOutput] = Agent(
    "openai:gpt-5.2",
    output_type=PDSGeoFindDatasetOutput,
    system_prompt=PDS_GEO_FINDER_SYSTEM_PROMPT,
    model_settings=ModelSettings(extra_body={"reasoning_effort": "high"}),
    toolsets=[pds_geo_mcp_server],
    retries=2,
)


# ---------------------------------------------------------------------------
# Convenience entrypoint
# ---------------------------------------------------------------------------


async def run_pds_geo_finder(query: str) -> PDSGeoFindDatasetOutput:
    """Run the GEO finder agent on a single query."""
    result = await pds_geo_finder_agent.run(query)
    return result.output


# ---------------------------------------------------------------------------
# Finder config — delegates to generalized pds_finder
# ---------------------------------------------------------------------------


def get_finder_config(node: str | None = None):
    """Return finder config.

    Args:
        node: If specified, builds for that node. Defaults to "geo"
            for backward compatibility.
    """
    from .pds_finder import get_finder_config as _get_finder_config

    return _get_finder_config(node=node or "geo")
