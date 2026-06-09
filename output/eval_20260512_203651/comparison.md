# Eval Comparison: Live vs Catalog

**Run:** `eval_20260512_203651`
**Model:** openai:gpt-5.2 | **Effort:** high | **Queries:** 96 | **Concurrency:** 3 | **Wall-clock:** 15,694s

---

## Experiment setup

### Gold dataset

96 natural-language research questions derived from published planetary science papers. Each query is paired with expected PDS dataset identifiers (PDS3 `dataset_id`s or PDS4 bundle/collection LIDs). Columns: `Paper` (citation), `Query` (research question), `Expected Identifiers`.

Node distribution in this run: GEO 35, ATM 22, SBN 16, PPI 15, RMS 4, IMG 1, LROC 1.

### Approach A — Live (HTTP directory-walking)

Two-stage architecture with two separate MCP servers:

**Stage 1 — Directory walking** via [`fuzzy-aquamarine-swordtail.fastmcp.app/mcp`](https://fuzzy-aquamarine-swordtail.fastmcp.app/mcp) (streamable HTTP):

1. **Router agent** (tool-less) classifies the query to a primary PDS node
2. **Worker agent** navigates the node's archive tree with 5 tools:
   - `pds_list_missions` — enumerate mission directories at the node
   - `pds_list_dataset_dirs` — list subdirectories under a path
   - `pds_probe_datasets` — batch-probe up to 20 paths for PDS labels
   - `pds_inspect_collections` — scan PDS4 bundle subdirs for collections
   - `pds_resolve_volume` — handle numbered volume siblings (e.g. `COISS_2xxx`)

**Stage 2 — Node-specific faceted APIs** via [`natural-bronze-stingray.fastmcp.app/mcp`](https://natural-bronze-stingray.fastmcp.app/mcp) (streamable HTTP):

After Stage 1 identifies candidates, the worker gets per-node tools filtered by the routed node:

| Node | Allowed Stage 2 tools |
|---|---|
| GEO | `ode_search_products_tool`, `ode_count_products_tool`, `ode_list_instruments_tool`, `ode_list_feature_classes_tool`, `ode_list_feature_names_tool`, `ode_get_feature_bounds_tool` |
| IMG | `img_search_tool`, `img_get_facets_tool`, `img_get_product_tool`, `img_count_tool` |
| RMS | `opus_search_tool`, `opus_count_tool`, `opus_get_metadata_tool`, `opus_get_files_tool` |
| SBN | `sbn_search_object_tool`, `sbn_search_coordinates_tool`, `sbn_list_sources_tool` |
| PPI, ATM, NAIF, LROC | PDS4 Registry fallback: `pds4search_bundles_tool`, `pds4search_collections_tool`, `pds4search_products_tool`, `pds4search_investigations_tool`, `pds4search_instruments_tool`, `pds4search_instrument_hosts_tool`, `pds4search_targets_tool`, `pds4get_product_tool`, `pds4crawl_context_product_tool` |

### Approach B — Catalog (pre-scraped search index)

This is the same approach currently deployed in the **alpha version (akd-labs)**, using the same prompt and MCP tools.

Single-stage, no routing. One unified agent via [`natural-bronze-stingray.fastmcp.app/mcp`](https://natural-bronze-stingray.fastmcp.app/mcp) (streamable HTTP) with access to all 24 tools at once:

**Catalog-specific tools (5):**
- `pds_catalog_search_tool` — text + structured filter search across the entire pre-scraped PDS catalog
- `pds_catalog_get_dataset_tool` — exact lookup by dataset_id
- `pds_catalog_list_missions_tool` — distinct mission names with counts
- `pds_catalog_list_targets_tool` — distinct target bodies with counts
- `pds_catalog_stats_tool` — totals, per-node, per-version, per-type aggregates

**Plus all node-specific faceted APIs (19):**
ODE (6), IMG (4), OPUS (4), SBN (3), PDS4 Registry (9) — same tools as live Stage 2, but all available simultaneously without node-based filtering.

### Scoring

A query is **matched** using **version-agnostic** comparison: the `-Vx.y` (PDS3) or `::x.y` (PDS4) version suffix is stripped from both the expected and candidate dataset IDs, then the base IDs must match exactly. This is the appropriate metric because gold expected IDs reference the version from the paper's publication date, but live archives may host a newer version — finding the correct dataset with a different version is a correct answer. Bundle-vs-collection granularity differences do not count as a match.

---

## Performance summary

| Metric | Live | Catalog |
|---|---|---|
| **Recall** | **50.0%** (48/96) | 33.3% (32/96) |
| Avg tool calls / query | **16.2** | 25.9 |
| Avg tokens / query | **252K** | 916K |
| Avg candidates returned / query | 5.3 | 6.6 |
| Avg time / query (s) | **296** | 302 |

Live achieves **+16.7pp higher recall** while using **60% fewer tool calls**, **3.6x fewer tokens**, and returning **fewer but more targeted candidates** per query. Query latency is roughly comparable despite the live HTTP overhead because live avoids the token bloat that slows catalog's LLM turns.

### Per-query distribution

| Metric | Stat | Live | Catalog |
|---|---|---|---|
| **Time (s)** | Mean | 296 | 302 |
| | Median | **189** | 252 |
| | P25–P75 | 119–410 | 164–365 |
| | Min–Max | 33–1,512 | 82–1,095 |
| **Tool calls** | Mean | **16.2** | 25.9 |
| | Median | **14** | 24 |
| | P25–P75 | 9–22 | 18–33 |
| | Min–Max | 3–51 | 0–69 |
| **Tokens (K)** | Mean | **252** | 916 |
| | Median | **192** | 525 |
| | P25–P75 | 109–340 | 307–1,035 |
| | Min–Max | 32–1,398 | 89–6,458 |
| **Candidates** | Mean | 5.3 | 6.6 |
| | Median | 5 | 6 |
| | P25–P75 | 3–7 | 5–8 |
| | Min–Max | 1–16 | 0–12 |

Live has a lower median than mean across all metrics, indicating a right-skewed distribution — most queries are efficient, with a long tail of harder ones. Catalog's token distribution is especially heavy-tailed (median 525K vs mean 916K; max 6.5M), driven by queries where the agent spirals through repeated `pds_catalog_search_tool` calls.

## Detailed head-to-head

| Metric | Live | Catalog | Winner |
|---|---|---|---|
| **Match rate** | **50.0%** (48/96) | 33.3% (32/96) | Live (+16.7pp) |
| Errors | **0** | 3 | Live |
| Wall-clock time | **7,527s** | 8,137s | Live (8% faster) |
| Total tokens | **24.2M** | **87.9M** | Live (3.6x cheaper) |
| LLM requests | 1,412 | 1,534 | Live (8% fewer) |

### Conclusion

**Live wins decisively** — 50.0% vs 33.3% (+16.7pp), with 3.6x fewer tokens and 37% fewer tool calls per query. The catalog approach burns ~64M more input tokens — mostly from repeated `pds_catalog_search_tool` calls (1,682 calls) — without converting that extra work into matches.

### Note on strict (exact version) matching

With exact version matching (no suffix stripping), the rates are Live 39.6% (38/96) vs Catalog 29.2% (28/96). The gap is narrower (+10.4pp) because strict matching penalises live for returning newer versions from the live archive (e.g. finding `CO-S-UVIS-2-SSB-V1.4` when the gold expects `V1.0`). Version-agnostic is the fairer metric since the agent's job is to find the right dataset, not to guess which historical version the paper cited.

Note: the original eval harness reported 45/96 strict for live using bidirectional substring matching, which inadvertently credited 7 bundle-vs-collection partial matches (e.g. `urn:nasa:pds:orex.otes` substring-matching `urn:nasa:pds:orex.otes:data_calibrated`). The 38/96 figure above uses exact base-ID matching, which is the correct strict metric.

Version mismatches rescued by version-agnostic scoring:

**Live (+10 queries):**

| Row | Expected | Found |
|---|---|---|
| 13 | `CO-S-UVIS-2-SSB-V1.0` | `CO-S-UVIS-2-SSB-V1.4` |
| 16 | `MRO-M-MCS-5-DDR-V6.2` | `MRO-M-MCS-5-DDR-V1.0` |
| 18 | `JNO-E/J/SS-WAV-3-CDR-BSTFULL-V1.0` | `JNO-E/J/SS-WAV-3-CDR-BSTFULL-V2.0` |
| 26 | `CO-S-UVIS-2-SSB-V1.0` | `CO-S-UVIS-2-SSB-V1.4` |
| 38 | `CO-S-UVIS-2-SPEC-V1.2` | `CO-S-UVIS-2-SPEC-V1.4` |
| 49 | `MRO-M-MCS-5-DDR-V6.2` | `MRO-M-MCS-5-DDR-V1.0` |
| 50 | `CO-S-UVIS-2-SPEC-V1.2` | `CO-S-UVIS-2-SPEC-V1.5` |
| 62 | `CO-S-UVIS-2-SSB-V1.0` | `CO-S-UVIS-2-SSB-V1.2` |
| 87 | `CO-S-CIRS-2/3/4-TSDR-V3.2` | `CO-S-CIRS-2/3/4-TSDR-V4.0` |
| 93 | `CO-S-UVIS-2-SPEC-V1.2` | `CO-S-UVIS-2-SPEC-V1.5` |

**Catalog (+4 queries):**

| Row | Expected | Found |
|---|---|---|
| 50 | `CO-S-UVIS-2-SPEC-V1.2` | `CO-S-UVIS-2-SPEC-V1.5` |
| 59 | `CO-S-CIRS-2/3/4-TSDR-V3.2` | `CO-S-CIRS-2/3/4-TSDR-V4.0` |
| 62 | `CO-S-UVIS-2-SSB-V1.0` | `CO-S-UVIS-2-SSB-V1.2` |
| 90 | `CO-S-CIRS-2/3/4-TSDR-V3.2` | `CO-S-CIRS-2/3/4-TSDR-V4.0` |

## Per-node breakdown (live mode)

| Node | Queries | Matched | Rate |
|---|---|---|---|
| **SBN** | 16 | 14 | **87.5%** |
| RMS | 4 | 2 | 50.0% |
| PPI | 15 | 7 | 46.7% |
| ATM | 22 | 10 | 45.5% |
| **GEO** | 35 | 11 | **31.4%** |
| IMG | 1 | 0 | 0.0% |
| LROC | 1 | 1 | 100% |

**GEO is the biggest opportunity for improvement** — it has the most queries (35) but the lowest match rate among heavily-tested nodes (31.4%). SBN is the standout performer at 87.5%. ATM and PPI are middling at ~45-47%.

## Tool usage patterns

### Live

Relies on the core directory-crawling tools:

| Tool | Calls |
|---|---|
| pds_list_dataset_dirs | 612 |
| pds_probe_datasets | 377 |
| pds_inspect_collections | 250 |
| final_result | 96 |
| pds_list_missions | 50 |
| pds_resolve_volume | 35 |
| pds4search_bundles_tool | 25 |
| pds4search_products_tool | 23 |
| ode_list_instruments_tool | 22 |
| ode_count_products_tool | 20 |
| ode_search_products_tool | 16 |
| ode_get_feature_bounds_tool | 10 |
| pds4search_instruments_tool | 5 |
| ode_list_feature_classes_tool | 3 |
| pds4search_targets_tool | 3 |
| pds4get_product_tool | 3 |
| opus_get_metadata_tool | 3 |
| opus_search_tool | 2 |

### Catalog

Hammers the catalog search API without converting breadth into accuracy:

| Tool | Calls |
|---|---|
| pds_catalog_search_tool | 1,682 |
| pds4search_bundles_tool | 188 |
| pds_catalog_get_dataset_tool | 178 |
| final_result | 93 |
| pds4search_instruments_tool | 64 |
| pds4search_products_tool | 61 |
| pds4search_collections_tool | 46 |
| pds4search_targets_tool | 32 |
| ode_list_instruments_tool | 22 |
| ode_search_products_tool | 20 |
| pds4search_investigations_tool | 18 |
| pds4get_product_tool | 16 |
| opus_search_tool | 14 |
| opus_get_metadata_tool | 11 |
| ode_get_feature_bounds_tool | 10 |
| img_get_facets_tool | 8 |
| pds4search_instrument_hosts_tool | 5 |
| pds_catalog_list_missions_tool | 4 |
| img_count_tool | 4 |
| pds_catalog_stats_tool | 3 |
| ode_list_feature_classes_tool | 3 |
| pds_catalog_list_targets_tool | 2 |
| ode_count_products_tool | 2 |
| opus_count_tool | 2 |
| opus_get_files_tool | 1 |
