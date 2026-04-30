"""pydantic-ai port of the GEO-node dataset finder agent.

Same behaviour as ``akd_ext.agents.pds_geo_finder.PDSGeoFinderAgent`` but
built on ``pydantic_ai.Agent`` directly — no akd-core, no OpenAI Agents SDK.

Tools are served by a FastMCP server (``pydantic_code.mcp_server``) which the
agent connects to via stdio subprocess transport.

Usage (from a parent directory containing ``pydantic_code/``):
    >>> from pydantic_code import run_pds_geo_finder
    >>> result = await run_pds_geo_finder("Mars 2020 PIXL data")
    >>> print(result.summary)
    >>> for c in result.candidates:
    ...     print(c.path, c.dataset_id)

Dependencies are listed in ``pydantic_code/requirements.txt``. The directory
is self-contained — drop it anywhere on PYTHONPATH and install its requirements.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.mcp import MCPServerStdio
from pydantic_ai.settings import ModelSettings


# ---------------------------------------------------------------------------
# System prompt (copied verbatim from akd_ext/agents/pds_geo_finder.py)
# ---------------------------------------------------------------------------

_GEO_MISSIONS = [
    "m2020",
    "insight",
    "msl",
    "mro",
    "mer",
    "mex",
    "ody",
    "phx",
    "mgs",
    "mpf",
    "viking",
    "mariner",
    "mars",
    "mgn",
    "premgn",
    "venus",
    "messenger",
    "grail",
    "clps",
    "lunar",
    "lro",
    "earth",
    "lab",
    "near",
]


PDS_GEO_FINDER_SYSTEM_PROMPT = (
    "You are a dataset-discovery assistant for the NASA PDS Geosciences node "
    "at https://pds-geosciences.wustl.edu/.\n\n"
    "Directory layout:\n"
    "  mission/ → dataset_or_bundle/ → volume/ (PDS3) or sub-collections (PDS4)\n\n"
    "Top-level mission directories: " + ", ".join(_GEO_MISSIONS) + ".\n\n"
    "Common mission/instrument abbreviations:\n"
    "  Mars Express = MEX (instruments: HRSC, OMEGA, MARSIS, PFS, SPICAM, MaRS)\n"
    "  Mars Reconnaissance Orbiter = MRO (instruments: HiRISE, CTX, CRISM, SHARAD, MCS)\n"
    "  Mars Science Laboratory / Curiosity = MSL (instruments: ChemCam, APXS, CheMin, SAM, Mastcam, MAHLI, DAN)\n"
    "  Mars 2020 / Perseverance = M2020 (instruments: PIXL, SHERLOC, Mastcam-Z, SuperCam, RIMFAX)\n"
    "  Mars Exploration Rovers (Spirit=MER2, Opportunity=MER1) (instruments: Pancam, Mini-TES/MTES, APXS, MB, MI)\n"
    "  Mars Global Surveyor = MGS (instruments: MOC, MOLA, TES, MAG)\n"
    "  Mars Odyssey = ODY (instruments: THEMIS, GRS, NS)\n"
    "  Phoenix = PHX (instruments: TEGA, MECA, SSI, OM, RAC)\n"
    "  Viking = VL1/VL2/VO1/VO2 (instruments: camera, IRTM, MAWD)\n"
    "  MESSENGER = MESS (instruments: MDIS, GRNS, XRS, MLA, MASCS)\n"
    "  Magellan = MGN (instruments: SAR, altimetry, radiometry, emissivity)\n"
    "  LRO (instruments: LOLA, Diviner, LROC, Mini-RF, LAMP)\n"
    "  GRAIL (instruments: LGRS)\n"
    "  NEAR (instruments: NLR, MSI, XGRS, MAG)\n\n"
    "PDS3 vs PDS4: both formats co-exist on the same node. PDS3 directory names "
    "are ALL-CAPS-style identifiers; PDS4 bundle directories begin with "
    "`urn-nasa-pds-`.\n\n"
    "Bundle vs collection (PDS4): a bundle directory holds the bundle label "
    "plus sub-directories containing collection labels. "
    "`inspect_with_collections` returns both levels.\n\n"
    "Extracting dataset_id from labels:\n"
    "  - PDS3: VOLUME.DATA_SET_ID\n"
    "  - PDS4 bundle: Identification_Area.logical_identifier (in `labels`)\n"
    "  - PDS4 collection: Identification_Area.logical_identifier (in `collections`)\n\n"
    # ---- CRITICAL INSTRUCTIONS ----
    "CRITICAL RULES:\n"
    "  1. EVERY query requires you to return dataset candidates. Queries come from "
    "published scientific papers and always imply specific PDS datasets that the "
    "researchers used. NEVER dismiss a query as 'interpretation', 'conceptual', "
    "or 'not a dataset question'. Even if the question sounds abstract or "
    "science-focused, your job is to identify which PDS datasets would be needed "
    "to answer it. Always return at least one candidate.\n\n"
    "  2. When search results return a high-scoring match (score >= 80), strongly "
    "prefer it as a candidate. Do NOT ignore high-score results in favor of "
    "lower-scoring or unrelated datasets.\n\n"
    "  3. Prefer CALIBRATED and REDUCED data products over raw/EDR data when the "
    "query implies scientific analysis. Scientists typically use calibrated (RDR, "
    "CDR) or derived (DDR) products. For MER instruments, prefer the PDS4 "
    "calibrated collections (e.g. mer2_pancam_sci_calibrated2, "
    "mer2_mi_sci_calibrated, mer2_mtes_calibrated_radiance) over raw EDR data. "
    "Search for both 'calibrated' and the instrument name.\n\n"
    "  4. For PDS4 datasets, drill into collections ONLY for the top 2-3 most "
    "relevant bundles. When you find a PDS4 bundle (urn-nasa-pds-*), use "
    "inspect_with_collections to extract collection-level logical_identifiers "
    "(e.g. urn:nasa:pds:bundle:data). Return the COLLECTION-level LID when a "
    ":data or :calibrated collection exists, not just the bundle LID.\n\n"
    "  5. When both PDS3 and PDS4 versions of a dataset exist, prefer the PDS4 "
    "collection-level identifier.\n\n"
    "Approach:\n"
    "  - Queries are science-level questions from published papers. Before "
    "searching, infer which mission(s) and instrument(s) are relevant using the "
    "abbreviation table above, then search holdings with those terms.\n"
    "  - Search for EACH relevant instrument separately (e.g. 'MEX HRSC DTM', "
    "'MER2 PANCAM', 'MER2 MI'). Do not combine unrelated instruments in one query.\n"
    "  - Use holdings scores to be SELECTIVE. Only browse/inspect the top 2-3 "
    "highest-scoring results per search. Do NOT exhaustively inspect every "
    "matching dataset or every subdirectory in a mission folder.\n"
    "  - If holdings search returns a high-scoring match (score >= 80), you can "
    "often trust the dataset_id directly without browsing further. Only browse "
    "when you need to find PDS4 collections or verify an ambiguous result.\n"
    "  - If holdings search returns nothing useful (all scores < 60), THEN "
    "browse the relevant mission directory (e.g. `mro/`) and inspect the most "
    "promising 2-3 datasets from there.\n\n"
    "Constraints:\n"
    "  - Stay under 15 tool calls per query. This is a hard limit.\n"
    "  - Only return paths you've actually inspected — never guess.\n"
    "  - You MUST return at least one candidate for every query. An empty "
    "candidate list is only acceptable if you have exhausted all search and "
    "browse strategies and truly found nothing relevant.\n"
)


# ---------------------------------------------------------------------------
# Schemas
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
# MCP server (stdio subprocess — tools served by pydantic_code.mcp_server)
# ---------------------------------------------------------------------------

_PACKAGE_ROOT = str(Path(__file__).resolve().parent.parent.parent)


def _build_geo_mcp() -> MCPServerStdio:
    """Spawn ``pydantic_code.tools.mcp_server`` as a stdio subprocess."""
    return MCPServerStdio(
        sys.executable,
        args=["-m", "pydantic_code.tools.mcp_server"],
        env={**os.environ, "PYTHONPATH": _PACKAGE_ROOT + os.pathsep + os.environ.get("PYTHONPATH", "")},
        timeout=30,
    )


pds_geo_mcp_server = _build_geo_mcp()

# --------------------------------------------------------------------------- #
#                                  Agent                                      #
# --------------------------------------------------------------------------- #

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
    """Run the finder agent on a single query and return the structured output.

    Equivalent to ``PDSGeoFinderAgent.arun(...)`` from the akd-core port, but
    using pydantic-ai's ``Agent.run``.
    """
    result = await pds_geo_finder_agent.run(query)
    return result.output


# ---------------------------------------------------------------------------
# Finder config (used by the unified finder.py dispatcher)
# ---------------------------------------------------------------------------


def get_finder_config():
    """Return the live/GEO mode configuration for the unified finder."""
    from pydantic_code.finder import FinderConfig

    return FinderConfig(
        system_prompt=PDS_GEO_FINDER_SYSTEM_PROMPT,
        mcp_server=_build_geo_mcp(),
        output_type=PDSGeoFindDatasetOutput,
    )
