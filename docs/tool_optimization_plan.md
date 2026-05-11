# PDS live-finder tool optimization plan

## Goal

Make the 5 MCP tools general and efficient enough that a competent caller can solve any gold-dataset query in **≤ 6 tool calls** without any node-specific branching inside the tools themselves. Per-node knowledge stays in the registry's text fields only.

## Scope

**6 nodes in scope:** `atm`, `geo`, `ppi`, `lroc`, `img`, `rms` — 80 gold queries total in `data/pds_node_classification.xlsx` (atm 20, geo 19, ppi 16, rms 12, img 9, lroc 4).

**Discarded from this round:**
- `sbn` — 403 is a network constraint, not a tool issue; degraded-mode prompt already exists.
- `naif` — no gold queries to evaluate against.

**Out of scope (three separate items):**
1. Per-node prompt edits — `workflow_steps` / `abbreviations` / `missions` in `tools/node_registry.py`. User applies these later using phase-5 artifacts.
2. Changes to `run_eval.py` or `test_nodes.py` (test harness, not subject of optimization).
3. Node-specific code inside any tool body. No `if node == "xyz"` branches.

## Defaults

- **Sample size:** 3 gold queries per node = 18 queries in phase 1.
- **Worktree:** this one (`vigorous-joliot-247f6d`).
- **Artifact format:** markdown briefs with paste-ready Python string blocks for the registry.

## Phases

### Phase 1 — Friction baseline (manual trace, no code changes)

Pick 3 gold queries per node (18 total). For each, **I act as the agent myself** through a small driver script that calls only the 5 MCP tools. Record per query:

- The tool-call sequence I made
- HTTP fetch count (approximate cost)
- Where I got stuck, guessed, or back-tracked
- Whether the final path matches the gold `Expected Identifiers`

Reference material: `docs/pds_node_scraping_plan.md` per-node patterns + each node's current registry entry.

**Deliverable:** `docs/tool_friction_baseline.md` — table of `(query, n_calls, n_redundant_calls, friction notes, success?)` per query, grouped by node.

### Phase 2 — Diagnose cross-node patterns

From phase 1 traces, extract friction modes that affect **≥ 3 of the 6 nodes**. Single-node friction is a prompt issue, not a tool issue — it gets logged for phase 5, not addressed here.

Hypotheses I'll test (firm up after phase 1):

1. `list_dataset_dirs` returns many similar names with no ranking — every flat-list node (PPI, RMS, ATM PDS3, IMG sub-trees) hits this.
2. No cheap way to check "is dataset_id X reachable from path Y" without a full probe → wastes HTTP.
3. `probe_datasets` slimmed fields vary by PDS version — agent has to branch on `pds_version`.
4. PDS4 bundle detection (deciding when to call `inspect_collections`) currently relies on probe's `pds_version` hint, which is sometimes wrong.

**Deliverable:** ranked list of cross-node frictions. Each ranked by `nodes-benefited × friction-removed ÷ implementation-cost`.

### Phase 3 — Implement top 2–3 generic tool changes

Caps:
- ≤ 2 modifications to existing tools.
- ≤ 1 new tool, and only if phase 2 shows it shortens workflows on ≥ 3 nodes by ≥ 2 calls each.
- All changes additive / backward-compatible (won't conflict with in-flight prompt edits).
- Hard rule: no `if node == "xyz"` inside any tool body. Anything node-specific stays in `node_registry.py` text fields.

Likely shape (firm up after phase 2):

- `list_dataset_dirs`: extend with optional pagination, scoring, or depth=2 listing.
- `probe_datasets`: normalize the slimmed-field shape across PDS3/PDS4 so the agent doesn't branch on version.
- (Maybe new) `find_by_keyword(query, node, max_depth=2)`: one-shot keyword-driven search combining `list` + `probe` internally with ranked candidates — only if phase 2 justifies it.

**Deliverable:** one focused commit per tool change, each with a smoke check against 1–2 known gold queries.

### Phase 4 — Re-run the phase-1 manual traces

Same 18 queries, same driver script, same metrics. Compare against the phase-1 baseline.

**Success criteria:**

- Median tool calls per query drops by ≥ 30%.
- ≥ 80% of queries resolve to the gold `Expected Identifiers`.
- No regression: no query that worked in phase 1 fails in phase 4.

**Deliverable:** `docs/tool_friction_after.md` — same table format as the baseline plus a delta column.

### Phase 5 — Generate per-node prompt artifacts

Once tools are stable, run `test_nodes.py --queries 3` against the live agent to capture **how the agent uses the optimized tools**. From the traces, derive per-node artifacts.

For each of the 6 in-scope nodes:

- **Proposed `workflow_steps`** — one block, ≤ 8 numbered steps, citing actual tool-call patterns I observed working.
- **Proposed `abbreviations` additions** — mission/instrument cues that appeared in queries but weren't in the table (e.g. CRISM, OTES, JAD if they came up).
- **Proposed `missions` additions** — entries that were missing and would have helped.
- **Primary failure mode** — one-line note for queries that still didn't work.
- **Diff against current** — exactly what's changing relative to the live registry entry, so the user can scan the patch quickly.

**Deliverable:** 6 markdown files in `docs/node_optimization_briefs/` (`atm.md`, `geo.md`, `ppi.md`, `lroc.md`, `img.md`, `rms.md`). Each ≤ 1 page, with paste-ready Python string blocks.

## Success criteria for the whole plan

1. Tools are strictly more general (no node-specific branching inside tool code; lines of code per tool roughly unchanged or down).
2. Phase 4 hits the per-query metrics above.
3. Phase 5 artifacts are concrete enough that the user can update each node's prompt in under 15 minutes per node.

## Risks

- **Phase 2 may show no shared friction** — i.e. each node's pain is unique and only addressable in prompt. Acceptable outcome: phase 3 makes minimal changes, more effort goes into phase 5.
- **Over-engineering a new tool.** Hard cap at 1, and only if ≥ 3 nodes benefit by ≥ 2 calls each.
- **In-flight prompt edits** to `pds_finder.py` / `node_registry.py` may conflict with my work. Mitigation: all tool changes are additive; I don't touch the live workflow text in `node_registry.py`, only deliver proposals in `docs/`.

## Sequence and dependencies

```
Phase 1 (manual traces)
   ↓
Phase 2 (diagnose) ──── if no cross-node friction → skip 3 & 4, go to 5
   ↓
Phase 3 (implement)
   ↓
Phase 4 (re-trace) ──── if metrics not hit → return to phase 3 once
   ↓
Phase 5 (briefs)
```

Each phase produces a deliverable the user can review before the next phase starts.
