"""Central registry of PDS discipline node configurations.

Each node entry contains the base URL, data root, mission list, and
prompt snippets needed by the tools and agent. Adding a new node is a
single dict entry in ``NODE_REGISTRY``.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class NodeConfig:
    """Static configuration for one PDS discipline node."""

    node_id: str
    base_url: str
    display_name: str
    data_root: str  # relative path to the data listing root ("" for GEO, "data/" for PPI/LROC)
    has_mission_layer: bool  # True → missions sit between data_root and datasets
    missions: tuple[dict[str, str], ...] = field(default_factory=tuple)
    description: str = ""
    workflow_notes: str = ""
    abbreviations: str = ""


# ---------------------------------------------------------------------------
# GEO — Geosciences
# ---------------------------------------------------------------------------

_GEO_MISSIONS: tuple[dict[str, str], ...] = (
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
)

_GEO_ABBREVIATIONS = (
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
    "  NEAR → near/ (instruments: NLR, MSI, XGRS, MAG)\n"
    "  InSight → insight/ (instruments: SEIS, HP3, RISE, IDA)\n"
)

_GEO_WORKFLOW = (
    "Directory layout: mission/ → dataset_or_bundle/ → volume/ (PDS3) or sub-collections (PDS4)\n"
    "This node has a mission layer. Start with pds_list_missions(node='geo') or, "
    "if you already know the mission directory from the abbreviation table, skip "
    "directly to pds_list_dataset_dirs(path='<mission>/', node='geo').\n"
    "Most queries can be answered in 3 tool calls: list_dataset_dirs → probe_datasets → inspect_collections.\n"
)

# ---------------------------------------------------------------------------
# PPI — Planetary Plasma Interactions
# ---------------------------------------------------------------------------

_PPI_MISSIONS: tuple[dict[str, str], ...] = (
    # Major missions — use the 'name' as the filter keyword for pds_list_dataset_dirs
    {"name": "cassini", "description": "Cassini at Saturn (CAPS, MAG, MIMI-CHEMS/INCA/LEMMS, RPWS, INMS). Also filter 'CO' for PDS3 IDs."},
    {"name": "galileo", "description": "Galileo at Jupiter + flybys of Earth/Venus/asteroids (EPD, MAG, PLS, PWS, PPR, HIC, SSD, RSS). Also filter 'GO' for PDS3 IDs."},
    {"name": "juno", "description": "Juno at Jupiter (Waves, JADE/JAD, JEDI/JED, FGM, ASC). Also filter 'JNO' for PDS3 IDs."},
    {"name": "VG1", "description": "Voyager 1 at Jupiter, Saturn, and interplanetary (CRS, LECP, MAG, PLS, PWS, PRA, RSS). Also filter 'vg1' for PDS4."},
    {"name": "VG2", "description": "Voyager 2 at Jupiter, Saturn, Uranus, Neptune, and interplanetary (CRS, LECP, MAG, PLS, PWS, PRA, RSS). Also filter 'vg2' for PDS4."},
    {"name": "MESS", "description": "MESSENGER at Mercury (EPPS incl. FIPS & EPS, MAG). Also filter 'messenger' for PDS4 bundle. Target: Mercury."},
    {"name": "MEX", "description": "Mars Express (ASPERA-3 incl. ELS/IMA/NPI, MARSIS). Target: Mars."},
    {"name": "maven", "description": "MAVEN at Mars (MAG, LPW, SEP, STATIC, SWEA, SWIA, EUV, ROSE). Target: Mars."},
    {"name": "P10", "description": "Pioneer 10 at Jupiter (CPI, CRT, GTT, HVM, PA, TRD, UV). Also filter 'p10' for PDS4."},
    {"name": "P11", "description": "Pioneer 11 at Jupiter and Saturn (CPI, CRT, FGM, GTT, HVM, PA, TRD, UV). Also filter 'p11' for PDS4."},
    {"name": "ULY", "description": "Ulysses at Jupiter and interplanetary (COSPIN, EPAC, HISCALE, SWOOPS, VHM-FGM, URAP, GAS, GRB, SCE, SWICS). Also filter 'ulysses' for PDS4."},
    {"name": "NH", "description": "New Horizons at Jupiter and Pluto (PEPSSI, SWAP). Target: Jupiter, Pluto."},
    {"name": "PVO", "description": "Pioneer Venus Orbiter (OEFD, OETP, OIMS, OMAG, ONMS, ORPA, ORSE). Also filter 'pvo' for PDS4. Target: Venus."},
    {"name": "LP", "description": "Lunar Prospector (MAG, ER — electron reflectometer). Also filter 'lp' for PDS4. Target: Moon."},
    {"name": "MGS", "description": "Mars Global Surveyor (MAG/ER, RSS). Also filter 'mgs' for PDS4. Target: Mars."},
    {"name": "NEAR", "description": "NEAR Shoemaker (MAG). Target: Eros, Earth flyby."},
    {"name": "M10", "description": "Mariner 10 (MAG, PLS). Target: Mercury."},
    {"name": "LRO", "description": "Lunar Reconnaissance Orbiter (CRaTER). Also filter 'lro' for PDS4. Target: Moon."},
    {"name": "ODY", "description": "Mars Odyssey (MARIE — radiation). Target: Mars."},
    {"name": "MSL", "description": "Mars Science Laboratory / Curiosity (RAD — radiation). Target: Mars."},
    {"name": "insight", "description": "InSight (IFG — fluxgate magnetometer). Target: Mars."},
    {"name": "vex", "description": "Venus Express (ASPERA-4 ELS, MAG). Target: Venus."},
    {"name": "ICE", "description": "International Cometary Explorer (EPAS, MAG, PLAWAV, RADWAV, SWPLAS). Target: Giacobini-Zinner."},
    {"name": "GIO", "description": "Giotto (IMS incl. HERS/HIS, JPA, MAG). Target: Halley."},
    {"name": "VEGA", "description": "Vega 1 & 2 (MISCHA, PM1, TNM). Target: Halley."},
    {"name": "DS1", "description": "Deep Space 1 (PEPE). Target: Borrelly."},
    {"name": "radiojove", "description": "Radio JOVE ground-based radio observations of Jupiter."},
)

_PPI_ABBREVIATIONS = (
    "Dataset naming conventions:\n"
    "  PDS3 dirs use uppercase mission codes: MESS-, CO-, GO-, JNO-, VG1-, VG2-, MEX-, P10-, P11-, ULY-, NH-, PVO-, etc.\n"
    "  PDS4 dirs use lowercase names: cassini-, galileo-, juno-, maven-, messenger-, ulysses-, etc.\n"
    "  Both conventions exist for many missions. Use pds_list_missions to see all available missions and filter keywords.\n"
)

_PPI_WORKFLOW = (
    "All ~781 datasets sit directly under data/ with no mission sub-directories.\n"
    "The mission 'name' from pds_list_missions is the filter keyword to use with list_dataset_dirs.\n"
)

# ---------------------------------------------------------------------------
# LROC — Lunar Reconnaissance Orbiter Camera
# ---------------------------------------------------------------------------

_LROC_ABBREVIATIONS = (
    "LROC datasets (3 total — each carries BOTH a PDS3 voldesc and a PDS4 bundle label):\n"
    "  LRO-L-LROC-2-EDR-V1.0   (PDS4 LID: urn:nasa:pds:lro-l-lroc-2-edr) — Experiment Data Records (raw images)\n"
    "  LRO-L-LROC-3-CDR-V1.0   (PDS4 LID: urn:nasa:pds:lro-l-lroc-3-cdr) — Calibrated Data Records\n"
    "  LRO-L-LROC-5-RDR-V1.0   (PDS4 LID: urn:nasa:pds:lro-l-lroc-5-rdr) — Reduced Data Records (derived products)\n"
    "\n"
    "Instruments: NAC (Narrow Angle Camera), WAC (Wide Angle Camera).\n"
    "Sub-volumes are numbered directories (e.g. LROLRC_0001/, LROLRC_0002/) inside each dataset.\n"
    "The PDS3 dataset_id and the PDS4 bundle LID address the same underlying data — they are equivalent.\n"
)

_LROC_WORKFLOW = (
    "This node has NO mission layer. Only 3 fixed dataset paths sit under data/.\n"
    "Do NOT call pds_list_missions — it will return an empty list.\n"
    "Go directly to pds_list_dataset_dirs(path='data/', node='lroc') to see all 3 datasets.\n"
    "Then probe the relevant ones with pds_probe_datasets.\n"
    "For PDS4 bundles, use inspect_collections to get collection-level LIDs.\n"
)

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

NODE_REGISTRY: dict[str, NodeConfig] = {
    "geo": NodeConfig(
        node_id="geo",
        base_url="https://pds-geosciences.wustl.edu/",
        display_name="Geosciences (GEO)",
        data_root="",
        has_mission_layer=True,
        missions=_GEO_MISSIONS,
        description="Geoscience data: Mars, Venus, Mercury, Moon surface/subsurface measurements, "
        "topography, gravity, geochemistry, imaging, spectroscopy",
        workflow_notes=_GEO_WORKFLOW,
        abbreviations=_GEO_ABBREVIATIONS,
    ),
    "ppi": NodeConfig(
        node_id="ppi",
        base_url="https://pds-ppi.igpp.ucla.edu/",
        display_name="Planetary Plasma Interactions (PPI)",
        data_root="data/",
        has_mission_layer=False,
        missions=_PPI_MISSIONS,
        description="Plasma, particle, and fields data: magnetospheres, solar wind, "
        "ionospheres, radio/plasma waves, energetic particles",
        workflow_notes=_PPI_WORKFLOW,
        abbreviations=_PPI_ABBREVIATIONS,
    ),
    "lroc": NodeConfig(
        node_id="lroc",
        base_url="https://pds.lroc.im-ldi.com/",
        display_name="Lunar Reconnaissance Orbiter Camera (LROC)",
        data_root="data/",
        has_mission_layer=False,
        missions=(),
        description="LROC imaging: NAC and WAC lunar surface images, EDR/CDR/RDR products",
        workflow_notes=_LROC_WORKFLOW,
        abbreviations=_LROC_ABBREVIATIONS,
    ),
}

SUPPORTED_NODES = tuple(NODE_REGISTRY.keys())


def get_node_config(node_id: str) -> NodeConfig:
    """Look up a node by ID. Raises ValueError if unknown."""
    config = NODE_REGISTRY.get(node_id.lower())
    if config is None:
        raise ValueError(
            f"Unknown PDS node: {node_id!r}. "
            f"Supported nodes: {', '.join(SUPPORTED_NODES)}"
        )
    return config


def get_base_url(node_id: str) -> str:
    """Shortcut: get the base URL for a node."""
    return get_node_config(node_id).base_url


def list_available_nodes() -> list[dict[str, str]]:
    """Return a summary of all registered nodes (for the select_node tool)."""
    return [
        {
            "node_id": cfg.node_id,
            "display_name": cfg.display_name,
            "description": cfg.description,
        }
        for cfg in NODE_REGISTRY.values()
    ]
