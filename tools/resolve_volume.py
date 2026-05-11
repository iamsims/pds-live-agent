"""Resolve which child volume of a volume-set contains a target DATA_SET_ID.

Volume-sets on RMS (``COUVIS_0xxx``, ``COISS_2xxx``) and volume series on
ATM (``jnomwr_0xxx``/``jnomwr_1xxx``, ``MROM_0xxx``/``MROM_2xxx``,
``cocirs_NNNN``) contain many sibling volumes. Each volume's ``voldesc.cat``
declares one or more ``DATA_SET_ID``s, and *different* volumes within the
same set can declare *different* dataset IDs (e.g.
``jnomwr_0100V2`` → ``urn:nasa:pds:juno_mwr:data_raw``,
``jnomwr_1100V2`` → ``urn:nasa:pds:juno_mwr:data_calibrated``).

``pds_probe_datasets`` recurses at most ~5 subdirectories from a parent
path; on a 50-volume set it may sample only volumes that all share the
same dataset_id and miss the one the agent wants. This tool fills that
gap:

  1. List every child directory under the volume-set path (cheap, 1 HTTP).
  2. Order children by name (default), or — if ``dataset_id_hint`` is
     given — promote any child whose name fuzzy-matches the hint.
  3. Probe up to ``sample`` of those children for their ``DATA_SET_ID``s.
  4. Return a per-child mapping plus a ``best_match`` field that points to
     the first child whose dataset_ids contain ``dataset_id_hint`` (case
     and slash insensitive).

Designed as a thin orchestrator over ``pds_list_dataset_dirs`` +
``pds_probe_datasets`` — no new node-specific branching.
"""

from __future__ import annotations

from typing import Any

from loguru import logger
from pydantic import BaseModel, Field

from .client import PDSLiveClient, PDSLiveClientError, PDSPathNotFoundError
from .node_registry import get_base_url
from .parsers import parse_apache_directory
from .probe_datasets import _extract_dataset_ids


def _normalise(s: str) -> str:
    """Lowercase + strip slashes/underscores for fuzzy DATA_SET_ID match."""
    return "".join(ch for ch in s.lower() if ch.isalnum())


def _fuzzy_contains(haystack: str, needle: str) -> bool:
    return _normalise(needle) in _normalise(haystack)


class PDSResolveVolumeChild(BaseModel):
    """One child volume that was probed."""

    name: str = Field(description="Child directory name")
    path: str = Field(description="Path of the child relative to the node root")
    pds_version: str | None = Field(default=None, description="'PDS3' or 'PDS4' from the parsed label")
    dataset_ids: list[str] = Field(
        default_factory=list,
        description="All DATA_SET_IDs / logical_identifiers declared by this child's label",
    )
    volume_name: str | None = Field(default=None, description="PDS3 VOLUME_NAME if present")


class PDSResolveVolumeOutput(BaseModel):
    """Output for pds_resolve_volume."""

    status: str = Field(..., description="'success', 'not_found', or 'error'")
    volume_set_path: str = Field(..., description="The parent path that was resolved")
    total_children: int = Field(default=0, description="Number of child directories under the parent")
    sampled: int = Field(default=0, description="Number of children actually probed")
    children: list[PDSResolveVolumeChild] = Field(
        default_factory=list,
        description="Per-child probe results, in the order they were sampled",
    )
    best_match: str | None = Field(
        default=None,
        description="Path of the first child whose dataset_ids fuzzy-match dataset_id_hint (if provided)",
    )
    error: str | None = Field(default=None)


async def pds_resolve_volume(
    volume_set_path: str,
    *,
    node: str = "rms",
    dataset_id_hint: str | None = None,
    sample: int = 8,
    timeout: float = 30.0,
) -> PDSResolveVolumeOutput:
    """List a volume-set's children and probe a sample of their voldesc.cat
    labels to discover which child carries which DATA_SET_ID.

    Args:
        volume_set_path: Parent directory (e.g. ``holdings/volumes/COUVIS_0xxx/``
            on RMS, ``PDS/data/`` filtered to a series on ATM). May also be any
            mission/instrument directory whose children are leaf volumes.
        node: PDS node identifier.
        dataset_id_hint: Optional substring of the DATA_SET_ID you're looking
            for (e.g. ``"DDR"``, ``"calibrated"``, ``"CO-S-UVIS-2-SSB"``).
            Children whose name contains tokens from the hint are sampled
            first, and ``best_match`` is populated by fuzzy-matching the
            probed dataset_ids against this string.
        sample: Maximum number of children to probe (default 8; cap 20).
        timeout: HTTP timeout for each request.
    """
    sample = max(1, min(sample, 20))
    base_url = get_base_url(node)

    try:
        async with PDSLiveClient(base_url=base_url, timeout=timeout) as client:
            try:
                html = await client._fetch_text(client._resolve(volume_set_path, must_be_dir=True))
            except PDSPathNotFoundError as e:
                return PDSResolveVolumeOutput(
                    status="not_found",
                    volume_set_path=volume_set_path,
                    error=str(e),
                )

            child_urls, _files = parse_apache_directory(html, client._resolve(volume_set_path, must_be_dir=True))
            child_names: list[str] = []
            for u in child_urls:
                # Each entry is a fully-qualified URL of a subdirectory.
                name = u.rstrip("/").rsplit("/", 1)[-1]
                if name and name not in {"..", "."}:
                    child_names.append(name)

            total_children = len(child_names)
            if not child_names:
                return PDSResolveVolumeOutput(
                    status="success",
                    volume_set_path=volume_set_path,
                    total_children=0,
                    sampled=0,
                )

            # Order children: hint-matched names first (preserving original
            # order within each group), then everything else.
            ordered: list[str] = child_names[:]
            if dataset_id_hint:
                # Tokenise the hint on common DATA_SET_ID separators. Keep
                # only tokens of length ≥ 2 so single letters (e.g. "J", "M",
                # "V") don't blow up scoring on every child.
                import re as _re
                tokens = [t for t in _re.split(r"[^A-Za-z0-9]+", dataset_id_hint.lower()) if len(t) >= 2]

                def score(name: str) -> int:
                    nn = name.lower()
                    return sum(1 for t in tokens if t in nn)

                ordered = sorted(child_names, key=lambda n: (-score(n), n))

            sampled_names = ordered[:sample]

            children: list[PDSResolveVolumeChild] = []
            best_match: str | None = None
            for child_name in sampled_names:
                child_path = volume_set_path.rstrip("/") + "/" + child_name + "/"
                try:
                    record = await client.inspect_dataset(child_path)
                except (PDSPathNotFoundError, PDSLiveClientError) as e:
                    children.append(
                        PDSResolveVolumeChild(
                            name=child_name,
                            path=child_path,
                            dataset_ids=[],
                            volume_name=f"[unprobed: {e}]",
                        )
                    )
                    continue

                # Aggregate dataset_ids and version across all labels for this child
                ids: list[str] = []
                pds_version: str | None = None
                volume_name: str | None = None
                for lbl in record["labels"]:
                    if lbl["file_type"].startswith("collection"):
                        continue
                    ver = lbl["pds_version"]
                    pds_version = pds_version or ver
                    for did in _extract_dataset_ids(ver, lbl["fields"]):
                        if did not in ids:
                            ids.append(did)
                    if volume_name is None and ver == "PDS3":
                        vol = lbl["fields"].get("VOLUME") if isinstance(lbl["fields"], dict) else None
                        if isinstance(vol, dict):
                            vn = vol.get("VOLUME_NAME")
                            if isinstance(vn, str):
                                volume_name = vn

                child = PDSResolveVolumeChild(
                    name=child_name,
                    path=record.get("volume_dir", child_path),
                    pds_version=pds_version,
                    dataset_ids=ids,
                    volume_name=volume_name,
                )
                children.append(child)

                if best_match is None and dataset_id_hint:
                    for did in ids:
                        if _fuzzy_contains(did, dataset_id_hint):
                            best_match = child.path
                            break

            return PDSResolveVolumeOutput(
                status="success",
                volume_set_path=volume_set_path,
                total_children=total_children,
                sampled=len(children),
                children=children,
                best_match=best_match,
            )

    except Exception as e:
        logger.error(f"Unexpected error in pds_resolve_volume: {e}")
        return PDSResolveVolumeOutput(
            status="error",
            volume_set_path=volume_set_path,
            error=f"Internal error: {e}",
        )
