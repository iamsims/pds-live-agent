"""PDS Geosciences finder + tools, ported to pydantic-ai.

Same behaviour as ``akd_ext.agents.pds_geo_finder`` and
``akd_ext.tools.pds.pds_geo``, but with no dependency on akd-core or the
OpenAI Agents SDK. The agent is a single ``pydantic_ai.Agent`` instance
with five tool functions registered.

The agent module (``pydantic_code.pds_geo_finder``) requires ``pydantic-ai``
to be installed; the tool layer (``pydantic_code.tools``) does not. We
import lazily so the tool layer remains usable on its own.
"""

from __future__ import annotations

__all__ = [
    # Geo-specific exports
    "PDSGeoDatasetCandidate",
    "PDSGeoFindDatasetInput",
    "PDSGeoFindDatasetOutput",
    "pds_geo_finder_agent",
    "run_pds_geo_finder",
    # Unified finder exports
    "build_finder",
    "run_finder",
    "FinderKind",
    "FinderConfig",
]

_FINDER_NAMES = {"build_finder", "run_finder", "FinderKind", "FinderConfig"}


def __getattr__(name: str):
    if name in __all__ and name not in _FINDER_NAMES:
        from . import pds_geo_finder

        return getattr(pds_geo_finder, name)
    if name in _FINDER_NAMES:
        from . import finder

        return getattr(finder, name)
    raise AttributeError(f"module 'pydantic_code' has no attribute {name!r}")
