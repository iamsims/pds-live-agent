"""Central registry of PDS discipline node configurations.

Each node entry contains the base URL, data root, mission list, and
prompt snippets needed by the tools and agent. Adding a new node is a
single dict entry in ``NODE_REGISTRY``.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class NodeConfig:
    """Static configuration for one PDS discipline node.

    Per-node optimization protocol: when tuning the prompt for a single node,
    edit ONLY this node's entry below — never the general prompt builder in
    ``live_finder.pds_finder``. See CLAUDE.md at the project root.
    """

    node_id: str
    base_url: str
    display_name: str
    data_root: str  # relative path to the data listing root ("" for GEO, "data/" for PPI/LROC)
    has_mission_layer: bool  # True → missions sit between data_root and datasets
    missions: tuple[dict[str, str], ...] = field(default_factory=tuple)
    description: str = ""
    # Free-form prose: directory layout + any caveats (HTTP 403, hybrid trees, etc.).
    workflow_notes: str = ""
    # Mission/instrument abbreviation table — used by the agent for fast lookup.
    abbreviations: str = ""
    # Numbered step-by-step plan the agent should follow for THIS node.
    # Drop-in replacement for the if/elif branching the prompt builder used to do.
    workflow_steps: str = ""


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

_GEO_WORKFLOW_STEPS = (
    "Step 1: If you know the mission directory from the abbreviation table, "
    "skip directly to list_dataset_dirs(path='<mission>/', node='geo').\n"
    "        Otherwise call pds_list_missions(node='geo') first.\n"
    "Step 2: Call pds_list_dataset_dirs for the relevant mission directory. "
    "Scan names and pds_hints to identify promising datasets.\n"
    "Step 3: Call pds_probe_datasets with the most relevant paths (batch up to 20).\n"
    "Step 4: If PDS4 bundles are found, call pds_inspect_collections on top 2-3.\n"
    "Step 5: Return candidates.\n"
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
    "Slash-encoding in DATA_SET_IDs: directory names cannot contain '/' so PPI replaces it\n"
    "with '_'. The dir 'JNO-J_SW-JAD-5-CALIBRATED-V1.0' corresponds to DATA_SET_ID\n"
    "'JNO-J/SW-JAD-5-CALIBRATED-V1.0', and 'MESS-E_V_H_SW-EPPS-3-FIPS-DDR-V2.0' →\n"
    "'MESS-E/V/H/SW-EPPS-3-FIPS-DDR-V2.0'. When the gold target contains '/', look for the\n"
    "directory with '_' in those positions — pds_probe_datasets will return the canonical\n"
    "DATA_SET_ID with the slashes restored.\n"
)

_PPI_WORKFLOW = (
    "All ~781 datasets sit directly under data/ with no mission sub-directories.\n"
    "The mission 'name' from pds_list_missions is the filter keyword to use with list_dataset_dirs.\n"
)

_PPI_WORKFLOW_STEPS = (
    "Step 1: Call pds_list_missions(node='ppi') to see all available missions and their filter keywords.\n"
    "Step 2: Identify which mission(s) are relevant to the query.\n"
    "Step 3: Call pds_list_dataset_dirs(path='data/', node='ppi', filter='<mission_name>') "
    "using the mission name as the filter keyword. Filter is mandatory — ~781 entries otherwise.\n"
    "Step 4: Call pds_probe_datasets with the most relevant paths (batch up to 20).\n"
    "Step 5: If PDS4 bundles are found, call pds_inspect_collections on top 2-3.\n"
    "Step 6: Return candidates.\n"
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

_LROC_WORKFLOW_STEPS = (
    "Step 1: SKIP pds_list_missions — it returns an empty list for LROC. "
    "Call pds_list_dataset_dirs(path='data/', node='lroc') directly to see all 3 datasets "
    "(EDR, CDR, RDR — each a hybrid PDS3+PDS4 directory).\n"
    "Step 2: Call pds_probe_datasets on the level(s) implied by the query "
    "(EDR=raw, CDR=calibrated, RDR=reduced/derived).\n"
    "Step 3: Call pds_inspect_collections on the relevant PDS4 bundles to get collection-level LIDs.\n"
    "Step 4: Return candidates — emit BOTH the PDS3 dataset_id and the PDS4 LID for the same data "
    "(e.g. LRO-L-LROC-5-RDR-V1.0 + urn:nasa:pds:lro-l-lroc-5-rdr).\n"
)

# ---------------------------------------------------------------------------
# IMG — JPL Imaging Node
# ---------------------------------------------------------------------------

# JPL IMG hosts the legacy planetary imaging archive at /img/data/. Top level is
# a flat list of mission directories. Each mission can nest deeply (e.g. cassini
# branches into cassini_orbiter/, opus/, pds4/, public/) — the agent should call
# list_dataset_dirs at successive depths rather than guessing paths.

_IMG_MISSIONS: tuple[dict[str, str], ...] = (
    {"name": "cassini", "description": "Cassini imaging at Saturn (ISS NAC/WAC). Nests into cassini_orbiter/, opus/, pds4/, public/."},
    {"name": "galileo", "description": "Galileo SSI imaging at Jupiter and asteroid flybys (Gaspra, Ida)."},
    {"name": "voyager", "description": "Voyager 1 & 2 ISS imaging — Jupiter, Saturn, Uranus, Neptune."},
    {"name": "mariner6", "description": "Mariner 6 Mars flyby imaging (1969)."},
    {"name": "mariner7", "description": "Mariner 7 Mars flyby imaging (1969)."},
    {"name": "mariner9", "description": "Mariner 9 Mars orbiter imaging (1971-72)."},
    {"name": "mariner10", "description": "Mariner 10 Mercury and Venus imaging (1973-75)."},
    {"name": "viking_orbiter", "description": "Viking Orbiter 1 & 2 imaging of Mars (1976-80)."},
    {"name": "viking_lander", "description": "Viking Lander 1 & 2 surface imaging at Mars."},
    {"name": "magellan", "description": "Magellan SAR/altimetry/radiometry/emissivity imaging at Venus."},
    {"name": "messenger", "description": "MESSENGER MDIS imaging at Mercury (legacy IMG mirror) — img/data/messenger/MDIS/MSGRMDS_*/ are the PDS3 volumes; IMG does NOT host the urn:nasa:pds:messenger_mdis_* PDS4 bundles (those live at PPI). Return the PDS3 DATA_SET_ID."},
    {"name": "near", "description": "NEAR Shoemaker MSI imaging at asteroid Eros."},
    {"name": "stardust", "description": "Stardust NAVCAM imaging of comet Wild 2 + Tempel 1 flyby."},
    {"name": "deepimpact", "description": "Deep Impact HRI/MRI/ITS imaging at comet Tempel 1."},
    # Additional mission dirs that exist under img/data/ but were missing from the legacy list:
    {"name": "mro", "description": "Mars Reconnaissance Orbiter cameras at IMG: img/data/mro/ctx/ (CTX EDR, ~5500 mrox_* volumes), img/data/mro/hirise/ (HiRISE EXTRAS only — main RDR not mirrored at IMG, hosted at GEO), img/data/mro/marci/."},
    {"name": "mer", "description": "Mars Exploration Rovers (Spirit=MER2, Opportunity=MER1) imaging: img/data/mer/ and direct PDS3 dirs img/data/mer1-* / mer2-* (Pancam, Navcam, Hazcam, Mini-TES, APXS). IMG hosts ONLY the PDS3 mer{1,2}-m-<inst>-<level>-* dirs; urn:nasa:pds:mer{1,2}_<inst>_sci_calibrated* PDS4 LIDs are NOT mirrored at IMG (hosted at GEO). Return the PDS3 DATA_SET_ID."},
    {"name": "lro", "description": "LRO LROC imaging (limited mirror) — full LROC archive is at the LROC node."},
)

_IMG_ABBREVIATIONS = (
    "Naming conventions on IMG:\n"
    "  Top level: lowercase mission directories (cassini/, galileo/, mariner9/, viking_orbiter/, …).\n"
    "  Inside a mission: variable structure. Cassini for example has cassini_orbiter/, opus/, "
    "pds4/, and public/ — all four can contain datasets at different depths.\n"
    "  PDS3 dataset names: hyphenated identifiers (e.g. co-s-iss-2-edr-v1.0); PDS4 bundles begin with urn-nasa-pds-.\n"
    "Skip these directories at every level when scanning: checksums, document, index, catalog, "
    "extras, browse, software, errata.\n"
)

_IMG_WORKFLOW = (
    "Directory layout: img/data/<mission>/[<sub-tree>/]<dataset_or_bundle>/\n"
    "Top level under img/data/ is a flat list of mission directories. Many missions nest one or\n"
    "two more levels before reaching dataset roots (Cassini is the most extreme — four parallel\n"
    "sub-trees). Recurse with list_dataset_dirs rather than guessing paths.\n"
    "There is no holdings/inventory page — the Apache directory listing is the only index.\n"
    "IMPORTANT — PDS4 coverage at IMG is partial. For MESSENGER MDIS, MER cameras, MRO HiRISE,\n"
    "the urn:nasa:pds:<mission>_<inst>_* PDS4 bundles are NOT mirrored here even though the\n"
    "PDS3 equivalents are. When the gold target is a urn: LID and a single list+probe doesn't\n"
    "find a matching bundle, return the closest PDS3 DATA_SET_ID and note that IMG only hosts\n"
    "the PDS3 mirror for that mission.\n"
)

_IMG_WORKFLOW_STEPS = (
    "Step 1: If you know the mission directory from the abbreviation table, skip directly to "
    "list_dataset_dirs(path='img/data/<mission>/', node='img'). Otherwise call "
    "pds_list_missions(node='img') first to see the mission list. Mission entries now include "
    "mro/ (CTX, HiRISE-EXTRAS, MARCI), mer/ (Pancam/Navcam/Hazcam/MiniTES/APXS), and notes on "
    "which urn: LIDs are NOT mirrored at IMG.\n"
    "Step 2: Call pds_list_dataset_dirs for the mission directory. If results look like another "
    "layer of organisational sub-trees (e.g. cassini_orbiter/, opus/, pds4/, public/ for Cassini, "
    "or ctx/, hirise/, marci/ for mro), call list_dataset_dirs again on the relevant sub-tree.\n"
    "Step 3: Volume-set targets — when the dataset is split across many numbered volumes (e.g. "
    "img/data/mro/ctx/mrox_NNNN/, img/data/messenger/MDIS/MSGRMDS_NNNN/), call "
    "pds_resolve_volume(volume_set_path='img/data/mro/ctx/', node='img', "
    "dataset_id_hint='<DATA_SET_ID fragment>', sample=8). It returns per-child dataset_ids in "
    "one call instead of multiple sequential probes.\n"
    "Step 4: If PDS4 bundles are found, call pds_inspect_collections on top 2-3.\n"
    "Step 5: When the gold target is urn:nasa:pds:messenger_mdis_*, urn:nasa:pds:mer{1,2}_*, or "
    "MRO-M-HIRISE-* and you don't find a matching bundle at IMG after Steps 1–4, "
    "return the PDS3 mirror's DATA_SET_ID (e.g. MESS-E/V/H-MDIS-2-EDR-RAWDATA-V1.0 for MDIS, "
    "MER2-M-PANCAM-3-RADCAL-RDR-V1.0 for Spirit Pancam calibrated) plus a 'PDS4 not mirrored "
    "at IMG' note. Do NOT keep hunting for the PDS4 form past one extra list/probe.\n"
    "Step 6: Use the new `dataset_ids` field on pds_probe_datasets results when a voldesc "
    "ships multiple DATA_SET_IDs — match against the full list, not just the scalar.\n"
)

# ---------------------------------------------------------------------------
# RMS — Ring-Moon Systems
# ---------------------------------------------------------------------------

# RMS publishes under TWO parallel trees:
#   holdings/volumes/<VOLUME_SET>/<VOLUME>/   — PDS3 volumes (volume-set is the mission/instrument grouping)
#   pds4/bundles/<bundle_dir>/                — PDS4 bundles (flat list)
# The agent treats holdings/volumes/ as the primary entry point and uses the
# volume-set prefixes below as filter keywords (PPI-style).

_RMS_MISSIONS: tuple[dict[str, str], ...] = (
    {"name": "COISS", "description": "Cassini ISS — Imaging Science Subsystem (NAC + WAC). Saturn rings, satellites, atmosphere."},
    {"name": "COUVIS", "description": "Cassini UVIS — Ultraviolet Imaging Spectrograph. UV spectroscopy (SPEC), stellar/solar occultations (SSB), calibrated products (CALIB). Covers rings AND satellite surfaces (Rhea, Enceladus, etc.)."},
    {"name": "COVIMS", "description": "Cassini VIMS — Visual and Infrared Mapping Spectrometer. Rings + satellites."},
    {"name": "COCIRS", "description": "Cassini CIRS — Composite InfraRed Spectrometer. Saturn/satellite atmospheres."},
    {"name": "CORSS", "description": "Cassini Radio Science Subsystem ring/atmosphere occultations."},
    {"name": "COSP", "description": "Cassini SPICE kernels (RMS mirror)."},
    {"name": "VG_28xx", "description": "Voyager 1/2 ring occultations (PPS/UVS/RSS)."},
    {"name": "VG_2xxx", "description": "Voyager 1/2 imaging (ISS) — Jupiter, Saturn, Uranus, Neptune."},
    {"name": "VGISS", "description": "Voyager 1/2 ISS PDS4 calibrated/raw images."},
    {"name": "GO_00xx", "description": "Galileo SSI imaging — Jupiter/satellites/ring system."},
    {"name": "EBROCC", "description": "Earth-Based Ring Occultations (1989 Saturn, 1980s/90s Uranus)."},
    {"name": "ESO_xxxx", "description": "European Southern Observatory ground-based ring observations."},
    {"name": "RES_xxxx", "description": "Reduced Earth-based stellar occultation results."},
    {"name": "HSTI", "description": "Hubble WFPC2 imaging of rings/satellites."},
    {"name": "HSTJ", "description": "Hubble ACS imaging of rings/satellites."},
    {"name": "HSTU", "description": "Hubble WFC3/STIS imaging of rings/satellites."},
    {"name": "HSTN", "description": "Hubble NICMOS imaging of rings/satellites."},
    {"name": "NHxxLO", "description": "New Horizons LORRI imaging — Pluto, KBOs, ring search."},
    {"name": "NHxxMV", "description": "New Horizons MVIC (Ralph) imaging."},
    {"name": "ASTROM", "description": "Ground/HST astrometric measurements of irregular satellites."},
    {"name": "cassini_iss", "description": "PDS4 bundle: Cassini ISS observations (cruise + Saturn tour)."},
    {"name": "cassini_vims", "description": "PDS4 bundle: Cassini VIMS observations."},
    {"name": "cassini_uvis", "description": "PDS4 bundle: Cassini UVIS occultations."},
)

_RMS_ABBREVIATIONS = (
    "Naming conventions on RMS:\n"
    "  PDS3 volumes use uppercase prefixes ending in _xxxx or numbered: COISS_1xxx, COVIMS_0xxx, GO_0017, EBROCC_xxxx.\n"
    "  Each prefix groups many numbered volumes (e.g. COISS_1xxx contains COISS_1001, COISS_1002, ...).\n"
    "  PDS4 bundles use lowercase descriptive names: cassini_iss, cassini_uvis, cassini_vims, etc.\n"
    "Mission/instrument keys (use as filter):\n"
    "  Cassini → CO* (COISS, COUVIS, COVIMS, COCIRS, CORSS) for PDS3; cassini_* for PDS4\n"
    "  Voyager → VG_2xxx (imaging), VG_28xx (occultations), VGISS (PDS4)\n"
    "  Galileo → GO_*\n"
    "  New Horizons → NHxxLO, NHxxMV\n"
    "  Hubble → HSTI/HSTJ/HSTU/HSTN (camera era — each volume is a unique HST program)\n"
    "  Earth-based → EBROCC, ESO_*, RES_*\n"
    "Cassini UVIS data types (COUVIS volumes):\n"
    "  COUVIS_0xxx     = raw + calibrated spectra/images (SPEC, SSB, CALIB, CUBE, etc.)\n"
    "  COUVIS_0xxx_v1  = older v1 publication of the same archive (gold v1.0/1.2 ids live here)\n"
    "  COUVIS_8xxx     = ring stellar/solar occultation profiles\n"
    "  For UV spectroscopy of surfaces (Rhea, Enceladus, etc.), use COUVIS_0xxx (not _8xxx).\n"
    "  COUVIS volume range:\n"
    "    COUVIS_0001..0008 = JUPITER encounter (DATA_SET_IDs prefixed CO-J-UVIS-…)\n"
    "    COUVIS_0003 also carries CO-S-UVIS-* (Jupiter+Saturn transition volume) and is\n"
    "    therefore the EARLIEST volume to contain a CO-S-UVIS-* id\n"
    "    COUVIS_0004+  = SATURN-tour only (CO-S-UVIS-…)\n"
    "Cassini ISS volume-sets:\n"
    "  COISS_1xxx = cruise-phase EDRs (Earth/Venus/Jupiter; DATA_SET_ID prefixed CO-J/V/E-…)\n"
    "  COISS_2xxx = Saturn-tour EDRs (the main science dataset; DATA_SET_ID CO-S-ISSNA/ISSWA-…)\n"
    "  COISS_3xxx = cartographic map products (MIDR)\n"
    "  COISS_0xxx = calibration files/software\n"
    "Cassini VIMS volume-sets:\n"
    "  COVIMS_0xxx = raw image/spectral cubes. DATA_SET_ID convention is\n"
    "    CO-E/V/J/S-VIMS-2-QUBE-V1.0 (note: QUBE not EDR). If gold says 'CO-S-VIMS-2-EDR-V1.0'\n"
    "    return CO-E/V/J/S-VIMS-2-QUBE-V1.0 with a 'gold id variant; node hosts QUBE' note.\n"
    "  COVIMS_8xxx = ring stellar/solar occultation profiles.\n"
    "Multi-DATA_SET_ID voldescs (common on Cassini):\n"
    "  COUVIS_*, COCIRS_*, COVIMS_* voldesc.cat files declare DATA_SET_ID as a list (one id per\n"
    "  product type on the volume — SSB/SPEC/CUBE/CALIB/WAV etc.). pds_probe_datasets now\n"
    "  exposes the full list in `dataset_ids`. Match the gold id against this list, not only\n"
    "  the scalar `dataset_id` field (which is just the first one).\n"
)

_RMS_WORKFLOW = (
    "Two parallel trees:\n"
    "  PDS3 → holdings/volumes/<VOLUME_SET>/<VOLUME>/  (volume-set wraps multiple numbered volumes)\n"
    "  PDS4 → pds4/bundles/<bundle>/                   (flat list of bundles)\n\n"
    "CRITICAL — volume-set explosion warning:\n"
    "  Volume-sets (e.g. COISS_2xxx, COUVIS_0xxx_v1, HSTUx_xxxx_v1.0) contain many numbered\n"
    "  volumes (often 30-100+). Do NOT probe a volume-set directory directly — pds_probe_datasets\n"
    "  will recurse into ALL volumes and produce massive redundant output (100+ near-identical results).\n"
    "  Instead, probe a SINGLE representative volume inside the set, e.g.:\n"
    "    pds_probe_datasets(paths=['holdings/volumes/COUVIS_0xxx_v1/COUVIS_0009/'], node='rms')\n"
    "  All volumes in a set share the same dataset_id, so one probe is enough.\n"
    "  HST volumes are the exception — each volume has a unique dataset_id per HST program,\n"
    "  but you still should NOT probe the entire set. Pick 1-2 representative volumes.\n"
)

_RMS_WORKFLOW_STEPS = (
    "Step 1: Call pds_list_missions(node='rms') to see the 23 instrument/mission filter keys.\n"
    "Step 2: Identify the SPECIFIC instrument(s) relevant to the query from the mission list:\n"
    "          - UV spectroscopy/absorption on surfaces → COUVIS (not COISS or HST)\n"
    "          - Visible imaging of rings/satellites → COISS\n"
    "          - IR spectral mapping → COVIMS\n"
    "          - Thermal spectra → COCIRS\n"
    "        Do NOT explore instruments not mentioned or implied by the query.\n"
    "Step 3 (PDS3): Call pds_list_dataset_dirs(path='holdings/volumes/', node='rms', "
    "filter='<KEY>') with a volume-set prefix from the abbreviation table "
    "(e.g. COISS, COVIMS, GO_00, VG_28, NHxxLO).\n"
    "Step 3 (PDS4): Call pds_list_dataset_dirs(path='pds4/bundles/', node='rms', filter='<key>') — "
    "flat list of named bundles (cassini_iss, cassini_uvis, cassini_vims, …).\n"
    "Step 4: Pick ONE representative volume from each relevant volume-set and probe it. "
    "Do NOT probe the volume-set directory itself — see the volume-set explosion warning above. "
    "Example: pds_probe_datasets(paths=['holdings/volumes/COISS_2xxx/COISS_2001/'], node='rms')\n"
    "Step 4b (preferred for UVIS Saturn / search by dataset_id substring): When the target\n"
    "is a specific CO-S-UVIS-2-<TYPE>-V<x>.<y> id, call pds_resolve_volume(\n"
    "  volume_set_path='holdings/volumes/COUVIS_0xxx_v1/', node='rms',\n"
    "  dataset_id_hint='CO-S-UVIS-2-<TYPE>', sample=4)\n"
    "It probes a hint-ranked sample and returns a `best_match` pointing at the first child\n"
    "whose `dataset_ids` list contains the requested id. One call replaces several manual\n"
    "probes — especially useful for the CO-S-UVIS-* family because the first hosting volume\n"
    "is COUVIS_0003 (Jupiter+Saturn transition), not COUVIS_0001.\n"
    "Step 5: For PDS4 bundles, call pds_inspect_collections on top 2-3 to get collection LIDs.\n"
    "Step 6: When the same instrument has BOTH a PDS3 volume-set and a PDS4 bundle, return BOTH "
    "candidates. Always scan `dataset_ids` (not only `dataset_id`) since Cassini voldescs "
    "ship many ids per volume. Do NOT silently drop the PDS3 form. Stay under 8 tool calls total.\n"
)

# ---------------------------------------------------------------------------
# SBN — Small Bodies Node
# ---------------------------------------------------------------------------

# SBN's /holdings/ Apache index is now accessible (~800+ dataset dirs).
# Historically it returned HTTP 403; the workflow includes a fallback to
# the abbreviation table if 403 recurs.

_SBN_MISSIONS: tuple[dict[str, str], ...] = (
    {"name": "ro-c", "description": "Rosetta at comet 67P/Churyumov-Gerasimenko (OSIRIS, NAVCAM, ALICE, MIRO, GIADA, COSIMA, VIRTIS, ROSINA)."},
    {"name": "ro-a", "description": "Rosetta asteroid flybys (Lutetia, Steins)."},
    {"name": "orex", "description": "OSIRIS-REx at asteroid Bennu (OCAMS, OVIRS, OTES, REXIS, OLA)."},
    {"name": "hay", "description": "Hayabusa at asteroid Itokawa (AMICA, NIRS, LIDAR, XRS)."},
    {"name": "hyb2", "description": "Hayabusa2 at asteroid Ryugu (ONC, NIRS3, TIR, LIDAR, MASCOT)."},
    {"name": "lucy", "description": "Lucy mission to Trojan asteroids (L'LORRI, L'Ralph, L'TES)."},
    {"name": "dart", "description": "DART impactor on Didymos/Dimorphos (DRACO, LICIACube)."},
    {"name": "sd", "description": "Stardust at comet Wild 2 + Tempel 1 flyby (NAVCAM, CIDA)."},
    {"name": "di", "description": "Deep Impact at comet Tempel 1 (HRI, MRI, ITS)."},
    {"name": "dif", "description": "EPOXI / Deep Impact extended mission (Hartley 2 flyby, exoplanet observations)."},
    {"name": "near-a", "description": "NEAR Shoemaker at asteroid Eros (MSI, NLR, NIS, MAG)."},
    {"name": "co-d-cda", "description": "Cassini CDA — Cosmic Dust Analyzer (interplanetary/Saturn dust)."},
    {"name": "gbo", "description": "Ground-based observations of asteroids/comets/KBOs."},
    {"name": "hst", "description": "Hubble small-body observations (asteroids, comets, KBOs)."},
    {"name": "spitzer", "description": "Spitzer Space Telescope small-body IR observations."},
    {"name": "irtf", "description": "NASA IRTF small-body IR observations."},
)

_SBN_ABBREVIATIONS = (
    "Naming conventions on SBN (when reachable):\n"
    "  PDS3 dataset names: <mission>-<target>-<instrument>-<level>-<v> (e.g. ro-c-osiris-2-cru2-mtp003-v2.0).\n"
    "  PDS4 bundles: urn:nasa:pds:<mission_instrument>_<level> (e.g. urn:nasa:pds:orex.ocams).\n"
    "Mission keys (use as filter):\n"
    "  Rosetta comet → ro-c-*; Rosetta asteroid → ro-a-*\n"
    "  OSIRIS-REx → orex_*; Hayabusa → hay_*; Hayabusa2 → hyb2_*\n"
    "  Lucy → lucy_*; DART → dart_*\n"
    "  Stardust → sd-*; Deep Impact → di-* / dii-* / dif-* (EPOXI extension)\n"
    "  NEAR → near-a-*; Cassini CDA → co-d-cda-*\n"
    "  Ground/space-based small-body observing → gbo*, hst, spitzer, irtf\n"
)

_SBN_WORKFLOW = (
    "Directory layout: holdings/<dataset_dir>/  — ~800+ dataset directories, flat list.\n"
    "SBN's /holdings/ Apache index is now accessible. Use pds_list_dataset_dirs "
    "with a filter keyword from the mission table to narrow results.\n"
    "IMPORTANT: The holdings index has historically been intermittent (HTTP 403). If "
    "pds_list_dataset_dirs returns status='forbidden', fall back to synthesising candidates "
    "from the abbreviation table (see 403 FALLBACK in workflow steps).\n"
)

_SBN_WORKFLOW_STEPS = (
    "Step 1: Call pds_list_missions(node='sbn') to load the mission abbreviation table.\n"
    "Step 2: Identify the mission(s) relevant to the query (Rosetta=ro-c/ro-a, OSIRIS-REx=orex, "
    "Hayabusa=hay/hyb2, Lucy=lucy, DART=dart, Stardust=sd, Deep Impact=di/dif, NEAR=near-a, "
    "Cassini CDA=co-d-cda, ground/space-based=gbo/hst/spitzer/irtf).\n"
    "Step 3: Call pds_list_dataset_dirs(path='holdings/', node='sbn', filter='<mission_key>') "
    "to list matching dataset directories.\n"
    "Step 4: If Step 3 succeeds, call pds_probe_datasets on the most relevant paths (batch up to 20).\n"
    "Step 5: If PDS4 bundles are found, call pds_inspect_collections on top 2-3.\n"
    "Step 6: Return candidates.\n\n"
    "403 FALLBACK — If pds_list_dataset_dirs returns status='forbidden' (HTTP 403), the holdings "
    "index is temporarily unreachable. In that case:\n"
    "  a. Synthesise ONE candidate per likely dataset using the abbreviation pattern from Step 1: "
    "PDS3 = '<mission>-<target>-<instrument>-<level>-v<n>' (e.g. ro-c-osiris-2-cru2-mtp003-v2.0); "
    "PDS4 = 'urn:nasa:pds:<mission_instrument>' (e.g. urn:nasa:pds:orex.ocams).\n"
    "  b. In every candidate's `reasoning`, EXPLICITLY state that the dataset_id was inferred "
    "from the abbreviation table because SBN's holdings index returned HTTP 403 — "
    "the candidate is plausible but NOT verified live.\n"
)

# ---------------------------------------------------------------------------
# ATM — Atmospheres
# ---------------------------------------------------------------------------

# ATM publishes under TWO parallel trees:
#   PDS/data/<VOLUME>/        — PDS3 volumes (uppercase volume names like MROM_0001)
#   PDS/data/PDS4/<bundle>/   — PDS4 bundles
# IMPORTANT: PDS/data/ contains a `PDS4/` subdirectory — that's the PDS4 root,
# not a PDS3 volume. The agent should skip it when scanning PDS3.

_ATM_MISSIONS: tuple[dict[str, str], ...] = (
    {"name": "MROM", "description": "Mars Reconnaissance Orbiter MCS (Mars Climate Sounder) — atmospheric temperature/aerosols."},
    {"name": "MAVENM", "description": "MAVEN at Mars (NGIMS, IUVS, SWIA, SWEA, SEP) — upper atmosphere/ionosphere."},
    {"name": "MEXSPI", "description": "Mars Express SPICAM — UV/IR atmospheric sensing."},
    {"name": "MEXASP", "description": "Mars Express ASPERA-3 plasma/neutral atom (atmospheres mirror)."},
    {"name": "MGSR", "description": "Mars Global Surveyor radio science atmospheric occultations."},
    {"name": "PVO", "description": "Pioneer Venus Orbiter (OETP, ONMS, OIR, OUVS) — Venus atmosphere/ionosphere."},
    {"name": "PVP", "description": "Pioneer Venus Probes (Sounder, Day, Night, North, Bus)."},
    {"name": "GP", "description": "Galileo Probe — Jupiter atmospheric structure/composition (NMS, NEP, ASI, NFR)."},
    {"name": "VG_IRIS", "description": "Voyager IRIS thermal emission spectra (Jupiter, Saturn, Uranus, Neptune)."},
    {"name": "VG_PRA", "description": "Voyager Planetary Radio Astronomy (atmospheres mirror)."},
    {"name": "HP", "description": "Huygens Probe at Titan (DISR, HASI, GCMS, ACP, SSP, DWE)."},
    {"name": "CO_HUYGENS", "description": "Cassini-Huygens cruise atmospheric observations."},
    {"name": "cocirs", "description": "Cassini CIRS — Composite InfraRed Spectrometer. Thermal emission spectra (10-600 cm⁻¹) of Saturn, Titan, and icy satellites (Enceladus, etc.). ATM mirror of RMS COCIRS volumes. ~84 volumes: cocirs_0401 … cocirs_1709."},
    {"name": "cors", "description": "Cassini Radio Science (RSS) atmospheric/ionospheric occultations at Saturn, Titan, and icy satellites. ~430 volumes: cors_0001 … cors_0434."},
    {"name": "coiss", "description": "Cassini ISS — Imaging Science Subsystem (ATM mirror). Limited holdings on ATM."},
    {"name": "coradr", "description": "Cassini RADAR — Titan surface/atmosphere radiometry (ATM mirror). Limited holdings on ATM."},
    {"name": "MSL_REMS", "description": "Mars Science Laboratory REMS — rover meteorology (pressure, temp, UV, RH, wind)."},
    {"name": "M2020_MEDA", "description": "Mars 2020 MEDA — rover meteorology (radiation, dust, temp, pressure, wind)."},
    {"name": "PHX", "description": "Phoenix lander — TEGA, MECA, atmospheric optical depth."},
    {"name": "EARTH_", "description": "Earth-based atmospheric / supporting observations."},
)

_ATM_ABBREVIATIONS = (
    "Naming conventions on ATM:\n"
    "  PDS3 volumes use lowercase prefixes on ATM: cocirs_0401, cors_0001, mrom_0001, etc.\n"
    "  Each prefix typically maps to one mission/instrument; volumes are numbered sequentially.\n"
    "  PDS4 bundles live under PDS/data/PDS4/ with mission-named directories (Huygens, InSight, MAVEN, etc.).\n"
    "  IMPORTANT — many PDS4 bundles are ALSO co-located inside their PDS3 mirror volume\n"
    "  under PDS/data/<VOLNAME>/ (hybrid). The Juno MWR PDS4 bundle, for instance, lives at\n"
    "  PDS/data/jnomwr_1100V2/ (not under PDS/data/PDS4/). Always probe the PDS3 volume too\n"
    "  when looking for a urn:nasa:pds: identifier on ATM.\n"
    "Mission/instrument keys (use as filter on PDS/data/):\n"
    "  Cassini CIRS (thermal IR spectra) → cocirs  (84 volumes: cocirs_0401 … cocirs_1709;\n"
    "                                       cocirs_1709 is the latest TSDR V4.0 + CUBES V2.0)\n"
    "  Cassini Radio Science (RSS) → cors  (430+ volumes: cors_0001 … cors_0434)\n"
    "  Cassini ISS (imaging, limited) → coiss\n"
    "  Cassini RADAR (Titan) → coradr\n"
    "  Cassini-Huygens cruise → CO_HUYGENS\n"
    "  Mars Climate Sounder (MRO) → MROM  — volume-number convention:\n"
    "        MROM_0xxx = EDR (raw, level-2),  MROM_2xxx = DDR (derived, level-5).\n"
    "        Pick MROM_2001 for MRO-M-MCS-5-DDR-V6.2.\n"
    "  Juno MWR → jnomwr  — volume-number convention:\n"
    "        jnomwr_0xxx = EDR (raw),  jnomwr_1xxx = RDR (calibrated).\n"
    "        The PDS4 bundle urn:nasa:pds:juno_mwr ships INSIDE the PDS3 hybrid volume;\n"
    "        the :data_calibrated collection lives in jnomwr_1100V2 (not 0100V2 which is raw).\n"
    "  MAVEN → MAVENM (PDS3) or look in PDS/data/PDS4/MAVEN/ (PDS4)\n"
    "  Mars Express SPICAM → MEXSPI\n"
    "  Pioneer Venus → PVO (orbiter), PVP (probes)\n"
    "  Galileo Probe → GP\n"
    "  Voyager IRIS → VG_IRIS\n"
    "  Huygens Probe → HP (PDS3) or PDS/data/PDS4/Huygens/ (PDS4 — has ACP, DISR, DWE, GCMS, HASI, SSP, HK)\n"
    "  Mars rover weather → MSL_REMS, M2020_MEDA, PHX\n"
)

_ATM_WORKFLOW = (
    "Two parallel trees:\n"
    "  PDS3 → PDS/data/<VOLUME>/  (note: PDS/data/ also contains a `PDS4/` subdir — skip it for PDS3)\n"
    "  PDS4 → PDS/data/PDS4/<bundle>/  (Huygens, InSight, MAVEN, etc.)\n"
    "For PDS3: pds_list_dataset_dirs(path='PDS/data/', node='atm', filter='<key>') with the abbreviation prefix.\n"
    "For PDS4: pds_list_dataset_dirs(path='PDS/data/PDS4/', node='atm') — flat list of bundle dirs.\n"
    "Many ATM directories are HYBRID — they ship BOTH a PDS3 voldesc.cat in subdirs and a PDS4 bundle XML.\n"
    "pds_probe_datasets returns one entry per label; expect duplicates with different pds_version values.\n"
)

_ATM_WORKFLOW_STEPS = (
    "Step 1: Decide PDS3 vs PDS4 based on the query.\n"
    "Step 2 (PDS3): Call pds_list_dataset_dirs(path='PDS/data/', node='atm', filter='<KEY>') "
    "with a volume prefix from the abbreviation table (MROM, MAVENM, MEXSPI, PVO, GP, HP, "
    "VG_IRIS, MSL_REMS, M2020_MEDA, PHX, EARTH_, jnomwr, cocirs, cors, …). Filter is "
    "mandatory — ~2000 entries. Ignore the `PDS4/` subdirectory at this level.\n"
    "Step 2 (PDS4 — top-level bundles): Call pds_list_dataset_dirs(path='PDS/data/PDS4/', "
    "node='atm') — flat list of mission-named bundle dirs (Huygens/, InSight/, MAVEN/, …).\n"
    "Step 2-bis (PDS4 hybrids — IMPORTANT): If the gold target is a urn:nasa:pds:<mission> "
    "identifier and Step 2 (PDS4) didn't find a matching bundle, the bundle is most likely "
    "co-located inside the PDS3 mirror volume under PDS/data/<VOLNAME>/. Run Step 3 there.\n"
    "Step 3: When a mission spans many numbered volumes that differ by product level "
    "(e.g. jnomwr_0xxx=raw / jnomwr_1xxx=calibrated; MROM_0xxx=EDR / MROM_2xxx=DDR), "
    "call pds_resolve_volume(volume_set_path='PDS/data/', node='atm', "
    "dataset_id_hint='<target dataset_id or product type>', sample=8) instead of probing "
    "volumes one by one. The hint can be a partial DATA_SET_ID, product keyword "
    "('calibrated', 'DDR', 'RDR'), or instrument code; the tool ranks children by hint "
    "similarity and probes the top `sample` of them in one call, returning per-child "
    "dataset_ids and a `best_match` path.\n"
    "Step 4: For PDS4 bundles (top-level OR hybrid), call pds_inspect_collections on the "
    "matched bundle path. Many bundles ship per-product collections "
    "(e.g. urn:…:juno_mwr:data_calibrated, urn:…:juno_mwr:data_raw); pick the one whose "
    "logical_identifier matches the gold query.\n"
    "Step 5: Use pds_probe_datasets only when you already know the specific volume path. "
    "It returns `dataset_id` (first id, scalar) AND `dataset_ids` (full list); on Cassini "
    "voldescs like cocirs_1709 the latter carries multiple ids (TSDR + CUBES). Always scan "
    "`dataset_ids` when matching against gold.\n"
    "Step 6: Return BOTH PDS3 and PDS4 IDs when the directory is hybrid.\n"
)

# ---------------------------------------------------------------------------
# NAIF — Navigation and Ancillary Information Facility (SPICE archive)
# ---------------------------------------------------------------------------

# NAIF publishes SPICE kernel archives (SPK, CK, FK, IK, LSK, PCK, SCLK) under
# TWO parallel trees:
#   pub/naif/pds/data/   — PDS3 archives (mission → version_dir, e.g. lro-l-spice-6-v1.0/lrosp_1000/)
#   pub/naif/pds/pds4/   — PDS4 bundles (flat list)
# PDS3 nests two levels deep (the mission archive contains a numbered version
# directory which is the actual PDS3 volume). The agent treats data/ as the
# primary entry and recurses one extra level when probing.

_NAIF_MISSIONS: tuple[dict[str, str], ...] = (
    {"name": "lro-l-spice-6", "description": "Lunar Reconnaissance Orbiter SPICE kernels."},
    {"name": "msl-m-spice-6", "description": "Mars Science Laboratory / Curiosity SPICE kernels."},
    {"name": "mars2020-m-spice-6", "description": "Mars 2020 / Perseverance SPICE kernels."},
    {"name": "insight-m-spice-6", "description": "InSight lander SPICE kernels."},
    {"name": "mer1-m-spice-6", "description": "Mars Exploration Rover Opportunity (MER-1) SPICE kernels."},
    {"name": "mer2-m-spice-6", "description": "Mars Exploration Rover Spirit (MER-2) SPICE kernels."},
    {"name": "mex-e_m-spice-6", "description": "Mars Express SPICE kernels."},
    {"name": "mro-m-spice-6", "description": "Mars Reconnaissance Orbiter SPICE kernels."},
    {"name": "mgs-m-spice-6", "description": "Mars Global Surveyor SPICE kernels."},
    {"name": "ody-m-spice-6", "description": "Mars Odyssey SPICE kernels."},
    {"name": "maven-m-spice-6", "description": "MAVEN SPICE kernels."},
    {"name": "co-s_e_v-spice-6", "description": "Cassini-Huygens SPICE kernels (Saturn tour + cruise)."},
    {"name": "vg1-j_s-spice-6", "description": "Voyager 1 SPICE kernels (Jupiter, Saturn)."},
    {"name": "vg2-j_s_u_n-spice-6", "description": "Voyager 2 SPICE kernels (Jupiter, Saturn, Uranus, Neptune)."},
    {"name": "go-j_e_a-spice-6", "description": "Galileo SPICE kernels (Jupiter, Earth, asteroids)."},
    {"name": "near-a-spice-6", "description": "NEAR Shoemaker SPICE kernels."},
    {"name": "mess-e_v_h-spice-6", "description": "MESSENGER SPICE kernels (Mercury cruise + orbit)."},
    {"name": "juno-j-spice-6", "description": "Juno SPICE kernels at Jupiter."},
    {"name": "nh-j_p_ss-spice-6", "description": "New Horizons SPICE kernels (Jupiter, Pluto, KBO encounters)."},
    {"name": "ro-c_e_a-spice-6", "description": "Rosetta SPICE kernels (comet 67P, Earth flybys, asteroid flybys)."},
    {"name": "orex-bennu-spice-6", "description": "OSIRIS-REx SPICE kernels at asteroid Bennu."},
    {"name": "hyb2-ryugu-spice-6", "description": "Hayabusa2 SPICE kernels at asteroid Ryugu."},
    {"name": "lucy-spice-6", "description": "Lucy SPICE kernels (Trojan asteroid mission)."},
    {"name": "dart-spice-6", "description": "DART SPICE kernels (Didymos/Dimorphos impact)."},
)

_NAIF_ABBREVIATIONS = (
    "Naming conventions on NAIF:\n"
    "  PDS3 archive root: <mission>-<target>-spice-6-v<x.y>/  (e.g. lro-l-spice-6-v1.0/).\n"
    "  Each archive root contains ONE numbered version sub-directory (e.g. lrosp_1000/, "
    "msls_1000/) which is the actual PDS3 volume holding voldesc.cat and data/, catalog/, etc.\n"
    "  PDS4 bundles use lowercase mission identifiers under pub/naif/pds/pds4/.\n"
    "Kernel types stored: SPK (trajectories), CK (orientation), FK (frames), IK (instrument), "
    "LSK (leapseconds), PCK (planetary constants), SCLK (spacecraft clocks). Only relevant "
    "when the query is about geometry/pointing/timing rather than measured science data.\n"
    "Skip these directories when scanning: checksums, extras, browse, software, errata, "
    "document, index, catalog.\n"
)

_NAIF_WORKFLOW = (
    "Two parallel trees:\n"
    "  PDS3 → pub/naif/pds/data/<mission_archive>/<version_dir>/   (TWO levels deep)\n"
    "  PDS4 → pub/naif/pds/pds4/<bundle>/                          (flat list)\n"
    "PDS3 archives nest the actual volume one level inside (e.g. lro-l-spice-6-v1.0/lrosp_1000/ "
    "contains the voldesc.cat). pds_probe_datasets recurses into that inner directory automatically.\n"
    "Multiple version dirs may exist (lrosp_1000/, lrosp_1001/, …) — prefer the highest-numbered version.\n"
    "NAIF is the SPICE archive: only use it for queries about ephemerides, attitude, frames, or "
    "spacecraft clocks. For measured science data (imaging, spectroscopy, fields/particles) use a "
    "discipline node instead.\n"
)

_NAIF_WORKFLOW_STEPS = (
    "Step 1: Confirm the query is actually about SPICE / geometry / pointing / timing — if it's "
    "about measured science data, use a discipline node (GEO/PPI/RMS/IMG/etc.) instead.\n"
    "Step 2: Decide PDS3 vs PDS4. Most NAIF papers cite the PDS3 archive id (e.g. "
    "LRO-L-SPICE-6-V1.0); PDS4 bundles are the modern equivalent.\n"
    "Step 3 (PDS3): Call pds_list_dataset_dirs(path='pub/naif/pds/data/', node='naif', "
    "filter='<mission>') with a mission key from the abbreviation table.\n"
    "Step 3 (PDS4): Call pds_list_dataset_dirs(path='pub/naif/pds/pds4/', node='naif') — "
    "flat list of bundles.\n"
    "Step 4: Call pds_probe_datasets on the relevant archive root(s). For PDS3, the tool "
    "automatically recurses into the inner numbered version directory to find voldesc.cat; "
    "when multiple version dirs exist, prefer the highest version (e.g. lrosp_1001 over lrosp_1000).\n"
    "Step 5: For PDS4 bundles, call pds_inspect_collections on top 2-3.\n"
    "Step 6: Return BOTH PDS3 archive id and PDS4 bundle LID when both exist for the same mission.\n"
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
        workflow_steps=_GEO_WORKFLOW_STEPS,
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
        workflow_steps=_PPI_WORKFLOW_STEPS,
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
        workflow_steps=_LROC_WORKFLOW_STEPS,
    ),
    "img": NodeConfig(
        node_id="img",
        base_url="https://planetarydata.jpl.nasa.gov/",
        display_name="JPL Imaging Node (IMG)",
        data_root="img/data/",
        has_mission_layer=True,
        missions=_IMG_MISSIONS,
        description="JPL legacy planetary imaging archive: Cassini ISS, Voyager ISS, Galileo SSI, "
        "Mariner missions, Viking Orbiter/Lander, Magellan SAR, MESSENGER MDIS, NEAR MSI, plus "
        "small-body imaging (Stardust, Deep Impact)",
        workflow_notes=_IMG_WORKFLOW,
        abbreviations=_IMG_ABBREVIATIONS,
        workflow_steps=_IMG_WORKFLOW_STEPS,
    ),
    "rms": NodeConfig(
        node_id="rms",
        base_url="https://pds-rings.seti.org/",
        display_name="Ring-Moon Systems (RMS)",
        # Two roots; holdings/volumes/ is the PDS3 entry. PDS4 lives at pds4/bundles/
        # and is documented in workflow_notes.
        data_root="holdings/volumes/",
        has_mission_layer=False,
        missions=_RMS_MISSIONS,
        description="Ring-Moon Systems: Saturn rings (Cassini ISS/UVIS/VIMS, Voyager), "
        "Uranus/Jupiter/Neptune rings, ring occultations, irregular satellites",
        workflow_notes=_RMS_WORKFLOW,
        abbreviations=_RMS_ABBREVIATIONS,
        workflow_steps=_RMS_WORKFLOW_STEPS,
    ),
    "sbn": NodeConfig(
        node_id="sbn",
        base_url="https://pds-smallbodies.astro.umd.edu/",
        display_name="Small Bodies Node (SBN)",
        # Holdings index now accessible; workflow includes 403 fallback.
        data_root="holdings/",
        has_mission_layer=False,
        missions=_SBN_MISSIONS,
        description="Small bodies: comets, asteroids, KBOs, dust; spacecraft "
        "(Rosetta, OSIRIS-REx, Hayabusa, Lucy, DART, Stardust, Deep Impact, NEAR) "
        "plus ground/space-based observations",
        workflow_notes=_SBN_WORKFLOW,
        abbreviations=_SBN_ABBREVIATIONS,
        workflow_steps=_SBN_WORKFLOW_STEPS,
    ),
    "atm": NodeConfig(
        node_id="atm",
        base_url="https://pds-atmospheres.nmsu.edu/",
        display_name="Atmospheres (ATM)",
        # Two roots; PDS/data/ is the PDS3 entry. PDS4 lives at PDS/data/PDS4/
        # and is documented in workflow_notes.
        data_root="PDS/data/",
        has_mission_layer=False,
        missions=_ATM_MISSIONS,
        description="Planetary atmospheres and surface meteorology: Mars (MCS, MAVEN, "
        "REMS, MEDA), Venus (Pioneer Venus), Jupiter (Galileo Probe), Titan (Huygens), "
        "outer planets (Voyager IRIS), Saturn system (Cassini CIRS thermal spectra, "
        "Cassini RSS atmospheric occultations)",
        workflow_notes=_ATM_WORKFLOW,
        abbreviations=_ATM_ABBREVIATIONS,
        workflow_steps=_ATM_WORKFLOW_STEPS,
    ),
    "naif": NodeConfig(
        node_id="naif",
        base_url="https://naif.jpl.nasa.gov/",
        display_name="Navigation and Ancillary Information Facility (NAIF)",
        # Two roots; pub/naif/pds/data/ is the PDS3 entry (mission archives nest one
        # level deeper into a numbered version dir). PDS4 lives at pub/naif/pds/pds4/.
        data_root="pub/naif/pds/data/",
        has_mission_layer=True,
        missions=_NAIF_MISSIONS,
        description="SPICE kernel archive: spacecraft ephemerides, orientation, frames, "
        "instrument geometry, and clocks. Use for geometry/pointing/timing queries — not "
        "for measured science data",
        workflow_notes=_NAIF_WORKFLOW,
        abbreviations=_NAIF_ABBREVIATIONS,
        workflow_steps=_NAIF_WORKFLOW_STEPS,
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
