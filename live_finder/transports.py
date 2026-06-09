"""MCP transport builders for the layered finder.

Both stages are HOSTED FastMCP servers reached over streamable HTTP — nothing
runs as a local subprocess:

* **Stage 1** — the deployed ``pds-node-mcp`` instance, exposing the 5 live
  directory-walking tools (``pds_list_missions``, ``pds_list_dataset_dirs``,
  ``pds_probe_datasets``, ``pds_inspect_collections``, ``pds_resolve_volume``).
* **Stage 2** — a second hosted instance exposing the deeper faceted-search
  tools (ode_* / opus_* / img_* / sbn_* / pds4*), filtered per node.

Defaults match the production deployment; override via ``PDS_STAGE1_MCP_URL`` /
``PDS_STAGE2_MCP_URL`` (or the ``url`` / ``headers`` kwargs) for staging or
local mirrors. ``Authorization: Bearer <FAST_MCP_AUTH>`` is added automatically
when that env var is present.
"""

from __future__ import annotations

import os

from pydantic_ai.mcp import MCPServerStreamableHTTP

from pydantic_code.live_finder.stage2 import stage2_spec_for

# Hosted streamable-HTTP endpoints — all consumers hit the same servers.
_DEFAULT_STAGE1_URL = "https://fuzzy-aquamarine-swordtail.fastmcp.app/mcp"
_DEFAULT_STAGE2_URL = "https://natural-bronze-stingray.fastmcp.app/mcp"

# timeout=30: pydantic-ai's default of 5s is too aggressive for FastMCP Cloud
# cold starts. A serverless instance that's been idle can take 20-30s to boot
# on the first request; with the 5s default the first queries of a batch
# reliably time out before the server is ready.
_MCP_TIMEOUT = 30


def _bearer_headers(headers: dict[str, str] | None) -> dict[str, str] | None:
    """Default to ``Authorization: Bearer <FAST_MCP_AUTH>`` when unset."""
    if headers is not None:
        return headers
    token = os.environ.get("FAST_MCP_AUTH")
    return {"Authorization": f"Bearer {token}"} if token else None


def build_stage1_mcp(
    *,
    url: str | None = None,
    headers: dict[str, str] | None = None,
) -> MCPServerStreamableHTTP:
    """Connect to the hosted Stage 1 MCP server over streamable HTTP.

    Override via ``PDS_STAGE1_MCP_URL`` for staging / local mirrors, or pass
    ``url`` / ``headers`` directly.
    """
    resolved_url = url or os.environ.get("PDS_STAGE1_MCP_URL") or _DEFAULT_STAGE1_URL
    return MCPServerStreamableHTTP(
        url=resolved_url, headers=_bearer_headers(headers), timeout=_MCP_TIMEOUT
    )


def build_stage2_mcp(
    *,
    url: str | None = None,
    headers: dict[str, str] | None = None,
) -> MCPServerStreamableHTTP:
    """Connect to the hosted Stage 2 MCP server over streamable HTTP.

    Override via ``PDS_STAGE2_MCP_URL`` for staging / local mirrors, or pass
    ``url`` / ``headers`` directly.
    """
    resolved_url = url or os.environ.get("PDS_STAGE2_MCP_URL") or _DEFAULT_STAGE2_URL
    return MCPServerStreamableHTTP(
        url=resolved_url, headers=_bearer_headers(headers), timeout=_MCP_TIMEOUT
    )


def build_stage2_toolset_for(node: str, **stage2_kwargs):
    """Build a per-node filtered Stage 2 toolset.

    The Stage 2 MCP exposes every layered tool; ``.filtered(...)`` hides
    everything not in that node's allow-list so the worker only ever sees its
    node's faceted-search tools.
    """
    allowed = stage2_spec_for(node).allowed
    return build_stage2_mcp(**stage2_kwargs).filtered(
        lambda ctx, td: td.name in allowed
    )
