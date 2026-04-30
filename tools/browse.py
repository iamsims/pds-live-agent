"""Browse a directory on the live GEO node."""

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
from .parsers import filename_from_url


class PDSGeoDirectoryEntry(BaseModel):
    """One entry in a GEO directory listing."""

    name: str = Field(description="Entry name (no trailing slash)")
    url: str = Field(description="Absolute URL of the entry on pds-geosciences.wustl.edu")
    is_dir: bool = Field(description="True for sub-directories, False for files")


class PDSGeoBrowseDirectoryOutput(BaseModel):
    """Output for pds_geo_browse_directory."""

    status: str = Field(..., description="'success', 'not_found', or 'invalid_input'")
    url: str = Field(..., description="Absolute URL of the directory that was listed")
    directory_count: int = Field(..., description="Number of sub-directories returned")
    file_count: int = Field(..., description="Number of files returned")
    entries: list[PDSGeoDirectoryEntry] = Field(
        default_factory=list,
        description="Sub-directories first, then files",
    )
    error: str | None = Field(None, description="Error message when status is not 'success'")


async def pds_geo_browse_directory(
    path: str = "",
    *,
    base_url: str = GEO_BASE_URL,
    timeout: float = 30.0,
) -> PDSGeoBrowseDirectoryOutput:
    """List sub-directories and files at a path on the live GEO node.

    Fetches the Apache directory index at
    ``https://pds-geosciences.wustl.edu/<path>/`` and returns its sub-directories
    and files. Empty path lists the top-level mission directories.
    """
    try:
        async with GEOLiveClient(base_url=base_url, timeout=timeout) as client:
            dir_urls, file_urls = await client.list_directory(path)
            listed_url = client._resolve(path, must_be_dir=True)

        entries = [PDSGeoDirectoryEntry(name=filename_from_url(u), url=u, is_dir=True) for u in dir_urls] + [
            PDSGeoDirectoryEntry(name=filename_from_url(u), url=u, is_dir=False) for u in file_urls
        ]

        return PDSGeoBrowseDirectoryOutput(
            status="success",
            url=listed_url,
            directory_count=len(dir_urls),
            file_count=len(file_urls),
            entries=entries,
        )

    except GEOPathInvalidError as e:
        return PDSGeoBrowseDirectoryOutput(
            status="invalid_input",
            url="",
            directory_count=0,
            file_count=0,
            error=str(e),
        )
    except GEOPathNotFoundError as e:
        return PDSGeoBrowseDirectoryOutput(
            status="not_found",
            url="",
            directory_count=0,
            file_count=0,
            error=str(e),
        )
    except GEOLiveClientError as e:
        logger.error(f"GEO live client error: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in pds_geo_browse_directory: {e}")
        raise RuntimeError(f"Internal error browsing GEO directory: {e}") from e
