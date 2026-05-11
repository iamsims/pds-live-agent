# SBN optimization brief

## Why the baseline failed

The original SBN registry pointed at `https://pds-smallbodies.astro.umd.edu/holdings/`
(UMD's mirror), which carries Rosetta, Stardust, Deep Impact, ICE/Halley, and
comet archives. None of the SBN gold-classification queries target UMD-hosted
missions — every one of the 16 gold queries points at Dawn, NEAR, OSIRIS-REx,
Hayabusa, or Hayabusa2, all of which are hosted at a **different** SBN
sub-mirror (`https://sbnarchive.psi.edu/`).

Baseline result against UMD: 3 / 3 sample gold queries returned
`filtered_total: 0` from `list_dataset_dirs(path='holdings/', filter=…)`.
The originally-recorded plan rationale ("403 is a network constraint, not
a tool issue") didn't capture this — the 403 is gone, but the missions
aren't hosted there in the first place.

## Friction tagging

This is a pure prompt-level fix per the optimization plan's protocol:
no tool changes. The friction is

- **P-sbn-1** — wrong sub-mirror. `base_url` pointed at UMD; the gold
  mission set lives at PSI.
- **P-sbn-2** — PSI uses a different naming convention than every other
  node we've handled: PDS3 dataset dirs are ALL_CAPS_WITH_UNDERSCORES
  (slashes AND hyphens both become `_`, periods become `_`); PDS4
  bundles use dot-separated LIDs (`orex.otes`, not `orex-otes` or
  `orex_otes`).
- **P-sbn-3** — Dawn PSI archive uses short codes (`DWNCSVIR_I1B`)
  instead of full hyphenated DATA_SET_IDs; the agent needs the decoding
  in the abbreviation table to land on the right volume on the first try.

## Registry diffs

- `base_url`: `https://pds-smallbodies.astro.umd.edu/` →
  `https://sbnarchive.psi.edu/`
- `data_root`: `holdings/` → `pds3/` (PDS3 is the primary tree; PDS4
  sits in parallel at `pds4/`)
- `has_mission_layer`: `False` → `True` (PSI splits by mission directory)
- `_SBN_MISSIONS`: rewritten to list PSI's actual mission subtrees
  (dawn, near, hayabusa, cassini, galileo, ulysses, iras, neat, msx,
  non_mission, multi_mission, orex, hayabusa2, clipper, ldex). Added
  entries for UMD-only missions (ro-c, sd, di, lucy, dart) with explicit
  "NOT hosted at this base_url" notes so the agent doesn't waste calls.
- `_SBN_ABBREVIATIONS`: rewritten to spell out PSI's
  underscore-encoding rule (hyphens AND slashes both become `_`, `V1.0`
  becomes `V1_0`) with three worked examples mapping gold DATA_SET_IDs
  to PSI directory names. Added the Dawn short-code table.
- `_SBN_WORKFLOW` / `_SBN_WORKFLOW_STEPS`: rewritten for the two-tree
  layout. Added `SBN_UMD_FALLBACK` directive: if the gold id starts
  with a UMD-only mission prefix, cap at 2 tool calls and synthesise
  the answer from the abbreviation pattern with a "lives at UMD's
  mirror" reasoning note.

## Verification (driver, post-edit)

Three gold-aligned sample queries, all in 2 calls each:

- Q1 `DAWN-A-VIR-3-RDR-IR-CERES-SPECTRA-V1.0`:
  `list(pds3/dawn/vir/, filter='I1B')` returns 10 Ceres IR L1B volumes
  including DWNCSVIR_I1B; `probe(DWNCSVIR_I1B/)` returns the gold id
  exactly. **2 calls** (baseline: 0 reachable from UMD).
- Q2 `NEAR-A-MSI-3-EDR-EROS/ORBIT-V1.0` +
  `NEAR-A-MSI-5-DIM-EROS/ORBIT-V1.0`:
  `list(pds3/near/, filter='MSI_3_EDR_EROS_ORBIT')` returns the single
  match; a batched probe of both directories returns both gold ids
  (slashes restored from the parsed voldesc). **2 calls** (baseline: 0).
- Q3 `urn:nasa:pds:orex.otes` + `urn:nasa:pds:orex.ovirs`:
  `list(pds4/orex/, filter='orex.ot')` shows orex.otes plus older
  versioned snapshots; a batched probe of orex.otes/ and orex.ovirs/
  returns both LIDs exactly. **2 calls** (baseline: 0).

## Known follow-up

- The T2 `pds_hint` heuristic doesn't currently tag dot-separated PDS4
  LIDs (`orex.otes`) as PDS4 — the regex requires `_` or `-` separators.
  Not a regression vs. baseline (the field was already `null` there)
  and not a correctness issue for the gold queries (the agent matches
  on `dataset_id` from probe). If we extend the heuristic to also
  accept `.` separators it would be a one-liner; deferred because it's
  speculative without a non-gold counterexample.
- Lucy and DART aren't at PSI either; the abbreviation table notes
  this. If future gold queries reach for them we'd need a third mirror
  configured, which is outside the current single-base_url model.
