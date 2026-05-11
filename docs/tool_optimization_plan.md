# PDS live-finder tool + prompt optimization plan

## Goal

Make the 5 MCP tools general and efficient, AND tune each node's per-node
prompt fields (`workflow_steps`, `abbreviations`, `missions`), such that any
gold-dataset query can be solved in **≤ 6 tool calls** without any
node-specific branching inside the tools themselves.

## Operating mode — self-development, no LLM

- **No pydantic-ai Agent.** No OpenAI key. `test_nodes.py` is NOT used here
  (it runs the live agent).
- **I am the orchestrator.** I invoke tools directly through a small Python
  driver that imports the 5 tool functions and prints their outputs.
- **One tool call at a time.** I read each output, decide the next call,
  log the trace. Each query ends when I find a path matching the gold
  `Expected Identifiers` or I exceed an 8-call budget.
- **Tools only.** No WebFetch, no other HTTP, no `grep` against the live
  nodes. The only HTTP comes from inside the 5 tool functions.

## Scope

**6 nodes in scope:** `atm`, `geo`, `ppi`, `lroc`, `img`, `rms` — 80 gold
queries total in `data/pds_node_classification.xlsx` (atm 20, geo 19,
ppi 16, rms 12, img 9, lroc 4).

**Discarded:**
- `sbn` — 403 is a network constraint, not a tool issue.
- `naif` — no gold queries to evaluate against.

**In scope:**
1. Tool code in `tools/` (generic improvements only).
2. **Per-node fields in `tools/node_registry.py`** — `workflow_steps`,
   `abbreviations`, `missions`. Editing these IS now part of the work.
3. Artifacts under `docs/` (friction logs, diffs) so the work is reviewable.

**Out of scope:**
1. Changes to `run_eval.py` or `test_nodes.py` (test harness).
2. Node-specific code inside any tool body. No `if node == "xyz"`. All
   node nuance stays in the registry's text fields.
3. The general prompt builder `_build_single_node_prompt` and the
   multi-node prompt in `live_finder/pds_finder.py` — those are the
   universal scaffolding and remain off-limits per `CLAUDE.md`.

## Defaults

- **Sample size:** 3 gold queries per node = 18 queries in phase 1.
- **Worktree:** this one (`vigorous-joliot-247f6d`).
- **Driver:** new file `scripts/orchestrator_driver.py` (created in phase 1,
  not committed to main; lives under a path I can add to `.gitignore` if
  needed).

## Phases

### Phase 1 — Friction baseline (I run the tools myself)

Pick 3 gold queries per node (18 total). Build the orchestrator driver
that imports `pds_list_missions`, `pds_list_dataset_dirs`,
`pds_probe_datasets`, `pds_inspect_collections`, `pds_select_node` and
calls them inline (no MCP transport).

For each query I record:

- Tool-call sequence I made (with the exact arguments)
- HTTP fetch count (approximate)
- Where I got stuck, guessed, or back-tracked
- Whether the final path matches the gold `Expected Identifiers`
- Friction notes (what I wished the tool had returned)

**Deliverable:** `docs/tool_friction_baseline.md` — table of
`(node, query, n_calls, success?, friction notes)` per query.

### Phase 2 — Diagnose cross-node patterns

From phase-1 traces, classify each piece of friction as:

- **Tool-level** (a generic improvement helps ≥ 3 of the 6 nodes) →
  goes to phase 3.
- **Prompt-level** (single-node only, or "I needed a hint I could have
  gotten from a richer abbreviation table") → goes to phase 5.

**Deliverable:** ranked list with each friction tagged `tool` or `prompt`,
plus the proposed fix.

### Phase 3 — Implement top 2–3 generic tool changes

Caps:
- ≤ 2 modifications to existing tools.
- ≤ 1 new tool, and only if phase 2 shows it helps ≥ 3 nodes save
  ≥ 2 calls each.
- All changes additive / backward-compatible.
- No `if node == "xyz"` inside any tool body.

**Deliverable:** one focused commit per tool change.

### Phase 4 — Re-trace with the new tools

Same 18 queries, same driver, same metrics. Compare against baseline.

**Success criteria:**

- Median tool calls per query drops by ≥ 30%.
- ≥ 80% of queries resolve to the gold `Expected Identifiers`.
- No regression: no query that worked in phase 1 fails in phase 4.

**Deliverable:** `docs/tool_friction_after.md` — same table format plus
a delta column.

### Phase 5 — Edit per-node prompt fields and re-verify

For each of the 6 in-scope nodes, edit `tools/node_registry.py`:

- **`workflow_steps`** — rewrite the numbered plan to cite tool-call
  patterns I observed working in phase 4, including the new tools.
- **`abbreviations`** — add mission/instrument cues that appeared in
  gold queries but weren't in the table (e.g. instrument acronyms I
  had to mentally translate).
- **`missions`** — add entries that were missing and would have helped.

After each node's edit, **re-run that node's 3 queries through the
driver** to verify the new `workflow_steps` actually maps to a working
trace. If it doesn't, fix the prompt before moving on.

Hard constraint: I never touch `_build_single_node_prompt` or the
multi-node prompt. Per-node fields only.

**Deliverable:** one focused commit per node (or one bundled commit
if changes are tiny), plus `docs/node_optimization_briefs/<node>.md`
summarising the diff and reasoning per node for review.

## Success criteria for the whole plan

1. Tools strictly more general (no node-specific branching; lines of code
   per tool roughly unchanged or down).
2. Phase 4 hits the per-query metrics.
3. Phase 5 leaves the registry with per-node `workflow_steps` that I've
   verified end-to-end against gold queries — not just plausible prose.

## Risks

- **Phase 2 may show no shared tool friction** — all pain is per-node.
  Acceptable: phase 3 makes minimal changes, more effort flows to phase 5.
- **Over-engineering a new tool.** Hard cap at 1, justified by ≥ 3 nodes
  saving ≥ 2 calls.
- **The "I'm the orchestrator" assumption.** A real LLM agent may struggle
  with things I find easy (and vice-versa). To partially mitigate, I write
  the `workflow_steps` from the LLM's perspective: include the exact
  decision points (e.g. "if results contain X, do Y") rather than just
  the actions I took.
- **In-flight edits to live_finder/pds_finder.py or node_registry.py top
  matter.** Mitigation: all my tool changes are additive; my registry
  edits are per-node, leaving the dataclass and other nodes untouched.

## Sequence and dependencies

```
Phase 1 (manual traces with driver)
   ↓
Phase 2 (diagnose, classify each friction as tool vs prompt)
   ↓
Phase 3 (implement generic tool changes)  ─── if no cross-node friction, skip
   ↓
Phase 4 (re-trace, measure delta)
   ↓
Phase 5 (per-node prompt edits + verify each node end-to-end)
```

Each phase produces a deliverable the user can review before the next phase.
