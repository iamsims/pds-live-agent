"""List sub-directory names under a path on any PDS node.

Cheap HTTP call — fetches the Apache directory listing and returns
directory names only. No label parsing, no recursion. The agent uses
this to see what dataset directories exist, then picks which ones to
probe in depth.
"""

from __future__ import annotations

import re

from loguru import logger
from pydantic import BaseModel, Field

from .client import (
    PDSLiveClient,
    PDSLiveClientError,
    PDSPathInvalidError,
    PDSPathNotFoundError,
)
from .node_registry import get_base_url
from .parsers import filename_from_url

# PDS3 dataset dirs use hyphenated names ending with a version,
# e.g. "mex-m-hrsc-5-refdr-dtm-v1" (at least 3 hyphens, ends with -v<digits>).
_PDS3_DIR_RE = re.compile(r"^[A-Za-z0-9_]+(-[A-Za-z0-9_]+){2,}-[Vv]\d+", re.IGNORECASE)

# PDS3 volume-set directories on RMS (e.g. COISS_2xxx, COUVIS_0xxx, GO_0017)
# and ATM (e.g. cocirs_0401, MROM_2001, jnomwr_1100V2): uppercase or lowercase
# letters, underscore, digits (often _0xxx, _Nxxx, _<digits>).
_PDS3_VOLSET_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]*_[0-9A-Za-z_]+", re.ASCII)

# PDS4 bundle dirs typically use lowercase descriptive names with
# underscores/hyphens, sometimes containing "bundle". Examples:
#   cassini_iss, cassini-mag-cal, juno_jiram_bundle, mer2_pancam_sci_calibrated2,
#   mgn-atm-profile, msl_ice-dust, junocam_atm-ml-calib
# Heuristic: all-lowercase, contains at least one separator (_ or -),
# does NOT match the PDS3 volume regex, does NOT end with -vN, and the
# basename has at least two tokens.
_PDS4_BUNDLE_RE = re.compile(r"^[a-z][a-z0-9]*([_\-][a-z0-9]+)+$")


def _infer_pds_version(dirname: str) -> str | None:
    """Infer PDS version from a directory name (heuristic, no HTTP).

    Rules, in priority order:
      1. ``urn-nasa-pds-…`` / ``urn_nasa_pds_…`` → PDS4 (canonical LID form).
      2. Hyphenated name ending with ``-v<digits>`` → PDS3 dataset directory
         (e.g. ``mex-m-hrsc-5-refdr-dtm-v1``).
      3. ``<UPPER_OR_LOWER>_<DIGITS_OR_LETTERS>`` (e.g. ``COISS_2001``,
         ``MROM_2001``, ``jnomwr_1100V2``, ``cocirs_1709``) → PDS3 volume.
      4. All-lowercase with at least one ``_`` or ``-`` separator and not
         matching PDS3 patterns → PDS4 bundle (e.g. ``cassini-mag-cal``,
         ``juno_jiram_bundle``, ``mer2_pancam_sci_calibrated2``).
      5. Otherwise → None.
    """
    lower = dirname.lower()
    if lower.startswith("urn-nasa-pds-") or lower.startswith("urn_nasa_pds_"):
        return "PDS4"
    if _PDS3_DIR_RE.match(dirname):
        return "PDS3"
    # Volume-set heuristic: NAME_<num> shape. Only fires when the dir name
    # actually contains digits in the tail token, so plain words like
    # "messenger" or "cassini" don't get tagged PDS3.
    if _PDS3_VOLSET_RE.match(dirname) and any(ch.isdigit() for ch in dirname):
        return "PDS3"
    # PDS4 bundle heuristic: all lowercase, contains separator, no version-vN tail.
    if dirname == lower and _PDS4_BUNDLE_RE.match(lower):
        return "PDS4"
    return None


class PDSDatasetDir(BaseModel):
    """One sub-directory under a path on a PDS node."""

    name: str = Field(description="Directory name")
    path: str = Field(description="Full relative path from the node root")
    pds_hint: str | None = Field(
        default=None,
        description="'PDS3' or 'PDS4' inferred from directory naming convention (not verified)",
    )


# Backward-compat alias
PDSGeoDatasetDir = PDSDatasetDir


class PDSListDatasetDirsOutput(BaseModel):
    """Output for pds_list_dataset_dirs."""

    status: str = Field(..., description="'success', 'not_found', or 'invalid_input'")
    path: str = Field(..., description="The path that was listed")
    total: int = Field(default=0, description="Total number of sub-directories found (before filtering)")
    filtered_total: int | None = Field(
        default=None,
        description="Number of directories after applying filter (None when no filter used)",
    )
    dirs: list[PDSDatasetDir] = Field(
        default_factory=list,
        description="Sub-directories found at the path, with inferred PDS version hints",
    )
    error: str | None = Field(None, description="Error message when status is not 'success'")


# Backward-compat alias
PDSGeoListDatasetDirsOutput = PDSListDatasetDirsOutput


async def pds_list_dataset_dirs(
    path: str,
    *,
    node: str = "geo",
    filter: str | None = None,
    timeout: float = 30.0,
) -> PDSListDatasetDirsOutput:
    """List sub-directory names at a path on a PDS node.

    No label parsing — just lists what directories exist. Each directory
    gets a ``pds_hint`` inferred from its naming convention (``urn-nasa-pds-*``
    → PDS4, hyphenated-with-version → PDS3, else None).

    Args:
        path: Directory path to list (e.g. "mex/" for GEO, "data/" for PPI).
        node: PDS node identifier ("geo", "ppi", "lroc").
        filter: Optional case-insensitive substring filter on directory names.
            When set, only directories whose names contain this string are returned.
        timeout: HTTP timeout in seconds.
    """
    base_url = get_base_url(node)
    try:
        async with PDSLiveClient(base_url=base_url, timeout=timeout) as client:
            dir_urls, _ = await client.list_directory(path)

        from urllib.parse import urlsplit

        base_path = urlsplit(base_url if base_url.endswith("/") else base_url + "/").path
        all_dirs: list[PDSDatasetDir] = []
        for d_url in dir_urls:
            name = filename_from_url(d_url)
            target_path = urlsplit(d_url).path
            relative = (
                target_path[len(base_path):]
                if target_path.startswith(base_path)
                else target_path.lstrip("/")
            )
            all_dirs.append(
                PDSDatasetDir(
                    name=name,
                    path=relative,
                    pds_hint=_infer_pds_version(name),
                )
            )

        total = len(all_dirs)

        # Apply optional filter
        if filter:
            filter_lower = filter.lower()
            filtered_dirs = [d for d in all_dirs if filter_lower in d.name.lower()]
            return PDSListDatasetDirsOutput(
                status="success",
                path=path,
                total=total,
                filtered_total=len(filtered_dirs),
                dirs=filtered_dirs,
            )

        return PDSListDatasetDirsOutput(
            status="success",
            path=path,
            total=total,
            dirs=all_dirs,
        )

    except PDSPathInvalidError as e:
        return PDSListDatasetDirsOutput(status="invalid_input", path=path, error=str(e))
    except PDSPathNotFoundError as e:
        return PDSListDatasetDirsOutput(status="not_found", path=path, error=str(e))
    except PDSLiveClientError as e:
        logger.error(f"PDS live client error: {e}")
        if "HTTP 403" in str(e):
            return PDSListDatasetDirsOutput(
                status="forbidden",
                path=path,
                error="HTTP 403 — server denied access. Use the abbreviation table "
                "to synthesise candidates instead.",
            )
        raise
    except Exception as e:
        logger.error(f"Unexpected error in pds_list_dataset_dirs: {e}")
        raise RuntimeError(f"Internal error listing directory: {e}") from e


# Backward-compat alias
pds_geo_list_dataset_dirs = pds_list_dataset_dirs
