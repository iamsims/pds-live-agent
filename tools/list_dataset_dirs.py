"""List sub-directory names under a mission path on the GEO node.

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
    GEO_BASE_URL,
    GEOLiveClient,
    GEOLiveClientError,
    GEOPathInvalidError,
    GEOPathNotFoundError,
)
from .parsers import filename_from_url

# PDS3 dataset dirs use hyphenated names ending with a version,
# e.g. "mex-m-hrsc-5-refdr-dtm-v1" (at least 3 hyphens, ends with -v<digits>).
_PDS3_DIR_RE = re.compile(r"^[A-Za-z0-9_]+(-[A-Za-z0-9_]+){2,}-[Vv]\d+", re.IGNORECASE)


def _infer_pds_version(dirname: str) -> str | None:
    """Infer PDS version from a directory name (heuristic, no HTTP)."""
    lower = dirname.lower()
    if lower.startswith("urn-nasa-pds-") or lower.startswith("urn_nasa_pds_"):
        return "PDS4"
    if _PDS3_DIR_RE.match(dirname):
        return "PDS3"
    return None


class PDSGeoDatasetDir(BaseModel):
    """One sub-directory under a mission path."""

    name: str = Field(description="Directory name")
    path: str = Field(description="Full relative path from GEO root (e.g. 'mex/mex-m-hrsc-5-refdr-dtm-v1/')")
    pds_hint: str | None = Field(
        default=None,
        description="'PDS3' or 'PDS4' inferred from directory naming convention (not verified)",
    )


class PDSGeoListDatasetDirsOutput(BaseModel):
    """Output for pds_geo_list_dataset_dirs."""

    status: str = Field(..., description="'success', 'not_found', or 'invalid_input'")
    path: str = Field(..., description="The mission path that was listed")
    total: int = Field(default=0, description="Total number of sub-directories found")
    dirs: list[PDSGeoDatasetDir] = Field(
        default_factory=list,
        description="Sub-directories found at the path, with inferred PDS version hints",
    )
    error: str | None = Field(None, description="Error message when status is not 'success'")


async def pds_geo_list_dataset_dirs(
    path: str,
    *,
    base_url: str = GEO_BASE_URL,
    timeout: float = 30.0,
) -> PDSGeoListDatasetDirsOutput:
    """List sub-directory names at a path on the GEO node.

    No label parsing — just lists what directories exist. Each directory
    gets a ``pds_hint`` inferred from its naming convention (``urn-nasa-pds-*``
    → PDS4, hyphenated-with-version → PDS3, else None).
    """
    try:
        async with GEOLiveClient(base_url=base_url, timeout=timeout) as client:
            dir_urls, _ = await client.list_directory(path)

        from urllib.parse import urlsplit, unquote

        base_path = urlsplit(base_url if base_url.endswith("/") else base_url + "/").path
        dirs: list[PDSGeoDatasetDir] = []
        for d_url in dir_urls:
            name = filename_from_url(d_url)
            target_path = urlsplit(d_url).path
            relative = (
                target_path[len(base_path):]
                if target_path.startswith(base_path)
                else target_path.lstrip("/")
            )
            dirs.append(
                PDSGeoDatasetDir(
                    name=name,
                    path=relative,
                    pds_hint=_infer_pds_version(name),
                )
            )

        return PDSGeoListDatasetDirsOutput(
            status="success",
            path=path,
            total=len(dirs),
            dirs=dirs,
        )

    except GEOPathInvalidError as e:
        return PDSGeoListDatasetDirsOutput(status="invalid_input", path=path, error=str(e))
    except GEOPathNotFoundError as e:
        return PDSGeoListDatasetDirsOutput(status="not_found", path=path, error=str(e))
    except GEOLiveClientError as e:
        logger.error(f"GEO live client error: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in pds_geo_list_dataset_dirs: {e}")
        raise RuntimeError(f"Internal error listing GEO directory: {e}") from e
