"""Scan a parent directory and pull each immediate sub-directory's first label title.

One call replaces N (browse + inspect) calls when an agent just wants to see
"what datasets live under this mission" with their titles.
"""

from __future__ import annotations

from loguru import logger
from pydantic import BaseModel, Field

from .client import (
    GEO_BASE_URL,
    GEOLiveClient,
    GEOLiveClientError,
    GEOPathInvalidError,
    GEOPathNotFoundError,
)


class PDSGeoScanItem(BaseModel):
    """One sub-directory in a scan, with its first-label title if any."""

    path: str = Field(description="Sub-directory path relative to the GEO base URL")
    url: str = Field(description="Absolute URL of the sub-directory")
    title: str | None = Field(
        default=None,
        description="Title from the sub-directory's first label, or None if no label is present",
    )
    pds_version: str | None = Field(default=None, description="'PDS3' or 'PDS4' if a label was found")
    file_type: str | None = Field(
        default=None,
        description="'voldesc.cat', 'bundle_xml', etc. if a label was found",
    )


class PDSGeoScanWithTitlesOutput(BaseModel):
    """Output for pds_geo_scan_with_titles."""

    status: str = Field(..., description="'success', 'not_found', or 'invalid_input'")
    parent_url: str = Field(..., description="Absolute URL of the directory that was scanned")
    total_subdirs: int = Field(..., description="Total sub-directories present at the parent")
    scanned_count: int = Field(..., description="How many of those were inspected (capped by max_subdirs)")
    items: list[PDSGeoScanItem] = Field(
        default_factory=list,
        description="One entry per scanned sub-directory; title=None means no label was found at that path",
    )
    error: str | None = Field(None, description="Error message when status is not 'success'")


async def pds_geo_scan_with_titles(
    parent_path: str = "",
    max_subdirs: int = 30,
    *,
    base_url: str = GEO_BASE_URL,
    timeout: float = 30.0,
    concurrency: int = 10,
) -> PDSGeoScanWithTitlesOutput:
    """Scan a parent directory and harvest each sub-directory's title in one call.

    Triage tool — when you have a candidate mission like ``mex/`` or ``mer/``
    and want a one-shot menu of what's inside with each dataset's
    human-readable title and pds_version. Sub-dirs without a label come back
    with ``title=None``.

    ``max_subdirs`` is capped at 50 (and at least 1) to protect against giant
    mission dirs fanning out into hundreds of HTTP requests.
    """
    max_subdirs = max(1, min(50, max_subdirs))

    try:
        async with GEOLiveClient(base_url=base_url, timeout=timeout) as client:
            record = await client.scan_with_titles(
                parent_path=parent_path,
                max_subdirs=max_subdirs,
                concurrency=concurrency,
            )

        items = [PDSGeoScanItem(**item) for item in record["items"]]
        return PDSGeoScanWithTitlesOutput(
            status="success",
            parent_url=record["parent_url"],
            total_subdirs=record["total_subdirs"],
            scanned_count=record["scanned_count"],
            items=items,
        )

    except GEOPathInvalidError as e:
        return PDSGeoScanWithTitlesOutput(
            status="invalid_input", parent_url="", total_subdirs=0, scanned_count=0, error=str(e)
        )
    except GEOPathNotFoundError as e:
        return PDSGeoScanWithTitlesOutput(
            status="not_found", parent_url="", total_subdirs=0, scanned_count=0, error=str(e)
        )
    except GEOLiveClientError as e:
        logger.error(f"GEO live client error: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in pds_geo_scan_with_titles: {e}")
        raise RuntimeError(f"Internal error scanning GEO directory: {e}") from e
