"""Parsers for the GEO node: Apache directory listings, PDS3 voldesc.cat, PDS4 XML.

These mirror the parsers used by the offline GEO scraper so that a record
fetched live has the same field shape as the corresponding row in
`scraped_data/geo_catalog.jsonl`.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from typing import Any
from urllib.parse import unquote, urljoin, urlsplit


# ---------------------------------------------------------------------------
# Apache directory listing parser
# ---------------------------------------------------------------------------


class _ApacheIndexParser(HTMLParser):
    """Collects href targets from an Apache mod_autoindex page."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        for name, value in attrs:
            if name.lower() == "href" and value:
                self.hrefs.append(value)
                return


def parse_apache_directory(html: str, base_url: str) -> tuple[list[str], list[str]]:
    """Parse an Apache directory listing into (subdirectories, files).

    Both lists contain absolute URLs resolved against ``base_url``. Apache's
    sort-column links (``?C=N;O=D``), the parent-directory link, and any
    off-host links are filtered out.
    """
    parser = _ApacheIndexParser()
    parser.feed(html)

    base_host = urlsplit(base_url).netloc
    base_path = urlsplit(base_url).path
    if not base_path.endswith("/"):
        base_path += "/"

    dirs: list[str] = []
    files: list[str] = []
    seen: set[str] = set()

    for href in parser.hrefs:
        # Sort-column toggles like "?C=N;O=D"
        if href.startswith("?"):
            continue
        # Parent-directory link
        if href in ("../", "..", "/"):
            continue

        absolute = urljoin(base_url, href)
        split = urlsplit(absolute)

        # Stay on the same host
        if split.netloc and split.netloc != base_host:
            continue
        # Stay under the current directory (avoid breadcrumbs to parent)
        if not split.path.startswith(base_path):
            continue
        # Skip self-link (the directory itself)
        if split.path == base_path:
            continue

        # Strip query and fragment for the canonical entry URL
        canonical = f"{split.scheme}://{split.netloc}{split.path}"
        if canonical in seen:
            continue
        seen.add(canonical)

        if canonical.endswith("/"):
            dirs.append(canonical)
        else:
            files.append(canonical)

    return dirs, files


def filename_from_url(url: str) -> str:
    """Return the trailing path segment (file or dir name) of a URL, URL-decoded."""
    path = urlsplit(url).path.rstrip("/")
    if not path:
        return ""
    return unquote(path.rsplit("/", 1)[-1])


# ---------------------------------------------------------------------------
# PDS3 voldesc.cat parser
# ---------------------------------------------------------------------------


def parse_voldesc_full(content: str) -> dict[str, Any]:
    """Parse all key-value pairs from a PDS3 ``voldesc.cat`` file.

    Handles simple ``KEY = VALUE`` pairs, multi-line quoted values, nested
    ``OBJECT``/``END_OBJECT`` blocks (as nested dicts), and set values like
    ``{"REF.CAT", "PROJREF.CAT"}`` (as lists).
    """
    if not content or not content.strip():
        return {}

    lines = content.splitlines()
    result: dict[str, Any] = {}
    stack: list[dict[str, Any]] = [result]
    i = 0

    while i < len(lines):
        stripped = lines[i].strip()

        if not stripped or stripped.startswith("/*"):
            if stripped.startswith("/*"):
                while i < len(lines) and "*/" not in lines[i]:
                    i += 1
            i += 1
            continue

        if stripped == "END":
            i += 1
            continue

        obj_match = re.match(r"^\s*OBJECT\s*=\s*(\S+)", stripped)
        if obj_match:
            obj_name = obj_match.group(1).strip()
            new_obj: dict[str, Any] = {}
            stack[-1][obj_name] = new_obj
            stack.append(new_obj)
            i += 1
            continue

        if re.match(r"^\s*END_OBJECT", stripped):
            if len(stack) > 1:
                stack.pop()
            i += 1
            continue

        kv_match = re.match(r"^\s*(\^?[A-Z_][A-Z0-9_]*)\s*=\s*(.*)", stripped)
        if kv_match:
            key = kv_match.group(1).strip()
            value_part = kv_match.group(2).strip()
            value, i = _parse_value(value_part, lines, i)
            stack[-1][key] = value
            i += 1
            continue

        i += 1

    return result


def _parse_value(value_part: str, lines: list[str], line_idx: int) -> tuple[Any, int]:
    if value_part.startswith("{"):
        return _parse_set_value(value_part, lines, line_idx)
    if value_part.startswith('"'):
        return _parse_quoted_value(value_part, lines, line_idx)
    if value_part.startswith("("):
        return _parse_paren_value(value_part, lines, line_idx)

    comment_idx = value_part.find("/*")
    if comment_idx >= 0:
        value_part = value_part[:comment_idx].strip()
    return value_part.strip(), line_idx


def _parse_quoted_value(value_part: str, lines: list[str], line_idx: int) -> tuple[str, int]:
    text = value_part[1:]
    close_idx = text.find('"')
    if close_idx >= 0:
        return text[:close_idx], line_idx

    parts = [text]
    i = line_idx + 1
    while i < len(lines):
        line = lines[i]
        close_idx = line.find('"')
        if close_idx >= 0:
            parts.append(line[:close_idx])
            full = " ".join(parts)
            return re.sub(r"\s+", " ", full).strip(), i
        parts.append(line)
        i += 1

    return re.sub(r"\s+", " ", " ".join(parts)).strip(), i - 1


def _parse_set_value(value_part: str, lines: list[str], line_idx: int) -> tuple[list[str], int]:
    text = value_part
    i = line_idx
    while "}" not in text and i + 1 < len(lines):
        i += 1
        text += " " + lines[i].strip()

    brace_content = text[text.find("{") + 1 : text.find("}")]
    return [item.strip().strip('"') for item in brace_content.split(",") if item.strip().strip('"')], i


def _parse_paren_value(value_part: str, lines: list[str], line_idx: int) -> tuple[list[str], int]:
    text = value_part
    i = line_idx
    while ")" not in text and i + 1 < len(lines):
        i += 1
        text += " " + lines[i].strip()

    paren_content = text[text.find("(") + 1 : text.find(")")]
    return [item.strip().strip('"') for item in paren_content.split(",") if item.strip().strip('"')], i


# ---------------------------------------------------------------------------
# PDS4 XML parser
# ---------------------------------------------------------------------------


def xml_to_dict(xml_content: str) -> dict[str, Any]:
    """Recursively convert PDS4 XML into a nested dict.

    PDS4 namespace prefixes are stripped. Repeated child tags become lists,
    attributes are preserved as ``@name`` keys.
    """
    xml_content = xml_content.lstrip("\ufeff").strip()
    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError:
        if xml_content.startswith("<?"):
            decl_end = xml_content.find("?>")
            if decl_end > 0:
                root = ET.fromstring(xml_content[decl_end + 2 :].strip())
            else:
                raise
        else:
            raise

    return _element_to_dict(root)


def _strip_namespace(tag: str) -> str:
    if tag.startswith("{"):
        return tag.split("}", 1)[1]
    return tag


def _element_to_dict(element: ET.Element) -> dict[str, Any]:
    tag = _strip_namespace(element.tag)
    result: dict[str, Any] = {f"@{_strip_namespace(k)}": v for k, v in element.attrib.items()}
    children = list(element)

    if not children:
        text = (element.text or "").strip()
        if result:
            if text:
                result["#text"] = text
            return {tag: result}
        return {tag: text}

    child_groups: dict[str, list[Any]] = {}
    for child in children:
        for child_tag, child_value in _element_to_dict(child).items():
            child_groups.setdefault(child_tag, []).append(child_value)

    for child_tag, values in child_groups.items():
        result[child_tag] = values[0] if len(values) == 1 else values
    return {tag: result}
