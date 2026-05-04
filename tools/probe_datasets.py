"""Probe dataset directories for PDS labels, recursing until leaf nodes.

A 'leaf node' is a directory that contains a PDS3 voldesc.cat/sfd or a
PDS4 bundle*.xml/lblx file. When a given path has no labels, the tool
recurses one level into its subdirectories (to handle the PDS3 nesting
pattern where the volume sits inside a subdirectory).

Accepts a list of paths so the agent can batch multiple probes in one call.
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


# ---------------------------------------------------------------------------
# Field slimming — keep only what the agent needs
# ---------------------------------------------------------------------------

_PDS3_VOLUME_KEEP = {
    "DATA_SET_ID",
    "VOLUME_SET_NAME",
    "VOLUME_NAME",
    "VOLUME_ID",
    "PUBLICATION_DATE",
    "DESCRIPTION",
}


def _slim_pds3_fields(fields: dict[str, Any]) -> dict[str, Any]:
    """Keep only the fields the agent needs from a parsed PDS3 voldesc."""
    out: dict[str, Any] = {}
    if "PDS_VERSION_ID" in fields:
        out["PDS_VERSION_ID"] = fields["PDS_VERSION_ID"]
    if "DATA_SET_ID" in fields:
        out["DATA_SET_ID"] = fields["DATA_SET_ID"]
    volume = fields.get("VOLUME")
    if isinstance(volume, dict):
        out["VOLUME"] = {k: v for k, v in volume.items() if k in _PDS3_VOLUME_KEEP}
    return out


def _slim_pds4_fields(fields: dict[str, Any]) -> dict[str, Any]:
    """Keep only Identification_Area from a parsed PDS4 XML label, sans Modification_History."""
    out: dict[str, Any] = {}
    ia = fields.get("Identification_Area")
    if ia is not None:
        if isinstance(ia, dict):
            ia = {k: v for k, v in ia.items() if k != "Modification_History"}
        out["Identification_Area"] = ia
    return out


def _extract_dataset_id(pds_version: str, fields: dict[str, Any]) -> str | None:
    """Extract the canonical dataset identifier from parsed label fields."""
    if pds_version == "PDS3":
        # Try VOLUME.DATA_SET_ID first, then top-level DATA_SET_ID
        volume = fields.get("VOLUME")
        if isinstance(volume, dict):
            dsid = volume.get("DATA_SET_ID")
            if isinstance(dsid, str) and dsid.strip():
                return dsid.strip()
        top_dsid = fields.get("DATA_SET_ID")
        if isinstance(top_dsid, str) and top_dsid.strip():
            return top_dsid.strip()
        return None

    if pds_version == "PDS4":
        ia = fields.get("Identification_Area")
        if isinstance(ia, dict):
            lid = ia.get("logical_identifier")
            if isinstance(lid, str) and lid.strip():
                return lid.strip()
        return None

    return None


# ---------------------------------------------------------------------------
# Output models
# ---------------------------------------------------------------------------


class PDSGeoProbeResult(BaseModel):
    """One probed dataset directory with its parsed label metadata."""

    path: str = Field(description="Directory path relative to GEO root where the label was found")
    pds_version: str = Field(description="'PDS3' or 'PDS4'")
    file_type: str = Field(
        description=(
            "'voldesc.cat', 'voldesc.sfd' (PDS3); "
            "'bundle_xml', 'bundle_lblx' (PDS4)"
        ),
    )
    dataset_id: str | None = Field(
        default=None,
        description="PDS3: VOLUME.DATA_SET_ID; PDS4: Identification_Area.logical_identifier",
    )
    title: str | None = Field(default=None, description="Human-readable title from the label")
    fields: dict[str, Any] = Field(description="Slimmed parsed label fields")


class PDSGeoProbeError(BaseModel):
    """One path that could not be probed."""

    path: str = Field(description="The path that was requested")
    error: str = Field(description="Why the probe failed")


class PDSGeoProbeDatasetsOutput(BaseModel):
    """Output for pds_geo_probe_datasets."""

    status: str = Field(..., description="'success' or 'error'")
    results: list[PDSGeoProbeResult] = Field(
        default_factory=list,
        description="Leaf-node labels found (one entry per label file; hybrid dirs produce multiple entries)",
    )
    errors: list[PDSGeoProbeError] = Field(
        default_factory=list,
        description="Paths that could not be probed (404, invalid path, etc.)",
    )
    error: str | None = Field(None, description="Top-level error message if the entire probe failed")


# ---------------------------------------------------------------------------
# Tool function
# ---------------------------------------------------------------------------


async def pds_geo_probe_datasets(
    paths: list[str],
    *,
    base_url: str = GEO_BASE_URL,
    timeout: float = 30.0,
) -> PDSGeoProbeDatasetsOutput:
    """Probe one or more dataset directories for PDS labels.

    For each path, fetches the directory listing and looks for leaf-node
    label files (``voldesc.cat``/``voldesc.sfd`` for PDS3,
    ``bundle_*.xml``/``bundle_*.lblx`` for PDS4).

    If no labels are found at a given path, recurses one level into its
    subdirectories (up to 3) to handle PDS3's nested volume pattern.

    Hybrid directories that contain both PDS3 and PDS4 labels produce
    multiple result entries.

    Returns parsed metadata including dataset_id, title, and slimmed fields.
    """
    if not paths:
        return PDSGeoProbeDatasetsOutput(status="success")

    # Cap the number of paths to prevent abuse
    paths = paths[:20]

    results: list[PDSGeoProbeResult] = []
    errors: list[PDSGeoProbeError] = []

    try:
        async with GEOLiveClient(base_url=base_url, timeout=timeout) as client:
            for path in paths:
                try:
                    record = await client.inspect_dataset(path)
                    for label in record["labels"]:
                        pds_version = label["pds_version"]
                        raw_fields = label["fields"]

                        # Only include bundle-level and voldesc labels, not collections
                        ft = label["file_type"]
                        if ft.startswith("collection"):
                            continue

                        # Slim the fields
                        if pds_version == "PDS3":
                            slimmed = _slim_pds3_fields(raw_fields)
                        else:
                            slimmed = _slim_pds4_fields(raw_fields)

                        results.append(
                            PDSGeoProbeResult(
                                path=label.get("volume_dir", record["volume_dir"]),
                                pds_version=pds_version,
                                file_type=ft,
                                dataset_id=_extract_dataset_id(pds_version, raw_fields),
                                title=label.get("title") or _extract_title(pds_version, raw_fields),
                                fields=slimmed,
                            )
                        )

                except GEOPathInvalidError as e:
                    errors.append(PDSGeoProbeError(path=path, error=str(e)))
                except GEOPathNotFoundError as e:
                    errors.append(PDSGeoProbeError(path=path, error=str(e)))
                except GEOLiveClientError as e:
                    errors.append(PDSGeoProbeError(path=path, error=str(e)))

    except Exception as e:
        logger.error(f"Unexpected error in pds_geo_probe_datasets: {e}")
        return PDSGeoProbeDatasetsOutput(
            status="error",
            results=results,
            errors=errors,
            error=f"Internal error: {e}",
        )

    return PDSGeoProbeDatasetsOutput(
        status="success",
        results=results,
        errors=errors,
    )
