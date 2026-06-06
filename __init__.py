"""PDS dataset discovery agent — live and catalog modes.

The agent uses pydantic-ai with hosted MCP tool servers to navigate
live PDS archive trees and faceted search APIs.
"""

from __future__ import annotations

__all__ = [
    "build_finder",
    "run_finder",
    "FinderKind",
    "FinderConfig",
]


def __getattr__(name: str):
    if name in __all__:
        from . import finder

        return getattr(finder, name)
    raise AttributeError(f"module 'pydantic_code' has no attribute {name!r}")
