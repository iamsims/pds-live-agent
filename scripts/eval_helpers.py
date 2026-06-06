"""Shared helpers for eval scripts — trace extraction, match checking, usage normalization."""

from __future__ import annotations

import json
from dataclasses import asdict

from pydantic_code.finder import FindDatasetOutput, build_finder


# ---------------------------------------------------------------------------
# Trace serializer
# ---------------------------------------------------------------------------


def serialize(obj):
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if hasattr(obj, "__dataclass_fields__"):
        return asdict(obj)
    return str(obj)


# ---------------------------------------------------------------------------
# Usage normalization
# ---------------------------------------------------------------------------

_USAGE_KEYS = (
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
    "total_tokens",
    "requests",
)


def usage_to_dict(usage) -> dict:
    """Normalize a pydantic-ai RunUsage into a flat dict."""
    if usage is None:
        return {k: 0 for k in _USAGE_KEYS}
    inp = getattr(usage, "input_tokens", 0) or 0
    out = getattr(usage, "output_tokens", 0) or 0
    return {
        "input_tokens": inp,
        "output_tokens": out,
        "cache_read_tokens": getattr(usage, "cache_read_tokens", 0) or 0,
        "cache_write_tokens": getattr(usage, "cache_write_tokens", 0) or 0,
        "total_tokens": inp + out,
        "requests": getattr(usage, "requests", 0) or 0,
    }


def sum_usage(*dicts: dict) -> dict:
    """Element-wise sum of usage dicts."""
    return {k: sum(int(d.get(k, 0) or 0) for d in dicts) for k in _USAGE_KEYS}


# ---------------------------------------------------------------------------
# Match checking
# ---------------------------------------------------------------------------


def check_match(
    candidates,
    expected_ids: list[str],
) -> tuple[bool, list[str], list[int]]:
    """Case-insensitive substring match between expected ids and each
    candidate's ``dataset_id`` or ``path``.
    """
    if not expected_ids:
        return False, [], []
    matched_exp: list[str] = []
    matched_idx: list[int] = []
    for i, c in enumerate(candidates):
        haystacks: list[str] = []
        for f in ("dataset_id", "path"):
            v = getattr(c, f, None)
            if v:
                haystacks.append(str(v).lower())
        if not haystacks:
            continue
        for e in expected_ids:
            el = e.lower()
            if any(el in h or h in el for h in haystacks):
                if e not in matched_exp:
                    matched_exp.append(e)
                if i not in matched_idx:
                    matched_idx.append(i)
    return bool(matched_exp), matched_exp, matched_idx


# ---------------------------------------------------------------------------
# Tool call extraction
# ---------------------------------------------------------------------------


def extract_tool_calls(messages) -> list[dict]:
    """Extract a flat list of tool calls from pydantic-ai message history."""
    returns: dict[str, str] = {}
    for msg in messages:
        if msg.kind == "request":
            for part in msg.parts:
                if part.part_kind == "tool-return":
                    returns[part.tool_call_id] = str(part.content)

    calls: list[dict] = []
    for msg in messages:
        if msg.kind == "response":
            for part in msg.parts:
                if part.part_kind == "tool-call":
                    calls.append(
                        {
                            "tool_name": part.tool_name,
                            "tool_input": part.args_as_dict(),
                            "tool_output": returns.get(part.tool_call_id, ""),
                        }
                    )
    return calls


def is_error_trace(trace: list) -> bool:
    """Return True if *trace* is an error sentinel (not real messages)."""
    return len(trace) == 1 and isinstance(trace[0], dict) and "error" in trace[0]


def print_tool_calls(tool_calls: list[dict], label: str) -> None:
    """Print tool calls in a clean, readable format."""
    if not tool_calls:
        print(f"  [{label}] No tool calls.")
        return
    for i, tc in enumerate(tool_calls, 1):
        print(f"  [{label}] Tool call {i}:")
        print(f"    tool_name:   {tc['tool_name']}")
        print(f"    tool_input:  {json.dumps(tc['tool_input'], indent=6)}")
        output_str = tc["tool_output"]
        if len(output_str) > 500:
            output_str = output_str[:500] + "... (truncated)"
        print(f"    tool_output: {output_str}")
        print()


# ---------------------------------------------------------------------------
# Single-query runner
# ---------------------------------------------------------------------------


async def run_query(kind: str, query: str, node: str | None = None, max_retries: int = 2) -> tuple[FindDatasetOutput, list]:
    """Run one query through a finder and return (output, raw_messages)."""
    for attempt in range(1, max_retries + 1):
        agent = build_finder(kind=kind, node=node)  # type: ignore[arg-type]
        async with agent:
            result = await agent.run(query)
        output = result.output
        messages = list(result.all_messages())
        if output.candidates or attempt == max_retries:
            return output, messages
        print(f"  [{kind}] Attempt {attempt}: 0 candidates, retrying...")
    return output, messages


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------


def format_candidates(output: FindDatasetOutput) -> str:
    """Format candidates into a readable multi-line string for an Excel cell."""
    if not output.candidates:
        return "(no candidates)"
    lines = []
    for i, c in enumerate(output.candidates, 1):
        parts = [f"{i}."]
        if c.dataset_id:
            parts.append(c.dataset_id)
        if c.title:
            parts.append(f'"{c.title}"')
        if c.path:
            parts.append(f"[path={c.path}]")
        if c.node:
            parts.append(f"(node={c.node})")
        if c.pds_version:
            parts.append(f"[{c.pds_version}]")
        lines.append(" ".join(parts))
    return "\n".join(lines)
