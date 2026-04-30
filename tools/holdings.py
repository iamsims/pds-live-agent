"""Search the GEO node's own published holdings index.

The GEO node maintains a single HTML page at
``https://pds-geosciences.wustl.edu/dataserv/holdings.html`` that lists every
archive on the site — both PDS3 DATA_SET_IDs and PDS4 bundle LIDs — paired
with a human-readable landing page URL. ~628 entries, ~313 KB. One HTTP GET
gets everything.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

from loguru import logger
from pydantic import BaseModel, Field
from rapidfuzz import fuzz

from .client import (
    GEO_BASE_URL,
    GEOLiveClient,
    GEOLiveClientError,
    GEOPathInvalidError,
    GEOPathNotFoundError,
)


HOLDINGS_PATH = "dataserv/holdings.html"


# A PDS3 DATA_SET_ID looks like ``MEX-M-HRSC-5-REFDR-DTM-V1.0`` or
# ``ARCB/NRAO-V-RTLS/GBT-3-DELAYDOPPLER-V1.0``.
_PDS3_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_/]*(-[A-Za-z0-9_/]+)+-V\d+(\.\d+)?$")

# Punctuation we strip when normalising a dataset ID for fuzzy scoring.
_NORMALISE_RE = re.compile(r"[^A-Za-z0-9]+")


def _normalise_for_search(s: str) -> str:
    return _NORMALISE_RE.sub(" ", s.lower()).strip()


# A PDS4 LID is ``urn:nasa:pds:<lid>``.
_PDS4_LID_RE = re.compile(r"^urn:nasa:pds:[A-Za-z0-9_]+(:[A-Za-z0-9_]+)*$", re.IGNORECASE)


_PDS3_MISSION_PREFIX_MAP: dict[str, str] = {
    "M2020": "m2020",
    "INSIGHT": "insight",
    "MSL": "msl",
    "MRO": "mro",
    "MER1": "mer",
    "MER2": "mer",
    "MEX": "mex",
    "ODY": "ody",
    "ODYSSEY": "ody",
    "PHX": "phx",
    "PHOENIX": "phx",
    "MGS": "mgs",
    "MPF": "mpf",
    "PATHFINDER": "mpf",
    "VG1": "viking",
    "VG2": "viking",
    "VL1": "viking",
    "VL2": "viking",
    "VO1": "viking",
    "VO2": "viking",
    "VIKING": "viking",
    "MARINER": "mariner",
    "MGN": "mgn",
    "MAGELLAN": "mgn",
    "PVO": "premgn",
    "MESSENGER": "messenger",
    "MESS": "messenger",
    "GRAIL": "grail",
    "LRO": "lro",
    "LP": "lunar",
    "LUNARP": "lunar",
    "CLEM1": "lunar",
    "CLEMENTINE": "lunar",
    "CH1": "lunar",
    "CH1-ORB": "lunar",
    "KAGUYA": "lunar",
    "MSX": "lunar",
    "APOLLO": "lunar",
    "ARCB": "lunar",
    "NEAR": "near",
    "EAR": "earth",
    "EARTH": "earth",
    "BUGLAB": "lab",
}

_PDS4_LID_MISSION_MAP: dict[str, str] = {
    "mars2020": "m2020",
    "insight": "insight",
    "msl": "msl",
    "mro": "mro",
    "mer": "mer",
    "mer1": "mer",
    "mer2": "mer",
    "mex": "mex",
    "magellan": "mgn",
    "mgn": "mgn",
    "mgs": "mgs",
    "mpf": "mpf",
    "phx": "phx",
    "lro": "lro",
    "lroc": "lro",
    "lola": "lro",
    "diviner": "lro",
    "grail": "grail",
    "messenger": "messenger",
    "near": "near",
    "venus": "venus",
}


class _HoldingsParser(HTMLParser):
    """Extract anchor (href, text) pairs from holdings.html."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._in_a = False
        self._cur_href: str | None = None
        self._buf: list[str] = []
        self.entries: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        for name, value in attrs:
            if name.lower() == "href" and value:
                self._cur_href = value
                self._in_a = True
                self._buf = []
                return

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or not self._in_a:
            return
        text = "".join(self._buf).strip()
        if self._cur_href and text:
            self.entries.append((self._cur_href, text))
        self._in_a = False
        self._cur_href = None
        self._buf = []

    def handle_data(self, data: str) -> None:
        if self._in_a:
            self._buf.append(data)


class HoldingsEntry(BaseModel):
    """One indexed dataset from holdings.html."""

    dataset_id: str = Field(description="Canonical PDS3 DATA_SET_ID or PDS4 logical_identifier")
    pds_version: str = Field(description="'PDS3' or 'PDS4'")
    landing_url: str = Field(description="Mission-page URL the holdings index points to (human-readable)")
    mission_hint: str | None = Field(
        default=None,
        description="Best-guess mission directory under https://pds-geosciences.wustl.edu/, or None if unknown",
    )


def parse_holdings_page(html: str) -> list[HoldingsEntry]:
    """Parse the GEO holdings page into a deduplicated list of entries."""
    parser = _HoldingsParser()
    parser.feed(html)

    seen_ids: set[str] = set()
    out: list[HoldingsEntry] = []
    for href, text in parser.entries:
        norm = text.strip()
        if _PDS3_ID_RE.match(norm):
            dataset_id = norm.upper()
            pds_version = "PDS3"
        elif _PDS4_LID_RE.match(norm):
            dataset_id = norm.lower()
            pds_version = "PDS4"
        else:
            continue
        if dataset_id in seen_ids:
            continue
        seen_ids.add(dataset_id)
        out.append(
            HoldingsEntry(
                dataset_id=dataset_id,
                pds_version=pds_version,
                landing_url=href,
                mission_hint=_mission_hint_for(dataset_id, pds_version),
            )
        )
    return out


def _mission_hint_for(dataset_id: str, pds_version: str) -> str | None:
    """Best-guess mission directory under the GEO base URL, or None."""
    if pds_version == "PDS3":
        first_seg = re.split(r"[-/]", dataset_id, maxsplit=1)[0].upper()
        return _PDS3_MISSION_PREFIX_MAP.get(first_seg)
    if pds_version == "PDS4":
        suffix = dataset_id[len("urn:nasa:pds:") :]
        first_word = suffix.split("_", 1)[0].split(":", 1)[0].lower()
        return _PDS4_LID_MISSION_MAP.get(first_word)
    return None


# ---------------------------------------------------------------------------
# Module-level cache: one fetch per process is enough for ~313 KB
# ---------------------------------------------------------------------------

_HOLDINGS_CACHE: list[HoldingsEntry] | None = None


async def _load_holdings_cached(client: GEOLiveClient) -> list[HoldingsEntry]:
    global _HOLDINGS_CACHE
    if _HOLDINGS_CACHE is not None:
        return _HOLDINGS_CACHE
    url = client.base_url + HOLDINGS_PATH
    html = await client._fetch_text(url)
    _HOLDINGS_CACHE = parse_holdings_page(html)
    return _HOLDINGS_CACHE


def _reset_cache() -> None:
    """Clear the in-process cache. Used by tests."""
    global _HOLDINGS_CACHE
    _HOLDINGS_CACHE = None


# ---------------------------------------------------------------------------
# Tool function
# ---------------------------------------------------------------------------


class PDSGeoHoldingsItem(BaseModel):
    """One scored entry returned from search_holdings."""

    dataset_id: str = Field(description="Canonical PDS3 DATA_SET_ID or PDS4 logical_identifier")
    pds_version: str = Field(description="'PDS3' or 'PDS4'")
    mission_hint: str | None = Field(
        default=None,
        description="Best-guess top-level mission directory on the GEO node, or None",
    )
    score: float = Field(description="Match score 0–100 (rapidfuzz token_set_ratio)")


class PDSGeoSearchHoldingsOutput(BaseModel):
    """Output for pds_geo_search_holdings."""

    status: str = Field(..., description="'success' or 'error'")
    total_in_index: int = Field(..., description="Total entries parsed from holdings.html")
    count: int = Field(..., description="Number of items returned")
    items: list[PDSGeoHoldingsItem] = Field(default_factory=list)
    error: str | None = Field(None, description="Error message when status is not 'success'")


async def pds_geo_search_holdings(
    query: str,
    limit: int = 20,
    *,
    base_url: str = GEO_BASE_URL,
    timeout: float = 30.0,
    min_score: float = 60.0,
) -> PDSGeoSearchHoldingsOutput:
    """Fuzzy-search the GEO node's published holdings index for dataset IDs.

    Fetches the holdings page once (cached in process) and returns the
    canonical dataset IDs whose text best matches the query, with a best-guess
    mission directory.
    """
    limit = max(1, min(50, limit))

    try:
        async with GEOLiveClient(base_url=base_url, timeout=timeout) as client:
            entries = await _load_holdings_cached(client)
    except (GEOPathInvalidError, GEOPathNotFoundError) as e:
        return PDSGeoSearchHoldingsOutput(status="error", total_in_index=0, count=0, error=str(e))
    except GEOLiveClientError as e:
        logger.error(f"GEO live client error fetching holdings: {e}")
        raise

    q = query.strip()
    if not q:
        return PDSGeoSearchHoldingsOutput(status="success", total_in_index=len(entries), count=0, items=[])

    q_norm = _normalise_for_search(q)
    scored: list[tuple[float, HoldingsEntry]] = []
    for entry in entries:
        id_norm = _normalise_for_search(entry.dataset_id)
        score = float(fuzz.token_set_ratio(q_norm, id_norm))
        if score >= min_score:
            scored.append((score, entry))
    scored.sort(key=lambda p: p[0], reverse=True)

    items = [
        PDSGeoHoldingsItem(
            dataset_id=e.dataset_id,
            pds_version=e.pds_version,
            mission_hint=e.mission_hint,
            score=score,
        )
        for score, e in scored[:limit]
    ]
    return PDSGeoSearchHoldingsOutput(
        status="success",
        total_in_index=len(entries),
        count=len(items),
        items=items,
    )
