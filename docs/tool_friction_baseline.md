# Tool friction baseline — Phase 1

Orchestrator (me) ran 18 gold queries (3 per node × 6 nodes) through
`scripts/orchestrator_driver.py`, calling the 5 MCP tool functions
directly (no LLM, no MCP transport). One tool call per step; I recorded
the call sequence, success vs. gold `Expected Identifiers`, and the
friction I felt.

Per the plan, an answer is "successful" if I reached the gold
identifier with ≤ 8 tool calls. "Version drift" = gold identifier
family found but its specific version number doesn't match what the
node currently hosts. "PDS4-missing" = gold gives a `urn:nasa:pds:…`
LID that the node doesn't appear to host; only the PDS3 equivalent
is present.

`select_node` is not counted as a tool call (the orchestrator may or
may not consult it; the live agent always does).

## Results

| # | Node | Gold target (short) | Calls | Result |
|---|------|----------------------|-------|--------|
| 1 | geo  | MEX-M-HRSC-5-REFDR-DTM-V1.0 | 2 | ✅ exact |
| 2 | geo  | urn:nasa:pds:magellan_gxdr:data | 3 | ✅ exact |
| 3 | geo  | MRO-M-CRISM-5-RDR-MULTISPECTRAL-V1.0 | 2 | ✅ exact |
| 4 | atm  | urn:nasa:pds:juno_mwr:data_calibrated | 5 | ✅ exact (volume jnomwr_1100V2) |
| 5 | atm  | MRO-M-MCS-5-DDR-V6.2 | 3 | ✅ exact (volume MROM_2001) |
| 6 | atm  | CO-S-CIRS-2/3/4-TSDR-V4.0 | 2 | ✅ exact (volume cocirs_1709) |
| 7 | ppi  | urn:nasa:pds:cassini-mag-cal:data-1min-krtp | 2 | ✅ exact |
| 8 | ppi  | MESS-E_V_H_SW-EPPS-3-FIPS-DDR-V2.0 + MAG-3-CDR-CALIBRATED-V1.0 | 2 | ✅ exact (batched probe) |
| 9 | ppi  | JNO-J/SW-JAD-5-CALIBRATED-V1.0 + JNO-J-JED-3-CDR-V1.0 | 2 | ✅ exact |
| 10 | lroc | LRO-L-LROC-5-RDR-V1.0 | 2 | ✅ exact |
| 11 | lroc | LRO-L-LROC-5-RDR-V1.0 | 2 | ✅ exact |
| 12 | lroc | LRO-L-LROC-5-RDR-V1.0 | 2 | ✅ exact |
| 13 | img  | urn:nasa:pds:messenger_mdis_1001 | 3 | ⚠ PDS4-missing — only PDS3 (MESS-E/V/H-MDIS-2-EDR-RAWDATA-V1.0) present |
| 14 | img  | MRO-M-HIRISE-3-RDR-V1.1 + MRO-M-CTX-2-EDR-L0-V1.0 | 4 | ⚠ CTX exact; HIRISE main volumes not present (only EXTRAS) |
| 15 | img  | urn:nasa:pds:mer2_pancam_sci_calibrated2 | 4 | ⚠ PDS4-missing — only PDS3 mer2-m-pancam-* dirs present |
| 16 | rms  | CO-S-UVIS-2-SSB-V1.0 + CO-S-ISSNA/ISSWA-2-EDR-V1.0 | 6 | ⚠ ISS exact; UVIS version drift (V1.0 gold → V1.2 hosted) |
| 17 | rms  | CO-S-VIMS-2-EDR-V1.0 | 2 | ⚠ family found (CO-E/V/J/S-VIMS-2-QUBE-V1.0); EDR variant not hosted |
| 18 | rms  | CO-S-UVIS-2-SPEC-V1.2 | 3 | ✅ exact (volume COUVIS_0xxx_v1/COUVIS_0009) |

**Median:** 2 calls. **Mean:** 2.8. **Successes (exact, ≤8 calls):**
12/18 (67%). Three RMS and three IMG cases are partial (gold version
or PDS4 form not actually hosted) — these aren't tool failures, but
some are still fixable with better prompt hints.

## Friction notes — tool-level (cross-node)

T1. **Multi-`DATA_SET_ID` voldescs collapse `probe_datasets.dataset_id`
to null.** Cassini volumes (CIRS cocirs_*, UVIS COUVIS_*, VIMS COVIMS_*)
ship voldesc.cat files where `DATA_SET_ID` is a list of 4+ IDs (one per
product type on the volume). `probe_datasets._extract_dataset_id` only
returns a scalar string; for list-valued IDs it returns `null` and the
agent has to dig into `fields.VOLUME.DATA_SET_ID`. Affects RMS, ATM,
some PPI. **Generic fix:** in `probe_datasets`, when `DATA_SET_ID` is a
list, surface it as `dataset_ids: list[str]` alongside the scalar
`dataset_id` (left as the first element or null for backward compat).

T2. **`pds_hint` heuristic misses lowercase PDS4 dirs.** The regex
`_PDS3_DIR_RE` matches uppercase/hyphen-version PDS3 names and
`urn-nasa-pds-` prefixes are caught for PDS4 — but PDS4 bundles on PPI
(`cassini-mag-cal`), RMS (`cassini_iss`), and ATM PDS4 (`juno_jiram_bundle`)
use plain lowercase descriptive names with **no** `urn-` prefix, so they
get `pds_hint: null`. The agent then guesses. Affects PPI, RMS, ATM.
**Generic fix:** broaden `_infer_pds_version` so that dirs missing
voldesc-style version suffixes but matching common PDS4 conventions
(lowercase with underscores, contains `bundle`, etc.) are tagged
`PDS4` — or, more conservatively, add a `name_kind` enum
(`volume_dir`, `bundle_dir`, `unknown`) so the agent has explicit
guidance without us guessing PDS3 vs PDS4 wrongly.

T3. **No "find which volume of a set contains target X" tool.** RMS
volume-sets (COUVIS_0xxx, COISS_2xxx) and ATM volume series (jnomwr_*,
MROM_2xxx, cocirs_*) contain many numbered volumes; the gold answer
lives in a specific one (e.g. jnomwr_1100V2 = calibrated, MROM_2xxx =
DDR, cocirs_1709 = latest V4.0 TSDR). The agent has to either (a) know
the convention from the abbreviation table (often missing or partial),
or (b) probe several volumes by hand. Affects RMS (6-call Q16), ATM
(5-call Q4). **Generic fix candidate (new tool):** `pds_resolve_volume`
that, given a volume-set path and an optional DATA_SET_ID hint string,
probes a sample of volumes and returns which volume(s) contain which
DATA_SET_ID. Capped at 1 new tool per plan; this is the strongest
candidate because it would save calls on ≥3 nodes (RMS, ATM, some IMG).

## Friction notes — prompt-level (per-node)

P-atm-1. ATM `workflow_notes` says PDS4 lives under `PDS/data/PDS4/`,
but several PDS4 bundles (juno_mwr, etc.) are co-located with their
PDS3 mirror under `PDS/data/<VOLNAME>/` (hybrid volumes). The agent
that follows the workflow_notes literally won't find them. Fix in
`_ATM_WORKFLOW` and `_ATM_WORKFLOW_STEPS`.

P-atm-2. ATM `abbreviations` has `MROM` → "Mars Climate Sounder" but
doesn't say `MROM_2xxx` = DDR (level-5 derived), `MROM_0xxx` = EDR
(raw). Same for `jnomwr_0100/0100V2` (raw) vs `jnomwr_1100/1100V2`
(calibrated), and `cocirs_1709` = latest V4.0 TSDR. Adding these one-
liner volume conventions would cut ATM queries 4, 5, 6 each by 1–2
calls.

P-img-1. IMG `_IMG_MISSIONS` is missing `mro/` (CTX, HIRISE, MARCI),
`mer/` (MER1/MER2 cameras + APXS), and `mer1/mer2` PDS3 dataset dirs
that live directly under `img/data/`. The orchestrator had to guess
`img/data/mer/` and `img/data/mro/` exist. Add these.

P-img-2. IMG `workflow_notes` should warn that **some PDS4 LIDs in
gold (`urn:nasa:pds:messenger_mdis_1001`, `urn:nasa:pds:mer2_pancam_*`)
do not exist on IMG** — only the PDS3 equivalents are mirrored. Without
this, the agent will burn calls hunting for a PDS4 bundle that doesn't
exist. The step should be: "if a urn: target isn't found at IMG after
1 list_dataset_dirs and 1 probe, return the closest PDS3 equivalent
DATA_SET_ID with a note that IMG hosts only PDS3 for this mission."

P-rms-1. RMS `abbreviations` says COUVIS_0xxx = "raw + calibrated
spectra/images" but the Saturn-tour subset starts at COUVIS_0009. The
agent that probes COUVIS_0001 gets the Jupiter encounter dataset
(CO-J-UVIS-…) and burns a call. Add "Saturn UVIS volumes start at
COUVIS_0009; volumes 0001–0008 are Jupiter encounter (CO-J-UVIS-…)".

P-rms-2. RMS `workflow_steps` doesn't mention that COUVIS/COISS/COVIMS
voldescs contain **multiple `DATA_SET_ID`s** (one per product type on
the volume). The agent should be told to look inside
`fields.VOLUME.DATA_SET_ID` (often a list) and pick the matching
member. Mitigated by T1 if implemented.

P-rms-3. CO-S-VIMS-2-EDR-V1.0 (gold Q17) doesn't appear on the node;
the hosted equivalent is `CO-E/V/J/S-VIMS-2-QUBE-V1.0`. This is a gold-
spec issue, not solvable from the prompt, but flagging the convention
"VIMS volumes carry QUBE-V1.0, not EDR-V1.0" in abbreviations would
help the agent return the right answer with a confidence note.

P-ppi-1. PPI is the smoothest node in the baseline (all 3 queries in 2
calls). One small win: noting that several PDS3 dataset-named dirs on
PPI replace `/` with `_` in their directory name
(`JNO-J_SW-JAD-5-CALIBRATED-V1.0` directory ↔ `JNO-J/SW-JAD-5-CALIBRATED-V1.0`
DATA_SET_ID), so the agent can trust the direct-mapping more
confidently. Currently in the abbreviations as a passing remark — make
it a Step.

## Tagging for Phase 2

| Friction | Affected nodes | Tag |
|----------|----------------|-----|
| T1 multi-DATA_SET_ID collapse | rms, atm, some ppi | tool (helps ≥3 nodes) |
| T2 lowercase PDS4 hint | ppi, rms, atm | tool (helps ≥3 nodes) |
| T3 volume-set resolver | rms, atm, img | tool (new tool — helps ≥3 nodes) |
| P-atm-1 hybrid PDS3+PDS4 in PDS/data/ | atm | prompt |
| P-atm-2 volume-number conventions | atm | prompt |
| P-img-1 missing missions (mro/, mer/) | img | prompt |
| P-img-2 PDS4-not-mirrored note | img | prompt |
| P-rms-1 COUVIS_0001..0008 = Jupiter | rms | prompt |
| P-rms-2 multi-DATA_SET_ID handling | rms | prompt (T1 helps too) |
| P-rms-3 VIMS QUBE-not-EDR convention | rms | prompt (caveat) |
| P-ppi-1 directory↔DATA_SET_ID slash mapping | ppi | prompt |

Phase 2 will rank these and pick ≤2 tool changes + ≤1 new tool (T1, T2,
T3 are the candidates) plus a per-node prompt edit list for Phase 5.
