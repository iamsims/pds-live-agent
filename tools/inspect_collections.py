"""Inspect a PDS4 bundle directory for its collection labels.

Walks the immediate sub-directories of a bundle path (skipping
document/, index/, catalog/, browse/, checksums/) and parses every
collection*.xml/lblx label found. Returns collection-level
logical_identifiers and titles.
"""

from __future__ import annotations

from typing import Any

from loguru import logger
from pydantic import BaseModel, Field

from .client import (
    GEO_BASE_URL,
    GEOLiveClient,
    GEOLiveClientError,
    GEOPathInvalidError,
    GEOPathNotFoundError,
    _extract_title,
)


def _extract_dataset_id(fields: dict[str, Any]) -> str | None:
    """Extract logical_identifier from PDS4 collection fields."""
    ia = fields.get("Identification_Area")
    if isinstance(ia, dict):
        lid = ia.get("logical_identifier")
        if isinstance(lid, str) and lid.strip():
            return lid.strip()
    return None


def _slim_pds4_fields(fields: dict[str, Any]) -> dict[str, Any]:
    """Keep only Identification_Area from a parsed PDS4 XML label."""
    out: dict[str, Any] = {}
    ia = fields.get("Identification_Area")
    if ia is not None:
        out["Identification_Area"] = ia
    return out


class PDSGeoCollection(BaseModel):
    """One PDS4 collection label found in a bundle subdirectory."""

    path: str = Field(description="Subdirectory path where this collection was found")
    dataset_id: str | None = Field(
        default=None,
        description="Collection-level logical_identifier (e.g. urn:nasa:pds:bundle:data_calibrated)",
    )
    title: str | None = Field(default=None, description="Human-readable title from the collection label")
    file_type: str = Field(description="'collection_xml' or 'collection_lblx'")
    fields: dict[str, Any] = Field(description="Slimmed parsed label fields (Identification_Area only)")


class PDSGeoInspectCollectionsOutput(BaseModel):
    """Output for pds_geo_inspect_collections."""

    status: str = Field(..., description="'success', 'not_found', or 'invalid_input'")
    bundle_path: str | None = Field(None, description="The bundle path that was scanned")
    collections: list[PDSGeoCollection] = Field(
        default_factory=list,
        description="PDS4 collection labels found in subdirectories",
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
    """Scan subdirectories of a PDS4 bundle for collection labels.

    Walks the immediate sub-directories of ``path`` (skipping
    ``document/``, ``index/``, ``catalog/``, ``browse/``, ``checksums/``)
    and collects every ``collection_*.xml/.lblx`` label found.
    """
    max_subdirs = max(1, min(50, max_subdirs))

    try:
        async with GEOLiveClient(base_url=base_url, timeout=timeout) as client:
            record = await client.inspect_with_pds4_collections(
                path,
                max_subdirs=max_subdirs,
                concurrency=concurrency,
            )

        collections: list[PDSGeoCollection] = []
        for label in record.get("collections", []):
            raw_fields = label["fields"]
            slimmed = _slim_pds4_fields(raw_fields)
            collections.append(
                PDSGeoCollection(
                    path=record["volume_dir"],
                    dataset_id=_extract_dataset_id(raw_fields),
                    title=label.get("title") or _extract_title("PDS4", raw_fields),
                    file_type=label["file_type"],
                    fields=slimmed,
                )
            )

        return PDSGeoInspectCollectionsOutput(
            status="success",
            bundle_path=record["volume_dir"],
            collections=collections,
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
