# GEO optimization brief

## Friction the prompt fixes solve

None. All 3 GEO queries in the baseline resolved exactly within 2–3
calls and the workflow_steps already match the optimal trace.

## Registry diffs

No edits to `_GEO_*` were necessary. The Phase 3 tool changes (T1
`dataset_ids`, T2 PDS4-bundle pds_hint) apply automatically through
the shared `pds_list_dataset_dirs` / `pds_probe_datasets` tools.

## Verification (driver, post-edit)

- Q1 (`MEX-M-HRSC-5-REFDR-DTM-V1.0`): list filter=hrsc-5 + probe. **2
  calls** (was 2).
- Q2 (`urn:nasa:pds:magellan_gxdr:data`): list filter=gxdr + probe +
  inspect_collections. **3 calls** (was 3).
- Q3 (`MRO-M-CRISM-5-RDR-MULTISPECTRAL-V1.0`): list filter=crism-5 +
  probe. **2 calls** (was 2).
