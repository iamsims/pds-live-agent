"""Stage 2 per-node faceted-search toolsets — data + transport filtering.

Stage 2 is the SECOND set of tools a layered worker may escalate to after
Stage 1 (the live directory walk) has located a bundle/collection. Each node
maps to one ``Stage2Spec`` that bundles two things which MUST stay in sync:

* ``prose``   — the plain-text tool block injected into the worker's system
                prompt (so the model knows the tools exist and how to call them).
* ``allowed`` — the frozenset the hosted Stage 2 MCP server is ``.filtered(...)``
                down to (so the worker can ONLY see its node's tools).

Keeping both on one object is deliberate: a tool named in ``prose`` but absent
from ``allowed`` is advertised-but-invisible; the reverse is callable-but-
undocumented. One source of truth per toolset makes that drift impossible.

Nodes without a bespoke faceted API (PPI, ATM, NAIF, LROC) share the cross-node
PDS4 registry fallback, which is also the safe default for any unknown node.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Stage2Spec:
    """One node's Stage 2 toolset: the prompt block + the MCP allow-list.

    ``allowed`` is derived from ``prose`` is NOT assumed — both are stated
    explicitly so the prose can carry parameter hints the bare tool names
    can't, while the allow-list stays the authoritative filter.
    """

    prose: str
    allowed: frozenset[str]


# ---------------------------------------------------------------------------
# Per-toolset specs. Each tool appears once, with a short parameter hint and a
# one-line purpose. No literal '{' or '}' — the prose is rendered via
# str.format when composed into the Stage 2 appendix.
# ---------------------------------------------------------------------------

_GEO = Stage2Spec(
    prose=(
        "  - ode_search_products_tool(target=..., instrument=..., bbox=..., "
        "pt=..., product_type=...): faceted product search across GEO/ODE "
        "holdings. Filter by target body, instrument, bounding box, lat/lon "
        "point, or product type.\n"
        "  - ode_count_products_tool(target=..., instrument=..., bbox=...): cheap "
        "count before pulling a large result set.\n"
        "  - ode_list_instruments_tool(target=...): enumerate instrument codes "
        "valid for a target.\n"
        "  - ode_list_feature_classes_tool(target=...) / "
        "ode_list_feature_names_tool(target=..., feature_class=...): gazetteer "
        "lookup for named surface features (craters, maria, etc.).\n"
        "  - ode_get_feature_bounds_tool(target=..., feature_name=...): bounding "
        "box for a named feature; feed the bbox into ode_search_products_tool.\n"
    ),
    allowed=frozenset({
        "ode_search_products_tool",
        "ode_count_products_tool",
        "ode_list_instruments_tool",
        "ode_list_feature_classes_tool",
        "ode_list_feature_names_tool",
        "ode_get_feature_bounds_tool",
    }),
)

_IMG = Stage2Spec(
    prose=(
        "  - img_search_tool(target=..., instrument=..., mission=..., "
        "time_range=..., filters=...): IMG faceted product search.\n"
        "  - img_get_facets_tool(field=...): enumerate valid facet values "
        "(instruments, missions, targets, product types) for the IMG catalog.\n"
        "  - img_get_product_tool(product_id=...): fetch metadata for one IMG "
        "product.\n"
        "  - img_count_tool(target=..., instrument=..., ...): count matches "
        "without pulling rows.\n"
    ),
    allowed=frozenset({
        "img_search_tool",
        "img_get_facets_tool",
        "img_get_product_tool",
        "img_count_tool",
    }),
)

_RMS = Stage2Spec(
    prose=(
        "  - opus_search_tool(target=..., instrument=..., time_range=..., "
        "ring_geometry=..., observation_type=...): RMS OPUS faceted product "
        "search at the observation/granule level.\n"
        "  - opus_count_tool(...): count results before pulling them.\n"
        "  - opus_get_metadata_tool(opus_id=...): metadata for one observation.\n"
        "  - opus_get_files_tool(opus_id=..., product_type=...): file list for "
        "one observation, optionally filtered by product type (raw / calibrated "
        "/ preview / geometry).\n"
    ),
    allowed=frozenset({
        "opus_search_tool",
        "opus_count_tool",
        "opus_get_metadata_tool",
        "opus_get_files_tool",
    }),
)

_SBN = Stage2Spec(
    prose=(
        "  - sbn_search_object_tool(target_name=..., target_type=...): look up "
        "data by small-body name (comet, asteroid, KBO).\n"
        "  - sbn_search_coordinates_tool(ra=..., dec=..., radius=..., "
        "epoch=...): spatial search of small-body observations near a sky "
        "position.\n"
        "  - sbn_list_sources_tool(): enumerate SBN sub-archives / mirrors when "
        "the PSI tree is unavailable (e.g. UMD mirror for Rosetta / Stardust / "
        "Deep Impact / comets).\n"
    ),
    allowed=frozenset({
        "sbn_search_object_tool",
        "sbn_search_coordinates_tool",
        "sbn_list_sources_tool",
    }),
)

# Shared PDS4 registry fallback for nodes without a bespoke deep-search API
# (PPI, ATM, NAIF, LROC) and the safe default for any unknown node.
_PDS4_FALLBACK = Stage2Spec(
    prose=(
        "  - pds4search_bundles_tool(keywords=..., investigation=..., "
        "instrument=..., target=...): cross-node PDS4 registry bundle search.\n"
        "  - pds4search_collections_tool(bundle_lid=..., keywords=..., ...): "
        "collection search; reuse the Stage 1 bundle LID as a filter when "
        "possible.\n"
        "  - pds4search_products_tool(collection_lid=..., keywords=..., ...): "
        "product-level search inside a collection.\n"
        "  - pds4search_investigations_tool / pds4search_instruments_tool / "
        "pds4search_instrument_hosts_tool / pds4search_targets_tool: context-"
        "product lookups when user-facing names need to be resolved to LIDs.\n"
        "  - pds4get_product_tool(lid=...): fetch one product label by LID.\n"
        "  - pds4crawl_context_product_tool(lid=...): walk a context product's "
        "associations to find related bundles/collections.\n"
    ),
    allowed=frozenset({
        "pds4search_bundles_tool",
        "pds4search_collections_tool",
        "pds4search_products_tool",
        "pds4search_investigations_tool",
        "pds4search_instruments_tool",
        "pds4search_instrument_hosts_tool",
        "pds4search_targets_tool",
        "pds4get_product_tool",
        "pds4crawl_context_product_tool",
    }),
)


# Single source of truth: node id -> its Stage 2 spec. Nodes absent here (and
# unknown nodes) fall back to PDS4 via ``stage2_spec_for``.
STAGE2_BY_NODE: dict[str, Stage2Spec] = {
    "geo":  _GEO,
    "img":  _IMG,
    "rms":  _RMS,
    "sbn":  _SBN,
    "ppi":  _PDS4_FALLBACK,
    "atm":  _PDS4_FALLBACK,
    "naif": _PDS4_FALLBACK,
    "lroc": _PDS4_FALLBACK,
}

# The PDS4 fallback spec, exposed for callers that need the default directly.
PDS4_FALLBACK = _PDS4_FALLBACK


def stage2_spec_for(node: str) -> Stage2Spec:
    """Return the Stage 2 spec for ``node`` (PDS4 fallback if unmapped)."""
    return STAGE2_BY_NODE.get(node.lower(), _PDS4_FALLBACK)
