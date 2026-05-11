# ATM optimization brief

## Friction the prompt fixes solve

- **P-atm-1**: PDS4 bundles can live INSIDE the PDS3 mirror tree (hybrid
  volumes like `PDS/data/jnomwr_1100V2/` carry both a PDS3 voldesc and a
  PDS4 bundle XML). The old workflow_notes only mentioned `PDS/data/PDS4/`
  as the PDS4 entry point, so the agent burned calls hunting in
  `PDS/data/PDS4/` for `urn:nasa:pds:juno_mwr:data_calibrated` that
  doesn't live there.
- **P-atm-2**: Volume-number → product-level conventions weren't surfaced.
  `MROM_0xxx`=EDR vs `MROM_2xxx`=DDR, `jnomwr_0xxx`=raw vs
  `jnomwr_1xxx`=RDR/calibrated, `cocirs_1709`=latest TSDR V4.0.

## Registry diffs

- `_ATM_ABBREVIATIONS`:
  - Added the hybrid-PDS4-inside-PDS3 note.
  - Annotated MROM with the `_0xxx`/`_2xxx` split.
  - Annotated jnomwr with `_0xxx` (raw) / `_1xxx` (calibrated) and pointed
    at `jnomwr_1100V2` for `:data_calibrated`.
  - Annotated cocirs_1709 as the latest TSDR+CUBES.
- `_ATM_WORKFLOW_STEPS`:
  - Added Step 2-bis (look in PDS3 mirror when PDS4 dir doesn't appear).
  - Step 3 now points at `pds_resolve_volume` for volume-series targets.
  - Step 5 now says to scan the new `dataset_ids` list field.

## Verification (driver, post-edit)

- Q4 (`juno_mwr:data_calibrated`): `resolve_volume(PDS/data/, hint='juno_mwr
  calibrated')` returns jnomwr_1100V2 with volume_name "CALIBRATED PRODUCTS";
  `inspect_collections` finds `:data_calibrated`. **2 calls** (was 5).
- Q5 (`MRO-M-MCS-5-DDR-V6.2`): direct probe of `PDS/data/MROM_2001/`
  returns the gold id in `dataset_id`. **1 call** (was 3).
- Q6 (`CO-S-CIRS-2/3/4-TSDR-V4.0`): direct probe of `PDS/data/cocirs_1709/`
  returns the gold id; T1's `dataset_ids` exposes both TSDR + CUBES.
  **1 call** (was 2).
