"""List known top-level mission directories on the GEO node.

Hardcoded — no HTTP required. The GEO node directory structure is stable
and changes very rarely (new missions are added on the order of years).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


_GEO_MISSIONS: list[dict[str, str]] = [
    {"name": "m2020", "description": "Mars 2020 / Perseverance (PIXL, SHERLOC, Mastcam-Z, SuperCam, RIMFAX)"},
    {"name": "insight", "description": "InSight lander (SEIS, HP3, RISE, IDA)"},
    {"name": "msl", "description": "Mars Science Laboratory / Curiosity (ChemCam, APXS, CheMin, SAM, Mastcam, MAHLI, DAN)"},
    {"name": "mro", "description": "Mars Reconnaissance Orbiter (HiRISE, CTX, CRISM, SHARAD, MCS)"},
    {"name": "mer", "description": "Mars Exploration Rovers — Spirit (MER2) and Opportunity (MER1) (Pancam, Mini-TES, APXS, MB, MI)"},
    {"name": "mex", "description": "Mars Express (HRSC, OMEGA, MARSIS, PFS, SPICAM, MaRS)"},
    {"name": "ody", "description": "Mars Odyssey (THEMIS, GRS, NS)"},
    {"name": "phx", "description": "Phoenix lander (TEGA, MECA, SSI, OM, RAC)"},
    {"name": "mgs", "description": "Mars Global Surveyor (MOC, MOLA, TES, MAG)"},
    {"name": "mpf", "description": "Mars Pathfinder (IMP, APXS)"},
    {"name": "viking", "description": "Viking (VL1, VL2, VO1, VO2 — camera, IRTM, MAWD)"},
    {"name": "mariner", "description": "Mariner missions"},
    {"name": "mars", "description": "Mars miscellaneous / Mars Express ancillary"},
    {"name": "mgn", "description": "Magellan (SAR, altimetry, radiometry, emissivity)"},
    {"name": "premgn", "description": "Pre-Magellan Venus data (Pioneer Venus Orbiter)"},
    {"name": "venus", "description": "Venus miscellaneous"},
    {"name": "messenger", "description": "MESSENGER at Mercury (MDIS, GRNS, XRS, MLA, MASCS)"},
    {"name": "grail", "description": "GRAIL lunar gravity (LGRS)"},
    {"name": "clps", "description": "Commercial Lunar Payload Services"},
    {"name": "lunar", "description": "Lunar missions (Clementine, Lunar Prospector, Chandrayaan, Kaguya, Apollo)"},
    {"name": "lro", "description": "Lunar Reconnaissance Orbiter (LOLA, Diviner, LROC, Mini-RF, LAMP)"},
    {"name": "earth", "description": "Earth-based observations"},
    {"name": "lab", "description": "Laboratory measurements"},
    {"name": "near", "description": "NEAR Shoemaker at Eros (NLR, MSI, XGRS, MAG)"},
]


class PDSGeoMission(BaseModel):
    """One mission directory on the GEO node."""

    name: str = Field(description="Top-level directory name on pds-geosciences.wustl.edu")
    description: str = Field(description="Mission name, spacecraft, and key instruments")


class PDSGeoListMissionsOutput(BaseModel):
    """Output for pds_geo_list_missions."""

    missions: list[PDSGeoMission] = Field(description="All known mission directories on the GEO node")
    count: int = Field(description="Number of missions")


def pds_geo_list_missions() -> PDSGeoListMissionsOutput:
    """Return the hardcoded list of GEO node mission directories.

    No HTTP call needed — the GEO node structure is stable.
    """
    missions = [PDSGeoMission(**m) for m in _GEO_MISSIONS]
    return PDSGeoListMissionsOutput(missions=missions, count=len(missions))
