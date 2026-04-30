"""Inspect a PDS4 bundle path AND its one-level collections in one call."""

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


class PDSGeoInspectWithCollectionsOutput(BaseModel):
    """Output for pds_geo_inspect_with_collections."""

    status: str = Field(..., description="'success', 'not_found', or 'invalid_input'")
    volume_dir: str | None = Field(None, description="Path of the bundle/volume relative to the GEO base URL")
    labels: list[PDSGeoLabel] = Field(
        default_factory=list,
        description="Labels found at the input path (PDS3 voldesc and/or PDS4 bundle)",
    )
    collections: list[PDSGeoLabel] = Field(
        default_factory=list,
        description=(
            "PDS4 collection labels found one directory level below the bundle. "
            "Empty when no PDS4 bundle was found at the input path."
        ),
    )
    error: str | None = Field(None, description="Error message when status is not 'success'")


async def pds_geo_inspect_with_collections(
    path: str,
    max_subdirs: int = 20,
    *,
    base_url: str = GEO_BASE_URL,
    timeout: float = 30.0,
    concurrency: int = 10,
) -> PDSGeoInspectWithCollectionsOutput:
    """Inspect a PDS4 bundle path AND its one-level collections in one call.

    Returns the bundle's own labels (under ``labels``) plus every
    ``collection_*.xml/.lblx`` label found one directory level beneath
    (under ``collections``). Sub-dirs named ``document``, ``index``,
    ``catalog``, ``browse``, ``calibration`` are skipped.

    If the path holds only a PDS3 voldesc, ``collections`` is empty.
    """
    max_subdirs = max(1, min(50, max_subdirs))

    try:
        async with GEOLiveClient(base_url=base_url, timeout=timeout) as client:
            record = await client.inspect_with_pds4_collections(
                path,
                max_subdirs=max_subdirs,
                concurrency=concurrency,
            )

        return PDSGeoInspectWithCollectionsOutput(
            status="success",
            volume_dir=record["volume_dir"],
            labels=[PDSGeoLabel(**label) for label in record["labels"]],
            collections=[PDSGeoLabel(**label) for label in record["collections"]],
        )

    except GEOPathInvalidError as e:
        return PDSGeoInspectWithCollectionsOutput(status="invalid_input", error=str(e))
    except GEOPathNotFoundError as e:
        return PDSGeoInspectWithCollectionsOutput(status="not_found", error=str(e))
    except GEOLiveClientError as e:
        logger.error(f"GEO live client error: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in pds_geo_inspect_with_collections: {e}")
        raise RuntimeError(f"Internal error inspecting GEO bundle with collections: {e}") from e
