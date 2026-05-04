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

PDS_GEO_FINDER_SYSTEM_PROMPT = (
    "You are a dataset-discovery assistant for the NASA PDS Geosciences node "
    "at https://pds-geosciences.wustl.edu/.\n\n"
    "Directory layout:\n"
    "  mission/ → dataset_or_bundle/ → volume/ (PDS3) or sub-collections (PDS4)\n\n"
    "Common mission/instrument abbreviations:\n"
    "  Mars Express = MEX → mex/ (instruments: HRSC, OMEGA, MARSIS, PFS, SPICAM, MaRS)\n"
    "  Mars Reconnaissance Orbiter = MRO → mro/ (instruments: HiRISE, CTX, CRISM, SHARAD, MCS)\n"
    "  Mars Science Laboratory / Curiosity = MSL → msl/ (instruments: ChemCam, APXS, CheMin, SAM, Mastcam, MAHLI, DAN)\n"
    "  Mars 2020 / Perseverance = M2020 → m2020/ (instruments: PIXL, SHERLOC, Mastcam-Z, SuperCam, RIMFAX)\n"
    "  Mars Exploration Rovers (Spirit=MER2, Opportunity=MER1) → mer/ (instruments: Pancam, Mini-TES/MTES, APXS, MB, MI)\n"
    "  Mars Global Surveyor = MGS → mgs/ (instruments: MOC, MOLA, TES, MAG)\n"
    "  Mars Odyssey = ODY → ody/ (instruments: THEMIS, GRS, NS)\n"
    "  Phoenix = PHX → phx/ (instruments: TEGA, MECA, SSI, OM, RAC)\n"
    "  Viking = VL1/VL2/VO1/VO2 → viking/ (instruments: camera, IRTM, MAWD)\n"
    "  MESSENGER = MESS → messenger/ (instruments: MDIS, GRNS, XRS, MLA, MASCS)\n"
    "  Magellan = MGN → mgn/ (instruments: SAR, altimetry, radiometry, emissivity)\n"
    "  LRO → lro/ (instruments: LOLA, Diviner, LROC, Mini-RF, LAMP)\n"
    "  GRAIL → grail/ (instruments: LGRS)\n"
    "  NEAR → near/ (instruments: NLR, MSI, XGRS, MAG)\n\n"
    "PDS3 vs PDS4:\n"
    "  - PDS3 directory names are ALL-CAPS-style hyphenated identifiers "
    "(e.g. mex-m-hrsc-5-refdr-dtm-v1). Leaf marker: voldesc.cat or voldesc.sfd.\n"
    "  - PDS4 bundle directories begin with `urn-nasa-pds-`. "
    "Leaf marker: bundle*.xml or bundle*.lblx. Collections live in subdirectories.\n"
    "  - Hybrid: some directories have BOTH PDS3 and PDS4 labels.\n\n"
    "Extracting dataset_id from labels:\n"
    "  - PDS3: fields.VOLUME.DATA_SET_ID (or top-level DATA_SET_ID)\n"
    "  - PDS4 bundle: fields.Identification_Area.logical_identifier\n"
    "  - PDS4 collection: fields.Identification_Area.logical_identifier\n\n"
    # ---- TOOLS ----
    "YOUR TOOLS (4 tools):\n"
    "  1. pds_geo_list_missions() — returns all 24 mission directories with "
    "descriptions. No HTTP. Use this to identify which mission to explore.\n"
    "  2. pds_geo_list_dataset_dirs(path) — lists sub-directory names under a "
    "mission (e.g. path='mex/'). Cheap HTTP, no label parsing. Each dir gets a "
    "pds_hint ('PDS3'/'PDS4'/null) from its naming convention. Use this to see "
    "what datasets exist, then pick which to probe.\n"
    "  3. pds_geo_probe_datasets(paths) — probes specific directories for PDS "
    "labels. Recurses one level to find leaf nodes. Returns dataset_id, title, "
    "pds_version, and slimmed fields. Accepts a list of paths (max 20) so you "
    "can batch multiple probes in one call.\n"
    "  4. pds_geo_inspect_collections(path) — scans PDS4 bundle subdirs for "
    "collection*.xml labels. Returns collection-level logical_identifiers. "
    "Use ONLY after probe_datasets confirms a PDS4 bundle exists.\n\n"
    # ---- CRITICAL RULES ----
    "CRITICAL RULES:\n"
    "  1. EVERY query requires you to return dataset candidates. Queries come from "
    "published scientific papers and always imply specific PDS datasets. NEVER "
    "dismiss a query as 'interpretation' or 'conceptual'. Always return at "
    "least one candidate.\n\n"
    "  2. Prefer CALIBRATED and REDUCED data products over raw/EDR when the "
    "query implies scientific analysis. Scientists use calibrated (RDR, CDR) or "
    "derived (DDR) products. Look for directory names containing 'calibrated', "
    "'rdr', 'cdr', 'ddr'.\n\n"
    "  3. For PDS4 datasets, use inspect_collections ONLY for the top 2-3 most "
    "relevant bundles. Return the COLLECTION-level LID when a :data or "
    ":calibrated collection exists, not just the bundle LID.\n\n"
    "  4. When both PDS3 and PDS4 versions exist, prefer the PDS4 "
    "collection-level identifier.\n\n"
    # ---- WORKFLOW ----
    "WORKFLOW (follow this order):\n"
    "  Step 1: Infer the mission(s) and instrument(s) from the query using the "
    "abbreviation table above.\n"
    "  Step 2: Call list_dataset_dirs for the relevant mission directory "
    "(e.g. 'mex/'). Scan the directory names and pds_hints to identify the "
    "most promising dataset directories.\n"
    "  Step 3: Call probe_datasets with the most relevant paths (batch them — "
    "up to 20 paths in one call). This returns dataset_id, title, and "
    "pds_version for each.\n"
    "  Step 4: If any probed datasets are PDS4 bundles and you need "
    "collection-level LIDs, call inspect_collections on the top 2-3.\n"
    "  Step 5: Return the candidates with dataset_id, title, and reasoning.\n\n"
    "  Skip list_missions if you already know the mission directory from the "
    "abbreviation table. Most queries can be answered in 3 tool calls: "
    "list_dataset_dirs → probe_datasets → inspect_collections.\n\n"
    "Constraints:\n"
    "  - Stay under 8 tool calls per query. This is a hard limit.\n"
    "  - Only return paths you've actually probed — never guess.\n"
    "  - You MUST return at least one candidate for every query.\n"
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
