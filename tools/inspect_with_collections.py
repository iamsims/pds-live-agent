"""Scan subdirs of a PDS4 bundle for collection labels."""

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
from .inspect import PDSGeoLabel


class PDSGeoInspectCollectionsOutput(BaseModel):
    """Output for pds_geo_inspect_collections."""

    status: str = Field(..., description="'success', 'not_found', or 'invalid_input'")
    volume_dir: str | None = Field(None, description="Path of the bundle relative to the GEO base URL")
    collections: list[PDSGeoLabel] = Field(
        default_factory=list,
        description=(
            "PDS4 collection labels found one directory level below the bundle. "
            "Each entry contains the collection's logical_identifier in fields.Identification_Area."
        ),
    )
    error: str | None = Field(None, description="Error message when status is not 'success'")


async def pds_geo_inspect_collections(
    path: str,
    max_subdirs: int = 20,
    *,
    base_url: str = GEO_BASE_URL,
    timeout: float = 30.0,
    concurrency: int = 10,
) -> PDSGeoInspectCollectionsOutput:
    """Scan subdirs of a PDS4 bundle path for collection labels.

    Walks the immediate sub-directories of ``path`` (skipping
    ``document/``, ``index/``, ``catalog/``, ``browse/``, ``checksums/``)
    and collects every ``collection_*.xml/.lblx`` label found.
    """
    max_subdirs = max(1, min(50, max_subdirs))

    try:
        async with GEOLiveClient(base_url=base_url, timeout=timeout) as client:
            record = await client.inspect_collections(
                path,
                max_subdirs=max_subdirs,
                concurrency=concurrency,
            )

        return PDSGeoInspectCollectionsOutput(
            status="success",
            volume_dir=record["volume_dir"],
            collections=[PDSGeoLabel(**label) for label in record["collections"]],
        )

    except GEOPathInvalidError as e:
        return PDSGeoInspectCollectionsOutput(status="invalid_input", error=str(e))
    except GEOPathNotFoundError as e:
        return PDSGeoInspectCollectionsOutput(status="not_found", error=str(e))
    except GEOLiveClientError as e:
        logger.error(f"GEO live client error: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in pds_geo_inspect_collections: {e}")
        raise RuntimeError(f"Internal error scanning collections: {e}") from e
