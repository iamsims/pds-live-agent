# PDS Node Scraping Plan

Reference notes for how each PDS node's scraper finds bundles and collections, plus a survey of holdings/inventory pages available per node. Compiled from reading the 8 scrapers in `sde-data-agents/scripts/` and direct verification against live node URLs (where reachable).

**Bundle/collection match rule (universal across scrapers):**
`fname.startswith("bundle"|"collection") and fname.endswith(".xml"|".lblx")` — this matches both `bundle.xml` and `bundle_*.xml`, and likewise for collections.

---

## Per-Node Plan: Finding Bundles and Collections

### 1. ATM — `pds-atmospheres.nmsu.edu/PDS/data/`
**Verified:** `MROM_0001/` has `VOLDESC.CAT` + `DATA/`, `CATALOG/`, etc.

**Plan:**
1. Two roots: `/PDS/data/` (PDS3) and `/PDS/data/PDS4/` (PDS4-only). Skip `MCSDDRV1`.
2. **PDS3 path:** at each volume root, look for `voldesc.cat`. If found → record. Recurse into `data_*/` for `*.sfd` files.
3. **PDS4 path:** depth ≤ 2. Match `bundle*.xml` and `collection*.xml` at root. Recurse into `data*`, `browse`, `l2`, `l3` subdirs scanning for more `collection*.xml`.
4. Edge case: volumes with XML but no `data_*` folder are logged separately (`volumes_xml_no_data`).

---

### 2. GEO — `pds-geosciences.wustl.edu/<mission>/`
**Verified:** 24 hardcoded missions. `m2020/urn-nasa-pds-mars2020_mission/` → `bundle.xml`. `msl/.../mslapx_0xxx/` → mixed `VOLDESC.CAT` + `bundle_apxs_raw.xml` + `DATA/`.

**Plan:**
1. Iterate `MISSION_PATHS` (24 missions: `m2020`, `msl`, `mro`, `lro`, …).
2. For each mission, list datasets. Each dataset can be: pure PDS3, pure PDS4, or **hybrid** (both markers — handle both, don't short-circuit).
3. **Bundle detection:** `bundle*.xml` or `bundle*.lblx` at dataset root.
4. **Collection scan:** recurse subdirs (skip `document`, `index`, `catalog`, `checksums`) looking for `collection*.{xml,lblx}` and nested `bundle*.lblx`.
5. **PDS3 detection:** `voldesc.cat` or `voldesc.sfd` at volume root.
6. Depth limit: 2.

---

### 3. JPL IMG — `planetarydata.jpl.nasa.gov/img/data/`
**Verified:** Top level is missions (`cassini/`, `mariner6/`, `viking_orbiter/`…). `cassini/` then has `cassini_orbiter/`, `opus/`, `pds4/`, `public/` — deep nesting.

**Plan:**
1. List root → mission dirs. HEAD-check each link to skip external redirects.
2. Recurse depth ≤ 4. Skip: `checksums`, `document`, `index`, `catalog`, `extras`, `browse`, `software`, `errata`.
3. **Bundle detection:** `bundle*.xml`, `bundle*.lblx` at any traversed dir.
4. **Collection detection:** `collection*.xml`, `collection*.lblx`, nested `bundle*.lblx`.
5. **PDS3 detection:** `voldesc.cat`, `voldesc.sfd`, generic `*.sfd`.
6. Persist `.dircache.json` for resume; exclude `.tar.gz` and `_md5.txt`.

---

### 4. LROC — `pds.lroc.im-ldi.com/data/`
**Verified:** 3 fixed datasets. `LRO-L-LROC-2-EDR-V1.0/` has `bundle_lro-l-lroc-2-edr.xml` at root + `LROLRC_*` subcollections.

**Plan:**
1. Iterate 3 hardcoded `DATASET_PATHS`.
2. **Stage 1 (dataset root):** capture `bundle*.xml`/`bundle*.lblx`.
3. **Stage 2 (volume subdirs):** check each numbered subdir for `voldesc.cat`/`voldesc.sfd` (PDS3) AND/OR run `_scan_for_collections()` (PDS4).
4. Collection scan matches `collection*.{xml,lblx}` and nested `bundle*.lblx`.
5. Depth limit: 2. Skip `document`, `index`, `catalog`, `checksums`.

---

### 5. NAIF — two roots: `data/` (PDS3), `pds4/` (PDS4)
**Verified:** `lro-l-spice-6-v1.0/lrosp_1000/` has `voldesc.cat` + `data/`, `catalog/`, etc. — PDS3 lives **two levels deep** (mission → version dir).

**Plan:**
1. Run two separate phases over the two base URLs.
2. **PDS3 phase:** depth ≤ 6 (mission dirs nest deeply). At every level look for `voldesc.cat`, `data.xml`, and any `*.sfd`. Recurse even when nothing found.
3. **PDS4 phase:** match `bundle*.xml`/`bundle*.lblx` and `collection*.{xml,lblx}`.
4. **Version dedup (NAIF-only):** when multiple `collection_*_v###.xml` exist, pick highest `_v###`. Fall back to alphabetical.
5. Skip non-data dirs: `checksums`, `extras`, `browse`, `software`, `errata` (+ standard PDS4 skips).

---

### 6. PPI — `pds-ppi.igpp.ucla.edu/data/`
**Verified:** Flat ~767 entries. `cassini-caps-calibrated/` has `bundle_cassini_caps_calibrated_1.0.xml` at root + `data-els/`, `data-ibs/`, … subdirs.

**Plan:**
1. List `/data/` root → ~767 mixed PDS3/PDS4 entries (no mission layer).
2. For each entry, run priority cascade: `bundle*.xml` > `voldesc.cat`/`voldesc.sfd` > `data.xml` > `*.sfd` > `*.lblx`.
3. If PDS4 markers found, recurse depth ≤ 4 into `data-*/` and other non-skip subdirs collecting `collection*.{xml,lblx}` and nested `bundle*.lblx`.
4. Skip: `checksums`, `browse`, `software`, `errata`, `extras` (+ PDS4: `document`, `index`, `catalog`).
5. Persist `.dircache.json` for resume.

---

### 7. RMS — two roots: `holdings/volumes/` (PDS3), `pds4/bundles/` (PDS4)
**Could not verify directly — node 403s WebFetch.**

**Plan (from code only — verify when running):**
1. **PDS3 phase:** list `holdings/volumes/` → mission dirs → volume subdirs (one level). Look for `voldesc.cat`, `voldesc.sfd`, `data.xml`, generic `*.sfd`.
2. **PDS4 phase:** list `pds4/bundles/` → bundle dirs (no intermediate level). Match `bundle*.{xml,lblx}` and `collection*.{xml,lblx}` at bundle root, then scan subdirs for nested collections.
3. Limited recursion (1 level inside volume/bundle).
4. **Suggested verification step:** when running scraper, log a sample of 3 volumes + 3 bundles to validate the file-name patterns hold; the code's assumption is shared with other nodes so risk is low.

---

### 8. SBN — `pds-smallbodies.astro.umd.edu/holdings/`
**Could not verify holdings directly (403), but `data_other/` works and confirms `.shtml` is real (`HST.shtml`, `Spitzer.shtml`).**

**Plan:**
1. List `holdings/` → flat dataset dirs.
2. **Per-dataset cascade:**
   - `bundle*.xml` at root → record (PDS4 bundle).
   - `voldesc.cat` at root → record (PDS3 volume).
   - `*.lblx` at root → record (PDS3 lblx variant — SBN-specific).
   - If none found → look one subdir level for `collection*.xml` or **exact** `collection.lblx` (skip `support/`).
   - **Final fallback:** parse `dataset.shtml` (SBN's HTML descriptor — unique to this node).
3. No deep recursion; no version dedup.

---

## Cross-cutting recommendations

- **Single-pattern unification:** all scrapers share `startswith("bundle")` + `endswith(".xml"/".lblx")`. Could be hoisted to a shared helper (currently duplicated 8×).
- **Verify RMS + SBN samples** when actually running — they're the only nodes that couldn't be drilled into via WebFetch (bot blocking). The code assumes the same patterns as other nodes; worth logging the first few hits to confirm.
- **NAIF version dedup logic** is the only truly node-specific behavior worth testing carefully — the regex `_v(\d+)` could miss formats like `_V01` (uppercase) or `-v1` (dash).

---

## Per-Node Holdings / Inventory Pages

Survey of node-level inventory pages that could be used as alternative crawl seeds.

| Node | Has holdings page? | URL | Notes |
|---|---|---|---|
| **GEO** | ✅ Yes | `/dataserv/holdings.html` | ~400–500 entries by target/mission/instrument |
| **ATM** | ✅ Yes | `/data_and_services/atmospheres_data/catalog.htm` | ~300+ entries by planet; links use CGI `getdir.pl?&volume=<ID>` |
| **SBN** | ✅ Yes (3 views) | `/data_sb/by_mission.shtml`, `by_target.shtml`, `by_datatype.shtml` | ~60+ missions; links: `/data_sb/missions/<mission>/index.shtml` |
| **NAIF** | ✅ Yes | `/naif/data.html` | 3 SPICE-kernel categories (Archived / Operational / Generic) |
| **PPI** | ❌ No | Search portal only at `/search/default.jsp` | Crawl `/data/` directly |
| **JPL IMG** | ❌ No | Apache directory at `/img/data/` | No HTML inventory |
| **LROC** | ❌ No | Data portal `data.im-ldi.com/mds`, PDS at `/data/` | No HTML inventory |
| **RMS** | ❓ Could not verify | Multiple paths 403'd | Likely has one but bot-blocked |

**Caveats on holdings pages:**
- All are hand-curated HTML — prone to staleness vs the live filesystem.
- They link to **landing pages** (`apxs.htm`) or directory roots, not directly to `voldesc.cat`/`bundle*.xml` — still requires the directory crawl to extract content.
- SBN's inventory is explicitly described as "selective rather than universal."
- **No standard format** across nodes (`.html`, `.htm`, `.shtml`, CGI scripts).

**How to use:** treat holdings pages as a **cross-check / hint**, not a source of truth. Flag anything in one source but not the other to catch crawler gaps and inventory drift.
