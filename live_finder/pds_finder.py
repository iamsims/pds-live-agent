"""PDS live finder agent — layered (Stage 1 + Stage 2) mode.

Supports GEO, PPI, LROC, IMG, RMS, SBN, ATM, and NAIF nodes. Every live worker
runs with two MCP toolsets:

* **Stage 1** — the 5 live HTTP directory-walking tools (``pds_list_missions``,
  ``pds_list_dataset_dirs``, ``pds_probe_datasets``, ``pds_inspect_collections``,
  ``pds_resolve_volume``), served by the hosted ``pds-node-mcp`` instance.
* **Stage 2** — deeper faceted-search tools (ODE / OPUS / IMG / SBN / PDS4),
  served by a second hosted FastMCP instance and filtered per node.

A tool-less router agent classifies the query to one node, then runs that
node's layered worker. See ``LiveFinder``, ``run_live_query``, and
``run_live_batch``.

The worker prompt is composed by ``_build_layered_prompt`` (Stage 1 scaffolding
from ``_build_stage1_prompt`` + a universal Stage 2 appendix).

NOTE: SBN's holdings index has historically been intermittent (HTTP 403). The
SBN workflow now tries the normal tools first; if list_dataset_dirs returns
status='forbidden', the agent falls back to the abbreviation table.
"""

from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from pydantic_code.live_finder.prompts import (
    ROUTER_SYSTEM_PROMPT,
    _build_layered_prompt,
)
from pydantic_code.live_finder.transports import (
    build_stage1_mcp,
    build_stage2_toolset_for,
)
from pydantic_code.tools.node_registry import SUPPORTED_NODES


# ---------------------------------------------------------------------------
# Router decision schema
# ---------------------------------------------------------------------------


class RouterDecision(BaseModel):
    """Structured output for the layered-mode router agent."""

    primary_node: str | None = Field(
        default=None,
        description=(
            "Primary PDS node id chosen for the query. One of "
            "'geo', 'ppi', 'lroc', 'img', 'rms', 'sbn', 'atm', 'naif'. "
            "Return null only when the query is too vague to map to a single "
            "node confidently (in which case confidence MUST be 'low')."
        ),
    )
    secondary_node: str | None = Field(
        default=None,
        description=(
            "Optional second-best node id from the same set, when the query "
            "plausibly overlaps two nodes. Leave null if only one node fits."
        ),
    )
    confidence: str = Field(
        description="One of 'high', 'medium', 'low'. Use 'low' for vague queries.",
    )
    reasoning: str = Field(
        description=(
            "One- or two-sentence explanation of which keywords or domain "
            "cues drove the choice."
        ),
    )


# ---------------------------------------------------------------------------
# Agent I/O schemas
# ---------------------------------------------------------------------------


class PDSLiveFindDatasetInput(BaseModel):
    """Input for the live finder agent."""

    query: str = Field(
        ...,
        description="Natural-language query, e.g. 'Mars 2020 PIXL data', 'Cassini magnetosphere'.",
    )


class PDSLiveDatasetCandidate(BaseModel):
    """One ranked dataset candidate found by the live agent."""

    path: str = Field(description="Path relative to the node's base URL")
    dataset_id: str | None = Field(
        default=None,
        description="Canonical PDS3 DATA_SET_ID or PDS4 logical_identifier",
    )
    title: str | None = Field(default=None, description="Dataset title from the label")
    pds_version: str | None = Field(default=None, description="'PDS3' or 'PDS4'")
    mission: str | None = Field(default=None, description="Top-level mission directory")
    node: str | None = Field(default=None, description="PDS node identifier")
    reasoning: str = Field(description="Why this dataset matches the query")


class PDSLiveFindDatasetOutput(BaseModel):
    """Output for the live finder agent."""

    candidates: list[PDSLiveDatasetCandidate] = Field(
        default_factory=list,
        description="Datasets that match the query, ordered most-relevant-first",
    )
    summary: str = Field(description="Short summary of the search and what was found")



# ---------------------------------------------------------------------------
# Live finder — router + per-node layered worker, with persistent transports
#
# Building one worker per query (a fresh `Agent` with its own toolsets) opens a
# new HTTP connection to BOTH hosted MCP servers every call — and may eat a
# FastMCP Cloud cold start (~20-30s) each time. For batches that's N x connect
# + N x handshake.
#
# LiveFinder opens MCP transports lazily and caches one worker per touched
# node. A single `async with LiveFinder()` covers any number of `.run(q)`
# calls; only the first query that visits a node pays the connect/cold-start
# cost.
# ---------------------------------------------------------------------------


class LiveFinder:
    """Router-driven live (layered Stage 1 + Stage 2) finder.

    Use as an async context manager so MCP cleanup is deterministic:

        async with LiveFinder() as lf:
            for q in queries:
                decision, output = await lf.run(q)

    The tool-less router is built once. Per-node workers are built and entered
    lazily — the first query that routes to a given node pays the MCP startup
    cost; all subsequent queries for that node reuse the open transports.
    """

    def __init__(
        self,
        *,
        model: str = "openai:gpt-5.2",
        reasoning_effort: Literal["low", "medium", "high"] = "high",
        stage2_url: str | None = None,
        stage2_headers: dict[str, str] | None = None,
        fallback_node: str = "geo",
    ) -> None:
        self._model = model
        self._effort = reasoning_effort
        self._stage2_url = stage2_url
        self._stage2_headers = stage2_headers
        self._fallback = fallback_node
        self._router: Agent[None, RouterDecision] | None = None
        self._workers: dict[str, Agent[None, PDSLiveFindDatasetOutput]] = {}
        self._stack: AsyncExitStack | None = None

    # -- agent construction (formerly module-level builders) ----------------

    def _build_router(self) -> Agent[None, RouterDecision]:
        """Build the tool-less routing agent — pure classification, no MCP."""
        return Agent(
            self._model,
            output_type=RouterDecision,
            system_prompt=ROUTER_SYSTEM_PROMPT,
        )

    def _build_worker(self, node: str) -> Agent[None, PDSLiveFindDatasetOutput]:
        """Build a layered worker agent for one node.

        Stage 1 toolset: hosted FastMCP server (5 live directory-walking tools).
        Stage 2 toolset: hosted FastMCP server, filtered to that node's
        ``Stage2Spec.allowed`` set (see ``live_finder.stage2``).
        """
        stage1 = build_stage1_mcp()
        stage2 = build_stage2_toolset_for(
            node, url=self._stage2_url, headers=self._stage2_headers
        )
        return Agent(
            self._model,
            toolsets=[stage1, stage2],
            output_type=PDSLiveFindDatasetOutput,
            system_prompt=_build_layered_prompt(node),
            model_settings=ModelSettings(
                extra_body={"reasoning_effort": self._effort}
            ),
            retries=2,
        )

    # -- lifecycle ----------------------------------------------------------

    async def __aenter__(self) -> "LiveFinder":
        self._stack = AsyncExitStack()
        await self._stack.__aenter__()
        self._router = self._build_router()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        assert self._stack is not None
        try:
            await self._stack.__aexit__(exc_type, exc, tb)
        finally:
            self._workers.clear()
            self._router = None
            self._stack = None

    async def route(self, query: str) -> RouterDecision:
        """Run the router only — no Stage 1 or Stage 2 MCPs touched."""
        assert self._router is not None, "Use inside 'async with LiveFinder()'"
        return (await self._router.run(query)).output

    async def _get_worker(self, node: str) -> Agent[None, PDSLiveFindDatasetOutput]:
        node = node.lower()
        if node not in self._workers:
            assert self._stack is not None
            agent = self._build_worker(node)
            await self._stack.enter_async_context(agent)
            self._workers[node] = agent
        return self._workers[node]

    async def warm(self, nodes: list[str] | None = None) -> None:
        """Pre-build workers and hit each MCP transport with a no-op RPC.

        Stage 1 (sequential): ``_get_worker(node)`` for every node. The
        MCP transport's ``__aenter__`` registers anyio cancel scopes that
        MUST be exited from the SAME task that entered them — so we
        enter them one at a time from the caller's task (the same task
        that will eventually run ``__aexit__``). Parallelizing this with
        ``asyncio.gather`` triggers a "cancel scope in different task"
        RuntimeError at shutdown.

        Stage 2 (parallel): ``list_tools()`` against every transport. These
        are pure HTTP requests with no scope ownership, so we can fire
        them in parallel for a real ``tools/list`` RPC that confirms each
        FastMCP Cloud container is awake.

        FastMCP cold-start is per-container, not per-transport, so even
        sequential entry only pays the cold start once per server (~20-30s
        each for stage1 + stage2); the remaining 14 transports reuse the
        warm container and open in <1s.

        ``nodes=None`` warms every node in the registry.
        """
        assert self._stack is not None, "Use inside 'async with LiveFinder()'"
        targets = [n.lower() for n in (nodes if nodes is not None else SUPPORTED_NODES)]
        for node in targets:
            await self._get_worker(node)

        async def _list(ts):
            list_fn = getattr(ts, "list_tools", None)
            if callable(list_fn):
                try:
                    await list_fn()
                except Exception:  # noqa: BLE001
                    pass

        pings = []
        for node in targets:
            worker = self._workers[node]
            for ts in getattr(worker, "toolsets", ()) or ():
                pings.append(_list(ts))
        if pings:
            await asyncio.gather(*pings)

    async def run(
        self,
        query: str,
    ) -> tuple[RouterDecision, PDSLiveFindDatasetOutput]:
        """Route then run the worker. Returns (decision, output)."""
        decision = await self.route(query)
        node = decision.primary_node or self._fallback
        worker = await self._get_worker(node)
        result = await worker.run(query)
        return decision, result.output

    async def run_traced(
        self,
        query: str,
        *,
        router_usage=None,
        worker_usage=None,
    ) -> tuple[RouterDecision, PDSLiveFindDatasetOutput, list, list]:
        """Like ``run()`` but also returns the worker's full message history
        plus per-call usage objects.

        If ``router_usage`` / ``worker_usage`` are passed in (instances of
        pydantic-ai's ``RunUsage``), pydantic-ai accumulates into them in
        place — so the caller still sees tokens spent before a mid-run
        failure (e.g. context overflow). The same instances are also
        returned in the result tuple's last element.

        Returns:
            ``(decision, output, worker_messages, [router_usage, worker_usage])``.
            Convert each with ``run_eval._usage_to_dict`` and combine with
            ``run_eval._sum_usage``.
        """
        from pydantic_ai.usage import RunUsage

        assert self._router is not None, "Use inside 'async with LiveFinder()'"
        if router_usage is None:
            router_usage = RunUsage()
        if worker_usage is None:
            worker_usage = RunUsage()
        router_result = await self._router.run(query, usage=router_usage)
        decision = router_result.output
        node = decision.primary_node or self._fallback
        worker = await self._get_worker(node)
        worker_result = await worker.run(query, usage=worker_usage)
        return (
            decision,
            worker_result.output,
            list(worker_result.all_messages()),
            [router_usage, worker_usage],
        )


async def run_live_query(
    query: str,
    *,
    model: str = "openai:gpt-5.2",
    reasoning_effort: Literal["low", "medium", "high"] = "high",
    stage2_url: str | None = None,
    stage2_headers: dict[str, str] | None = None,
    fallback_node: str = "geo",
) -> tuple[RouterDecision, PDSLiveFindDatasetOutput]:
    """Single-shot live query. Opens and closes one transport set.

    For multiple queries, instantiate ``LiveFinder`` directly so the MCP
    transports are reused across queries.
    """
    async with LiveFinder(
        model=model,
        reasoning_effort=reasoning_effort,
        stage2_url=stage2_url,
        stage2_headers=stage2_headers,
        fallback_node=fallback_node,
    ) as lf:
        return await lf.run(query)


async def run_live_batch(
    queries: list[str],
    *,
    model: str = "openai:gpt-5.2",
    reasoning_effort: Literal["low", "medium", "high"] = "high",
    stage2_url: str | None = None,
    stage2_headers: dict[str, str] | None = None,
    fallback_node: str = "geo",
) -> list[tuple[RouterDecision, PDSLiveFindDatasetOutput]]:
    """Run a batch of queries reusing one set of MCP transports.

    Pays the MCP connect/cold-start cost only for the first query that visits
    each node — every subsequent query for the same node reuses the open
    transports. For N queries spanning M unique nodes this drops you from
    N transport opens to M.
    """
    results: list[tuple[RouterDecision, PDSLiveFindDatasetOutput]] = []
    async with LiveFinder(
        model=model,
        reasoning_effort=reasoning_effort,
        stage2_url=stage2_url,
        stage2_headers=stage2_headers,
        fallback_node=fallback_node,
    ) as lf:
        for q in queries:
            results.append(await lf.run(q))
    return results
