# RMS optimization brief

## Friction the prompt fixes solve

- **P-rms-1**: COUVIS_0001..0008 are JUPITER encounter volumes (carry
  `CO-J-UVIS-*`), not Saturn. The agent that picked COUVIS_0001 for a
  Saturn UVIS query got back the wrong dataset and burned calls
  backtracking.
- **P-rms-2**: Cassini voldescs (COUVIS/COISS/COVIMS/COCIRS) declare
  `DATA_SET_ID` as a LIST. The agent has to scan the full list, not just
  the scalar field. T1 surfaces the list as `dataset_ids`; the prompt
  now tells the agent to match against it.
- **P-rms-3**: VIMS uses QUBE not EDR — gold `CO-S-VIMS-2-EDR-V1.0`
  doesn't exist; the node hosts `CO-E/V/J/S-VIMS-2-QUBE-V1.0`. Surfaced
  as a caveat so the agent returns the right answer with a note.

## Registry diffs

- `_RMS_ABBREVIATIONS`:
  - COUVIS volume range annotated: `_0001..0008` = Jupiter (`CO-J-UVIS-…`),
    `_0003` = Jupiter+Saturn transition (earliest CO-S-UVIS-* id), `_0004+` =
    Saturn-only. Added `COUVIS_0xxx_v1` for older v1.0/1.2 ids.
  - COISS volume range annotated with DATA_SET_ID prefixes per range.
  - COVIMS QUBE-not-EDR convention spelled out.
  - Multi-DATA_SET_ID-voldesc paragraph added; agent told to scan
    `dataset_ids` (the new T1 field) when matching gold.
- `_RMS_WORKFLOW_STEPS`: added Step 4b — when target is a specific
  `CO-S-UVIS-2-<TYPE>-V<x>.<y>` id, call `pds_resolve_volume` on
  `COUVIS_0xxx_v1/` with the dataset_id_hint and read `best_match` to
  jump directly to the right volume. Step 6 reminds the agent to scan
  `dataset_ids`.

## Verification (driver, post-edit)

- Q16 (`CO-S-UVIS-2-SSB-V1.0` + `CO-S-ISSNA/ISSWA-2-EDR-V1.0`):
  `resolve_volume(COUVIS_0xxx, hint='CO-S-UVIS-2-SSB')` returns
  `best_match=COUVIS_0003` whose `dataset_ids` contains
  `CO-S-UVIS-2-SSB-V1.2` (version drift vs gold V1.0 noted).
  `list_dataset_dirs(COISS_2xxx)` + `probe(COISS_2001)` returns
  `CO-S-ISSNA/ISSWA-2-EDR-V1.0` exact. **3 calls** (was 6).
- Q17 (`CO-S-VIMS-2-EDR-V1.0`): list + probe COVIMS_0001 returns the
  hosted variant `CO-E/V/J/S-VIMS-2-QUBE-V1.0`; the agent now knows to
  return this with a 'QUBE-not-EDR' caveat. **2 calls** (was 2, but
  result is now interpreted correctly).
- Q18 (`CO-S-UVIS-2-SPEC-V1.2`): `resolve_volume(COUVIS_0xxx_v1,
  hint='CO-S-UVIS-2-SPEC-V1.2')` returns `best_match=COUVIS_0009` with
  the exact id in `dataset_ids`. **2 calls** (was 3).
