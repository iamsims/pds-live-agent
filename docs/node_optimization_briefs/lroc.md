# LROC optimization brief

## Friction the prompt fixes solve

None. LROC has only 3 datasets total and all 3 are PDS3-hybrid-with-PDS4
products listed at the data/ root. The existing workflow_steps already
say "skip pds_list_missions, go straight to list_dataset_dirs". Every
gold LROC query reaches the answer in 2 calls.

## Registry diffs

No edits to `_LROC_*` were necessary.

## Verification (driver, post-edit)

- Q10, Q11, Q12 (`LRO-L-LROC-5-RDR-V1.0`): list_dataset_dirs(data/) +
  probe(LRO-L-LROC-5-RDR-V1.0/). **2 calls each** (unchanged).
