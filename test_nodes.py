"""Per-node smoke test — run N queries against each PDS node in live mode.

Verifies that the live finder works for each of the 8 supported nodes
(geo, ppi, lroc, img, rms, sbn, atm, naif) and produces traces useful for
iterating on per-node prompt/workflow optimization. Defaults to 2 queries
per node, all 8 nodes, live mode only.

Usage:
    .venv/bin/python pydantic_code/test_nodes.py                 # all 8 nodes
    .venv/bin/python pydantic_code/test_nodes.py --node img      # one node
    .venv/bin/python pydantic_code/test_nodes.py --node img,naif # subset
    .venv/bin/python pydantic_code/test_nodes.py --queries 3     # 3 per node
    .venv/bin/python pydantic_code/test_nodes.py --print-tool-calls

Output:
    output/test_per_node_<timestamp>/
        summary.json                     — per-node aggregate stats
        <node>/
            results.xlsx                 — gold sheet + live result columns
            traces/live/<idx>_trace.json — full message trace per query

When iterating on a single node's workflow:
    1. Edit that node's entry in pydantic_code/tools/node_registry.py.
    2. Re-run with --node <id>.
    3. Diff the new traces against the previous run to see what changed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import openpyxl
from dotenv import load_dotenv

load_dotenv()

from pydantic_code.run_eval import (  # noqa: E402
    _extract_tool_calls,
    _format_candidates,
    _is_error_trace,
    _print_tool_calls,
    _run_query,
    _serialize,
    _write_results_xlsx,
)
from pydantic_code.tools.node_registry import SUPPORTED_NODES  # noqa: E402

# Use pds_node_classification.xlsx directly — it is the canonical query set
# (a strict superset of gold_standard_bundle_collection_dataset_level.xlsx)
# and uses the corrected per-node taxonomy. We bypass run_eval's load_gold_queries
# because that one routes geo/img/atm/sbn through the GEO-curated gold-standard
# file which uses a different (less granular) node tagging.
_CLASSIFICATION_FILE = (
    Path(__file__).resolve().parent
    / "data"
    / "pds_node_classification.xlsx"
)
# Column indices in the classification sheet (0-based, values_only=True)
_NC_PAPER_SHORT = 0
_NC_PAPER = 1
_NC_QUERY = 2
_NC_EXPECTED_IDS = 3
_NC_PRIMARY_NODE = 4


def load_queries_for_node(node: str, limit: int | None = None) -> list[dict]:
    """Load queries for a node from pds_node_classification.xlsx.

    Filters on the Primary PDS Node column (case-insensitive). Returns dicts
    with the same keys run_eval expects so the rest of the pipeline is unchanged.
    """
    wb = openpyxl.load_workbook(_CLASSIFICATION_FILE, read_only=True)
    ws = wb["PDS Node Classification"]
    rows: list[dict] = []
    target = node.strip().lower()
    for row in ws.iter_rows(min_row=2, values_only=True):
        primary = str(row[_NC_PRIMARY_NODE] or "").strip().lower()
        if primary != target:
            continue
        rows.append(
            {
                "rank": None,
                "paper_short": row[_NC_PAPER_SHORT],
                "rationale": None,
                "paper": row[_NC_PAPER],
                "query": row[_NC_QUERY],
                "expected_ids": row[_NC_EXPECTED_IDS],
                "node": row[_NC_PRIMARY_NODE],
            }
        )
        if limit and len(rows) >= limit:
            break
    wb.close()
    return rows


# ---------------------------------------------------------------------------
# Per-node runner
# ---------------------------------------------------------------------------


async def _run_node(
    node: str,
    n_queries: int,
    output_dir: Path,
    concurrency: int,
    print_tool_calls: bool,
) -> dict:
    """Run live finder for `n_queries` queries against one node."""
    queries = load_queries_for_node(node, limit=n_queries)

    print(f"\n=== {node.upper()} ===")
    if not queries:
        print(f"  (no queries found in gold data for node={node!r} — skipping)")
        return {"node": node, "queries": 0, "elapsed_s": 0.0, "results": []}

    print(f"  {len(queries)} queries, concurrency={concurrency}")
    node_dir = output_dir / node
    traces_dir = node_dir / "traces" / "live"
    traces_dir.mkdir(parents=True, exist_ok=True)

    sem = asyncio.Semaphore(concurrency)
    started = time.monotonic()

    async def _process(idx: int, row: dict) -> dict:
        async with sem:
            query = row["query"]
            print(f"  [{idx + 1}/{len(queries)}] {str(query)[:90]}")
            try:
                output, trace = await _run_query("live", query, node=node)
                tool_calls = (
                    _extract_tool_calls(trace)
                    if trace and not _is_error_trace(trace)
                    else []
                )
                n_cands = len(output.candidates)
                print(f"      → {n_cands} candidates, {len(tool_calls)} tool calls")
                if print_tool_calls and tool_calls:
                    _print_tool_calls(tool_calls, f"{node}/{idx + 1}")
                failed = False
            except Exception as e:
                print(f"      → FAILED: {type(e).__name__}: {e}")
                output = None
                tool_calls = []
                trace = [{"error": f"{type(e).__name__}: {e}"}]
                failed = True

            trace_data = {
                "query": query,
                "row": row,
                "tool_calls": tool_calls,
                "full_trace": (
                    [_serialize(m) for m in trace]
                    if not _is_error_trace(trace)
                    else trace
                ),
            }
            (traces_dir / f"{idx:03d}_trace.json").write_text(
                json.dumps(trace_data, indent=2, default=str)
            )

            return {
                **row,
                "_idx": idx,
                "live_ids": "\n".join(
                    c.dataset_id
                    for c in (output.candidates if output else [])
                    if c.dataset_id
                ),
                "live_candidates": _format_candidates(output) if output else "ERROR",
                "live_summary": output.summary if output else "ERROR",
                # The shared xlsx writer expects catalog_* keys too — leave blank.
                "catalog_ids": "",
                "catalog_candidates": "",
                "catalog_summary": "",
                "_n_candidates": len(output.candidates) if output else 0,
                "_n_tool_calls": len(tool_calls),
                "_failed": failed,
            }

    raw = await asyncio.gather(*[_process(i, r) for i, r in enumerate(queries)])
    results = sorted(raw, key=lambda r: r["_idx"])
    elapsed = time.monotonic() - started

    # Strip private fields before writing xlsx
    public_results = [
        {k: v for k, v in r.items() if not k.startswith("_")} for r in results
    ]
    _write_results_xlsx(node_dir / "results.xlsx", public_results)

    return {
        "node": node,
        "queries": len(queries),
        "elapsed_s": round(elapsed, 1),
        "results": [
            {
                "query": str(r["query"])[:90],
                "n_candidates": r["_n_candidates"],
                "n_tool_calls": r["_n_tool_calls"],
                "failed": r["_failed"],
            }
            for r in results
        ],
    }


# ---------------------------------------------------------------------------
# Top-level orchestration + summary
# ---------------------------------------------------------------------------


async def main_async(
    nodes: list[str],
    n_queries: int,
    concurrency: int,
    print_tool_calls: bool,
) -> None:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_dir = (
        Path(__file__).resolve().parent / "output" / f"test_per_node_{timestamp}"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Output dir: {output_dir}")

    # Sequential across nodes (clean logs); concurrent within a node.
    summaries: list[dict] = []
    for node in nodes:
        summary = await _run_node(
            node, n_queries, output_dir, concurrency, print_tool_calls
        )
        summaries.append(summary)

    # ---- Final summary table ----
    print("\n" + "=" * 78)
    print(
        f"{'Node':<6} {'Queries':>8} {'Avg cands':>10} {'Avg tools':>10} "
        f"{'Failed':>7} {'Elapsed':>8}"
    )
    print("-" * 78)
    for s in summaries:
        if not s["results"]:
            print(
                f"{s['node']:<6} {'-':>8} {'-':>10} {'-':>10} {'-':>7} "
                f"{'-':>8}  (no queries)"
            )
            continue
        avg_cands = sum(r["n_candidates"] for r in s["results"]) / len(s["results"])
        avg_tools = sum(r["n_tool_calls"] for r in s["results"]) / len(s["results"])
        n_failed = sum(1 for r in s["results"] if r["failed"])
        print(
            f"{s['node']:<6} {s['queries']:>8} {avg_cands:>10.1f} "
            f"{avg_tools:>10.1f} {n_failed:>7} {s['elapsed_s']:>7.1f}s"
        )
    print("=" * 78)

    (output_dir / "summary.json").write_text(
        json.dumps(summaries, indent=2, default=str)
    )
    print(f"\nDetailed traces & per-node results.xlsx in: {output_dir}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Smoke-test the live finder for each PDS node",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--node",
        default="all",
        help=(
            "Comma-separated list of node IDs to test, or 'all' (default). "
            f"Supported: {','.join(SUPPORTED_NODES)}"
        ),
    )
    parser.add_argument(
        "--queries",
        type=int,
        default=2,
        help="Number of gold queries to run per node (default: 2)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=2,
        help="Max concurrent queries within one node (default: 2)",
    )
    parser.add_argument(
        "--print-tool-calls",
        action="store_true",
        help="Print every tool call inline (verbose; default off)",
    )
    args = parser.parse_args()

    if args.node == "all":
        nodes = list(SUPPORTED_NODES)
    else:
        nodes = [n.strip().lower() for n in args.node.split(",") if n.strip()]
        unknown = [n for n in nodes if n not in SUPPORTED_NODES]
        if unknown:
            parser.error(
                f"Unknown nodes: {unknown}. Supported: {list(SUPPORTED_NODES)}"
            )

    asyncio.run(
        main_async(
            nodes=nodes,
            n_queries=args.queries,
            concurrency=args.concurrency,
            print_tool_calls=args.print_tool_calls,
        )
    )


if __name__ == "__main__":
    main()
