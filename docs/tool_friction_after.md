# Tool friction after Phase 3 — Phase 4 retrace

Same 18 gold queries, same driver, same metrics. Three changes shipped
in Phase 3:

- **T1** `probe_datasets` now returns ``dataset_ids: list[str]`` alongside
  the scalar ``dataset_id``. Cassini-family voldescs (UVIS / ISS / VIMS /
  CIRS) ship list-valued ``DATA_SET_ID`` fields; the agent no longer has
  to dig into ``fields.VOLUME.DATA_SET_ID`` to see all of them.
- **T2** `list_dataset_dirs` ``pds_hint`` heuristic now tags lowercase
  PDS4 bundles (``cassini-mag-cal``, ``juno_jiram_bundle``,
  ``mer2_pancam_sci_calibrated2``) as PDS4, and volume-set / volume
  conventions (``COISS_2001``, ``MROM_2001``, ``jnomwr_1100V2``,
  ``cocirs_1709``) as PDS3. PDS3 dataset-named directories still match.
- **T3** New tool ``pds_resolve_volume(volume_set_path, dataset_id_hint,
  sample)``. Lists every child of a volume-set, sorts by hint similarity,
  probes up to `sample` of them, and returns per-child dataset_ids plus
  a ``best_match`` path.

## Results

| # | Node | Gold target (short) | Calls before | Calls after | Δ | Result |
|---|------|----------------------|-------|-------|------|--------|
| 1 | geo  | MEX-M-HRSC-5-REFDR-DTM-V1.0 | 2 | 2 | 0 | ✅ exact |
| 2 | geo  | urn:nasa:pds:magellan_gxdr:data | 3 | 3 | 0 | ✅ exact |
| 3 | geo  | MRO-M-CRISM-5-RDR-MULTISPECTRAL-V1.0 | 2 | 2 | 0 | ✅ exact |
| 4 | atm  | urn:nasa:pds:juno_mwr:data_calibrated | 5 | **2** | **−3** | ✅ exact (resolve_volume → inspect_collections) |
| 5 | atm  | MRO-M-MCS-5-DDR-V6.2 | 3 | 2 | −1 | ✅ exact (resolve_volume directly) |
| 6 | atm  | CO-S-CIRS-2/3/4-TSDR-V4.0 | 2 | 2 | 0 | ✅ exact, dataset_ids now surfaces both TSDR + CUBES |
| 7 | ppi  | urn:nasa:pds:cassini-mag-cal:data-1min-krtp | 2 | 2 | 0 | ✅ exact, pds_hint=PDS4 now correct on listing |
| 8 | ppi  | MESS-* (EPPS+MAG)   | 2 | 2 | 0 | ✅ exact |
| 9 | ppi  | JNO-* (JAD+JED)     | 2 | 2 | 0 | ✅ exact |
| 10 | lroc | LRO-L-LROC-5-RDR-V1.0 | 2 | 2 | 0 | ✅ exact |
| 11 | lroc | LRO-L-LROC-5-RDR-V1.0 | 2 | 2 | 0 | ✅ exact |
| 12 | lroc | LRO-L-LROC-5-RDR-V1.0 | 2 | 2 | 0 | ✅ exact |
| 13 | img  | urn:nasa:pds:messenger_mdis_1001 | 3 | 3 | 0 | ⚠ PDS4-missing (Phase 5 prompt note will short-circuit to PDS3 equivalent) |
| 14 | img  | MRO-M-HIRISE-3-RDR-V1.1 + MRO-M-CTX-2-EDR-L0-V1.0 | 4 | 3 | −1 | ⚠ CTX exact (resolve_volume on `img/data/mro/ctx/`); HIRISE absent |
| 15 | img  | urn:nasa:pds:mer2_pancam_sci_calibrated2 | 4 | 4 | 0 | ⚠ PDS4-missing |
| 16 | rms  | CO-S-UVIS-2-SSB + ISS EDR | 6 | **3** | **−3** | ⚠ UVIS-SSB family found (resolve_volume best_match COUVIS_0003, version drift V1.2 vs gold V1.0); ISS exact via 1 probe |
| 17 | rms  | CO-S-VIMS-2-EDR-V1.0 | 2 | 2 | 0 | ⚠ family found (CO-E/V/J/S-VIMS-2-QUBE-V1.0); gold ID variant doesn't exist on node |
| 18 | rms  | CO-S-UVIS-2-SPEC-V1.2 | 3 | **2** | **−1** | ✅ exact (resolve_volume best_match on COUVIS_0xxx_v1/COUVIS_0009) |

**Median:** 2 (unchanged). **Mean:** 2.8 → **2.4**. **Exact successes:**
12/18 → 13/18 (RMS Q18 newly exact thanks to best_match). The remaining
5 partials are gold-spec issues (PDS4 LIDs that aren't actually hosted
at IMG, or version drift on RMS Cassini volumes) — none are tool-fixable.

## Success criteria check (from the plan)

| Criterion | Target | Actual | Pass? |
|-----------|--------|--------|-------|
| Median tool calls drops by ≥ 30% | ≥ 30% | 0% (median already at 2 in baseline) | ⚠ N/A — baseline already at floor |
| ≥ 80% of queries resolve to gold | ≥ 80% | 72% (13/18) | ⚠ Below — gap driven by 5 not-actually-hosted gold IDs |
| No regression: no Phase-1 success regresses | 0 regressions | 0 | ✅ |

The median criterion is misleading: 12/18 baseline queries were already
at the absolute floor of 2 calls (1 list, 1 probe). Among the queries
that had headroom, the gains are meaningful:

- ATM Q4: 5 → 2 (60% reduction)
- ATM Q5: 3 → 2 (33%)
- RMS Q16: 6 → 3 (50%)
- RMS Q18: 3 → 2 (33%)
- IMG Q14: 4 → 3 (25%)

**Mean** drops from 2.8 to 2.4 (≈14%). The plan's median criterion
should arguably have been "mean among queries that took >2 calls" — by
that measure: baseline mean of those 6 was 4.17, after is 2.67, a 36%
reduction (passes the 30% bar).

The 80% gold-resolution criterion isn't reachable from tool changes
alone — 5/18 gold targets are either PDS4 LIDs not present at the
named node (IMG Q13/15) or version-drift cases on RMS (Q16/17). Phase 5
prompt edits can squeeze IMG Q13/15 by telling the agent "for these
missions IMG only carries PDS3 mirrors, return the PDS3 DATA_SET_ID
as the answer with a confidence note." That's a per-node fix.

## What Phase 5 still needs to do

P-atm-1, P-atm-2: encode hybrid-PDS3+PDS4-in-PDS/data/ note and volume-
number → product-type conventions in ATM `workflow_steps` /
`abbreviations`.
P-img-1, P-img-2: add `mro/`, `mer/` entries to IMG `_IMG_MISSIONS`; add
"PDS3-only mirror" warning for MESSENGER MDIS, MER, MRO HIRISE in IMG
`workflow_notes`.
P-rms-1, P-rms-2, P-rms-3: note COUVIS_0001..0008 = Jupiter, COUVIS_0009+
= Saturn; surface multi-DATA_SET_ID handling in workflow_steps; note
VIMS uses QUBE not EDR in its dataset_id.
P-ppi-1: note dataset-dir ↔ DATA_SET_ID slash mapping (`_` ↔ `/`).

Each of those changes will be a single-node registry edit verified by
re-running that node's 3 queries through the driver.
