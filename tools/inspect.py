"""Inspect a single dataset on the live GEO node by parsing its label file(s)."""

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
)


class PDSGeoLabel(BaseModel):
    """One parsed label file (PDS3 voldesc or PDS4 bundle/collection XML)."""

    pds_version: str = Field(description="'PDS3' or 'PDS4'")
    file_type: str = Field(
        description=(
            "'voldesc.cat', 'voldesc.sfd' (PDS3); "
            "'bundle_xml', 'bundle_lblx', 'collection_xml', or 'collection_lblx' (PDS4)"
        ),
    )
    source_url: str = Field(description="Absolute URL of the parsed label file")
    title: str | None = Field(
        default=None,
        description=(
            "Human-readable title pulled from the label, when present. "
            "PDS4: Identification_Area.title. "
            "PDS3: VOLUME.VOLUME_SET_NAME (or VOLUME_NAME / DATA_SET_ID as fallback)."
        ),
    )
    fields: dict[str, Any] = Field(
        description="Parsed label fields. Mirrors the shape used by the offline GEO scraper.",
    )


class PDSGeoInspectDatasetOutput(BaseModel):
    """Output for pds_geo_inspect_dataset."""

    status: str = Field(..., description="'success', 'not_found', or 'invalid_input'")
    volume_dir: str | None = Field(None, description="Path of the volume/bundle relative to the GEO base URL")
    labels: list[PDSGeoLabel] = Field(
        default_factory=list,
        description=(
            "All label files found at the path. Hybrid volumes that ship both PDS3 and "
            "PDS4 labels return multiple entries; each entry stands alone."
        ),
    )
    error: str | None = Field(None, description="Error message when status is not 'success'")


async def pds_geo_inspect_dataset(
    path: str,
    *,
    base_url: str = GEO_BASE_URL,
    timeout: float = 30.0,
) -> PDSGeoInspectDatasetOutput:
    """Fetch and parse PDS label file(s) at a single GEO directory path.

    Recognises ``voldesc.cat``/``voldesc.sfd`` (PDS3),
    ``bundle_*.xml``/``bundle_*.lblx`` (PDS4 bundle), or
    ``collection_*.xml``/``collection_*.lblx`` (PDS4 collection). Does NOT
    recurse — to inspect collections inside a bundle, browse into its
    sub-directory and inspect that.
    """
    try:
        async with GEOLiveClient(base_url=base_url, timeout=timeout) as client:
            record = await client.inspect_dataset(path)

        return PDSGeoInspectDatasetOutput(
            status="success",
            volume_dir=record["volume_dir"],
            labels=[PDSGeoLabel(**label) for label in record["labels"]],
        )

    except GEOPathInvalidError as e:
        return PDSGeoInspectDatasetOutput(status="invalid_input", error=str(e))
    except GEOPathNotFoundError as e:
        return PDSGeoInspectDatasetOutput(status="not_found", error=str(e))
    except GEOLiveClientError as e:
        logger.error(f"GEO live client error: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in pds_geo_inspect_dataset: {e}")
        raise RuntimeError(f"Internal error inspecting GEO dataset: {e}") from e
