# IMG optimization brief

## Friction the prompt fixes solve

- **P-img-1**: `_IMG_MISSIONS` was missing `mro/`, `mer/`, and `lro/`, all
  of which exist as real directories under `img/data/`. The agent had to
  guess these paths.
- **P-img-2**: Some gold PDS4 LIDs (`urn:nasa:pds:messenger_mdis_1001`,
  `urn:nasa:pds:mer{1,2}_<inst>_*`, `urn:nasa:pds:mro_hirise_*`) are NOT
  mirrored at IMG even though the PDS3 equivalents are. The agent burned
  multiple calls hunting for a PDS4 bundle that doesn't exist.

## Registry diffs

- `_IMG_MISSIONS`: added `mro` (with note about CTX vs HiRISE coverage),
  `mer` (with PDS3-only PDS4 note), and `lro` (limited mirror). Updated
  `messenger` description to call out the missing PDS4 mirror explicitly.
- `_IMG_WORKFLOW`: added the "PDS4 coverage is partial — fall back to PDS3
  DATA_SET_ID when no bundle is found" paragraph.
- `_IMG_WORKFLOW_STEPS`: added Step 3 (volume-set targets use
  `pds_resolve_volume`) and Step 5 (PDS4-not-mirrored fallback, capped at
  one extra list/probe). Mentions the new `dataset_ids` field in Step 6.

## Verification (driver, post-edit)

- Q13 (`urn:nasa:pds:messenger_mdis_1001`): under the new workflow the
  agent stops after 1 list (`img/data/messenger/`) + 1 probe
  (`MSGRMDS_1001/`) and returns `MESS-E/V/H-MDIS-2-EDR-RAWDATA-V1.0`
  with the "PDS4 not mirrored at IMG" note. **2 calls** (was 3, partial).
- Q14 (`MRO-M-CTX-2-EDR-L0-V1.0` + `MRO-M-HIRISE-3-RDR-V1.1`): mission
  table now lists `mro/`. `list_dataset_dirs(img/data/mro/ctx/)` then
  `probe(mrox_0001)` returns CTX exact id. HiRISE main volumes still
  aren't mirrored at IMG (Step 5 explains why and returns the empty
  result with a clear note). **2 calls** (was 4, partial).
- Q15 (`urn:nasa:pds:mer2_pancam_sci_calibrated2`): list + probe of
  `mer2-m-pancam-3-radiometric-ops-v1.0` returns the closest PDS3
  calibrated id with the PDS4-not-mirrored note. **2 calls** (was 4,
  partial).
