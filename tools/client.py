"""Async HTTP client for the live GEO node directory at pds-geosciences.wustl.edu."""

from __future__ import annotations

import asyncio
import xml.etree.ElementTree as ET
from types import TracebackType
from typing import Any
from urllib.parse import urlsplit

import httpx

from .parsers import (
    filename_from_url,
    parse_apache_directory,
    parse_voldesc_full,
    xml_to_dict,
)


GEO_BASE_URL = "https://pds-geosciences.wustl.edu/"


class GEOLiveClientError(Exception):
    """Base exception for GEO live client errors."""


class GEOPathNotFoundError(GEOLiveClientError):
    """Raised when a requested path returns 404."""


class GEOPathInvalidError(GEOLiveClientError):
    """Raised when the caller-supplied path is malformed or escapes the base URL."""


def _normalize_relative_path(path: str, *, must_be_dir: bool = False) -> str:
    """Validate a caller-supplied relative path and return its canonical form.

    Rejects absolute paths, schemes, ``..`` segments, and backslashes — anything
    that could escape the GEO base URL.
    """
    raw = path.strip()
    if not raw:
        return ""

    if "://" in raw or raw.startswith("//"):
        raise GEOPathInvalidError(f"Path must be relative to {GEO_BASE_URL}, got: {raw!r}")
    if raw.startswith("/"):
        raw = raw.lstrip("/")
    if "\\" in raw:
        raise GEOPathInvalidError(f"Backslashes are not allowed in path: {raw!r}")

    segments = [seg for seg in raw.split("/") if seg != ""]
    for seg in segments:
        if seg in (".", ".."):
            raise GEOPathInvalidError(f"Path may not contain '.' or '..' segments: {raw!r}")

    cleaned = "/".join(segments)
    if must_be_dir and cleaned and not raw.endswith("/"):
        cleaned += "/"
    elif raw.endswith("/") and cleaned:
        cleaned += "/"
    return cleaned


class GEOLiveClient:
    """Async client for the GEO node directory tree.

    Use as an async context manager:

        async with GEOLiveClient() as client:
            dirs, files = await client.list_directory("<mission>/")
            metadata = await client.inspect_dataset("<mission>/<bundle_or_volume>/")
    """

    def __init__(
        self,
        base_url: str = GEO_BASE_URL,
        timeout: float = 30.0,
        max_bytes: int = 4 * 1024 * 1024,
    ) -> None:
        self.base_url = base_url if base_url.endswith("/") else base_url + "/"
        self.timeout = timeout
        self.max_bytes = max_bytes
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "GEOLiveClient":
        self._client = httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=True,
            headers={
                "User-Agent": "akd-ext-pds-geo-live/0.1",
                "Accept": "text/html,application/xml;q=0.9,*/*;q=0.8",
            },
        )
        return self

    async def __aexit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc_val: BaseException | None,
        _exc_tb: TracebackType | None,
    ) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise GEOLiveClientError("GEOLiveClient must be used as an async context manager")
        return self._client

    def _resolve(self, relative_path: str, *, must_be_dir: bool = False) -> str:
        cleaned = _normalize_relative_path(relative_path, must_be_dir=must_be_dir)
        return self.base_url + cleaned

    async def _fetch_text(self, url: str) -> str:
        client = self._ensure_client()
        try:
            response = await client.get(url)
        except httpx.HTTPError as e:
            raise GEOLiveClientError(f"HTTP error fetching {url}: {e}") from e

        if response.status_code == 404:
            raise GEOPathNotFoundError(f"Not found: {url}")
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise GEOLiveClientError(f"HTTP {response.status_code} fetching {url}: {e}") from e

        content = response.content
        if len(content) > self.max_bytes:
            raise GEOLiveClientError(f"Response from {url} is {len(content)} bytes, exceeds max_bytes={self.max_bytes}")
        return response.text

    # ------------------------------------------------------------------
    # Tool 1: list a directory
    # ------------------------------------------------------------------

    async def list_directory(self, relative_path: str) -> tuple[list[str], list[str]]:
        """Fetch an Apache index page and return (dir_urls, file_urls)."""
        url = self._resolve(relative_path, must_be_dir=True)
        html = await self._fetch_text(url)
        return parse_apache_directory(html, url)

    # ------------------------------------------------------------------
    # Tool 2: inspect a dataset (PDS3 voldesc.cat or PDS4 bundle XML)
    # ------------------------------------------------------------------

    async def inspect_dataset(self, relative_path: str) -> dict[str, Any]:
        """Find and parse every PDS label file at a single directory path.

        Recognised label files (one HTTP request per file matched):
        - PDS3: ``voldesc.cat``, ``voldesc.sfd``
        - PDS4 bundles: ``bundle_*.xml``, ``bundle_*.lblx``
        - PDS4 collections: ``collection_*.xml``, ``collection_*.lblx``

        When no labels are found at the given path, recurses one level down
        into **all** subdirectories — PDS3 datasets on GEO typically nest the
        volume (with ``voldesc.cat``) inside a subdirectory (e.g.
        ``mex-m-hrsc-5-refdr-dtm-v1/mexhrs_2001/voldesc.cat``).

        Hybrid volumes that ship both PDS3 and PDS4 labels return one entry per label.

        Returns:
            ``{"volume_dir": str, "labels": [{"pds_version", "file_type", "source_url", "fields", "volume_dir"}, ...]}``.
            Each label carries its own ``volume_dir`` so that results from
            multiple subdirectories are correctly attributed. The top-level
            ``volume_dir`` is from the first label.

        Raises:
            GEOPathNotFoundError: If no label file can be located in the directory
                or its immediate subdirectories.
        """
        url = self._resolve(relative_path, must_be_dir=True)
        html = await self._fetch_text(url)
        dirs, files = parse_apache_directory(html, url)

        labels = await self._parse_labels_from_files(files)

        # Tag each label with its volume_dir
        if labels:
            vdir = _volume_dir_from_url(labels[0]["source_url"], self.base_url)
            for lbl in labels:
                lbl["volume_dir"] = vdir

        # Fallback: if no labels at this level, try one level down into
        # ALL subdirectories to find every leaf node.
        if not labels and dirs:
            base_path = urlsplit(self.base_url).path
            if not base_path.endswith("/"):
                base_path += "/"

            for d_url in dirs:
                target_path = urlsplit(d_url).path
                sub_relative = (
                    target_path[len(base_path):]
                    if target_path.startswith(base_path)
                    else target_path.lstrip("/")
                )
                try:
                    sub_url = self._resolve(sub_relative, must_be_dir=True)
                    sub_html = await self._fetch_text(sub_url)
                    _, sub_files = parse_apache_directory(sub_html, sub_url)
                    sub_labels = await self._parse_labels_from_files(sub_files)
                    if sub_labels:
                        vdir = _volume_dir_from_url(sub_labels[0]["source_url"], self.base_url)
                        for lbl in sub_labels:
                            lbl["volume_dir"] = vdir
                        labels.extend(sub_labels)
                except (GEOPathNotFoundError, GEOLiveClientError):
                    continue

        if not labels:
            raise GEOPathNotFoundError(
                f"No voldesc.cat/voldesc.sfd, bundle_*.xml/.lblx, or collection_*.xml/.lblx found at {url}"
            )

        return {
            "volume_dir": labels[0]["volume_dir"],
            "labels": labels,
        }

    async def _parse_labels_from_files(self, files: list[str]) -> list[dict[str, Any]]:
        """Parse PDS label files from a list of file URLs.

        Fetches and parses voldesc.cat/sfd (PDS3) and bundle/collection XML/lblx (PDS4).
        """
        file_map = {filename_from_url(f).lower(): f for f in files}
        labels: list[dict[str, Any]] = []

        for voldesc_name in ("voldesc.cat", "voldesc.sfd"):
            if voldesc_name in file_map:
                target_url = file_map[voldesc_name]
                content = await self._fetch_text(target_url)
                fields = parse_voldesc_full(content)
                labels.append(
                    {
                        "pds_version": "PDS3",
                        "file_type": voldesc_name,
                        "source_url": target_url,
                        "fields": fields,
                        "title": _extract_title("PDS3", fields),
                    }
                )

        for fname, furl in file_map.items():
            is_xml = fname.endswith(".xml") or fname.endswith(".lblx")
            is_bundle = fname.startswith("bundle")
            is_collection = fname.startswith("collection")
            if not is_xml or not (is_bundle or is_collection):
                continue
            content = await self._fetch_text(furl)
            try:
                parsed = xml_to_dict(content)
            except ET.ParseError as e:
                raise GEOLiveClientError(f"Failed to parse XML at {furl}: {e}") from e
            fields = parsed
            if len(parsed) == 1:
                inner = next(iter(parsed.values()))
                if isinstance(inner, dict):
                    fields = inner
            kind = "bundle" if is_bundle else "collection"
            ext = "lblx" if fname.endswith(".lblx") else "xml"
            labels.append(
                {
                    "pds_version": "PDS4",
                    "file_type": f"{kind}_{ext}",
                    "source_url": furl,
                    "fields": fields,
                    "title": _extract_title("PDS4", fields),
                }
            )

        return labels

    # ------------------------------------------------------------------
    # Tool 4: inspect a PDS4 bundle and one level of its collections
    # ------------------------------------------------------------------

    # Sub-dirs that PDS4 bundles use for non-data content. Skipped when
    # walking a bundle for collections (mirrors scrape_geo_data.PDS4_SKIP_DIRS).
    PDS4_SKIP_SUBDIRS: set[str] = {"document", "index", "catalog", "browse", "checksums"}

    async def inspect_with_pds4_collections(
        self,
        relative_path: str,
        max_subdirs: int = 20,
        concurrency: int = 10,
    ) -> dict[str, Any]:
        """Inspect a path AND, when a PDS4 bundle is present, also fetch one level of collections.

        Workflow:
          1. ``inspect_dataset(path)`` — gets PDS3 voldescs / PDS4 bundles at this path.
          2. If any PDS4 bundle was found, browse the same directory's
             sub-dirs (skipping ``document/``/``index/``/``catalog/``/``browse/``/``calibration/``)
             and inspect each for ``collection_*.xml/.lblx`` labels.
          3. Return the bundle labels and the collection labels separately.

        This is the on-demand equivalent of the offline scraper's
        ``_scan_for_collections`` step.

        Args:
            relative_path: Bundle directory path on the GEO node.
            max_subdirs: Cap on sub-dirs to walk for collections. Default 20.
            concurrency: Max concurrent collection-label fetches. Default 10.

        Returns:
            ``{
                "volume_dir": str,
                "labels": [bundle/voldesc labels at the input path],
                "collections": [collection labels found one level deeper],
            }``.

        Raises:
            GEOPathNotFoundError: If no labels at all are found at the input path.
        """
        record = await self.inspect_dataset(relative_path)
        bundle_labels = record["labels"]

        has_pds4_bundle = any(
            label["pds_version"] == "PDS4" and label["file_type"].startswith("bundle") for label in bundle_labels
        )

        collection_labels: list[dict[str, Any]] = []
        if has_pds4_bundle:
            url = self._resolve(relative_path, must_be_dir=True)
            html = await self._fetch_text(url)
            dir_urls, _files = parse_apache_directory(html, url)

            base_path = urlsplit(self.base_url).path
            if not base_path.endswith("/"):
                base_path += "/"

            candidate_paths: list[str] = []
            for d_url in dir_urls:
                name = filename_from_url(d_url).lower()
                if name in self.PDS4_SKIP_SUBDIRS:
                    continue
                target_path = urlsplit(d_url).path
                relative = (
                    target_path[len(base_path) :] if target_path.startswith(base_path) else target_path.lstrip("/")
                )
                candidate_paths.append(relative)
                if len(candidate_paths) >= max_subdirs:
                    break

            sem = asyncio.Semaphore(concurrency)

            async def _scan_collection(sub_path: str) -> list[dict[str, Any]]:
                async with sem:
                    try:
                        sub_record = await self.inspect_dataset(sub_path)
                    except (GEOPathNotFoundError, GEOLiveClientError):
                        return []
                    except Exception:  # noqa: BLE001
                        return []
                return [label for label in sub_record["labels"] if label["file_type"].startswith("collection")]

            sub_results = await asyncio.gather(*[_scan_collection(p) for p in candidate_paths])
            for collected in sub_results:
                collection_labels.extend(collected)

        return {
            "volume_dir": record["volume_dir"],
            "labels": bundle_labels,
            "collections": collection_labels,
        }

    # ------------------------------------------------------------------
    # Tool 3: scan a parent directory and harvest each subdir's title
    # ------------------------------------------------------------------

    async def scan_with_titles(
        self,
        parent_path: str,
        max_subdirs: int = 30,
        concurrency: int = 10,
    ) -> dict[str, Any]:
        """List a directory and pull each immediate sub-directory's first label title.

        For each sub-directory we attempt one inspect_dataset() and harvest just
        the first label's title / pds_version / file_type. Sub-dirs without a
        label (e.g. pure organisational dirs) come back with title=None.

        Args:
            parent_path: Path to scan (e.g. "mex/" or "" for the root).
            max_subdirs: Cap on subdirs to inspect; protects against huge mission dirs.
            concurrency: Max in-flight label fetches.

        Returns:
            ``{"parent_url", "total_subdirs", "scanned_count", "items": [
                {"path", "url", "title", "pds_version", "file_type"}, ...
            ]}``.
        """
        parent_url = self._resolve(parent_path, must_be_dir=True)
        html = await self._fetch_text(parent_url)
        dir_urls, _files = parse_apache_directory(html, parent_url)

        total = len(dir_urls)
        targets = dir_urls[:max_subdirs]
        sem = asyncio.Semaphore(concurrency)
        base_path = urlsplit(self.base_url).path
        if not base_path.endswith("/"):
            base_path += "/"

        async def _scan_one(d_url: str) -> dict[str, Any]:
            target_path = urlsplit(d_url).path
            relative = target_path[len(base_path) :] if target_path.startswith(base_path) else target_path.lstrip("/")
            item: dict[str, Any] = {
                "path": relative,
                "url": d_url,
                "title": None,
                "pds_version": None,
                "file_type": None,
            }
            async with sem:
                try:
                    record = await self.inspect_dataset(relative)
                except (GEOPathNotFoundError, GEOLiveClientError):
                    return item
                except Exception:  # noqa: BLE001 - one bad subdir shouldn't kill the scan
                    return item
            labels = record.get("labels", [])
            if labels:
                first = labels[0]
                item["title"] = first.get("title")
                item["pds_version"] = first.get("pds_version")
                item["file_type"] = first.get("file_type")
            return item

        items = await asyncio.gather(*[_scan_one(u) for u in targets])
        return {
            "parent_url": parent_url,
            "total_subdirs": total,
            "scanned_count": len(items),
            "items": items,
        }


def _extract_title(pds_version: str, fields: dict[str, Any]) -> str | None:
    """Pull a human-readable title out of the parsed label fields.

    PDS4 (bundle / collection): ``Identification_Area.title``.
    PDS3 voldesc: ``VOLUME.VOLUME_SET_NAME`` -> ``VOLUME.VOLUME_NAME`` -> ``VOLUME.DATA_SET_ID``.
    Returns None if nothing useful is present.
    """
    if pds_version == "PDS4":
        ia = fields.get("Identification_Area")
        if isinstance(ia, dict):
            title = ia.get("title")
            if isinstance(title, str) and title.strip():
                return title.strip()
        return None

    if pds_version == "PDS3":
        volume = fields.get("VOLUME")
        if isinstance(volume, dict):
            for key in ("VOLUME_SET_NAME", "VOLUME_NAME", "DATA_SET_ID"):
                value = volume.get(key)
                if isinstance(value, str) and value.strip() and value.strip().upper() not in {"NULL", "N/A", "UNK"}:
                    return value.strip()
        # Some voldescs put DATA_SET_ID at the top level
        top_dsid = fields.get("DATA_SET_ID")
        if isinstance(top_dsid, str) and top_dsid.strip():
            return top_dsid.strip()
        return None

    return None


def _volume_dir_from_url(url: str, base_url: str) -> str:
    base_path = urlsplit(base_url).path
    if not base_path.endswith("/"):
        base_path += "/"
    target_path = urlsplit(url).path
    if target_path.startswith(base_path):
        relative = target_path[len(base_path) :]
    else:
        relative = target_path.lstrip("/")
    parts = relative.rsplit("/", 1)
    return parts[0] if len(parts) > 1 else ""
