# PPI optimization brief

## Friction the prompt fixes solve

- **P-ppi-1**: PDS3 dataset-named dirs on PPI replace `/` with `_` (dir
  `JNO-J_SW-JAD-5-CALIBRATED-V1.0` ↔ DATA_SET_ID
  `JNO-J/SW-JAD-5-CALIBRATED-V1.0`). Surface the convention so the agent
  can map gold ids to dir names without surprise.

## Registry diffs

- `_PPI_ABBREVIATIONS`: appended a 3-line "Slash-encoding in
  DATA_SET_IDs" paragraph with two concrete examples
  (JNO-J/SW-JAD-5-CALIBRATED-V1.0, MESS-E/V/H/SW-EPPS-3-FIPS-DDR-V2.0).

## Verification (driver, post-edit)

PPI was already the smoothest node in the baseline (all 3 queries in 2
calls). The slash-encoding note doesn't change call counts; it makes
the agent more confident:

- Q7 (`urn:nasa:pds:cassini-mag-cal:data-1min-krtp`): T2 now tags
  `cassini-mag-cal` as PDS4 on the listing. **2 calls** (was 2; cleaner).
- Q8 (`MESS-E_V_H_SW-EPPS-3-FIPS-DDR-V2.0`): 1 list + 1 batched probe of
  both EPPS and MAG dirs. The slash-mapping note prevents the agent from
  wondering whether the dir is misnamed. **2 calls** (was 2).
- Q9 (`JNO-J/SW-JAD-5-CALIBRATED-V1.0` + `JNO-J-JED-3-CDR-V1.0`): same
  as Q8. **2 calls** (was 2).
