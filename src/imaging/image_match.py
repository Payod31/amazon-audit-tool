"""
Shared pieces for the 'Image match check' tool: fetching a product's main
image, and parsing the 'name(s) then image link' shape (from a paste or a
spreadsheet) into a common list of rows. The actual yes/no/unsure judgment
is done in src/imaging/clip_match.py (a free, local CLIP-based check --
see that file for why).

Expected row shape (from a paste or a spreadsheet), one entry per product:

    Homedics Tabletop Water Fountain, Home Decor Soothing Sound Machine
    https://m.media-amazon.com/images/I/61vEjplUwlL._AC_SL1500_.jpg

Two identifiers are given in front of the image link -- the SECOND one is
"the name" actually checked against the image (the first is kept only as
fallback/context, e.g. a SKU or a broader title). If only one identifier
is given, that one is used as the name.

This only ever fetches a public image URL that's already sitting in a file
or pasted text the user provides (e.g. the m.media-amazon.com image CDN).
It never logs into, scrapes, or otherwise touches Seller Central or any
other Amazon account page -- fetching is refused outright for any link on
a sellercentral.amazon host.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from urllib.parse import urlparse

import pandas as pd
import requests

from src.imaging.reorganize_links import guess_column, non_empty_columns, read_any_table  # noqa: F401  (re-exported for the UI)

# ---------------------------------------------------------------------------
# Fetching the image
# ---------------------------------------------------------------------------

MAX_IMAGE_BYTES = 10 * 1024 * 1024
FETCH_TIMEOUT = 20
SUPPORTED_MEDIA_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}

# Refuse outright, regardless of what the user pastes -- Pattern's policy is
# that nothing here ever touches Seller Central.
BLOCKED_HOST_SNIPPETS = ("sellercentral.amazon",)


@dataclass
class FetchedImage:
    ok: bool
    media_type: str = ""
    data: bytes = b""
    error: str = ""


def _sniff_media_type(data: bytes) -> str | None:
    """Falls back to the file's magic bytes when a server doesn't send a
    useful Content-Type header."""
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def fetch_image(url: str, timeout: int = FETCH_TIMEOUT) -> FetchedImage:
    """Downloads one image link. Never raises -- failures come back as
    FetchedImage(ok=False, error=...)."""
    url = (url or "").strip()
    if not url:
        return FetchedImage(ok=False, error="No image link given")

    host = urlparse(url).netloc.lower()
    if any(snippet in host for snippet in BLOCKED_HOST_SNIPPETS):
        return FetchedImage(
            ok=False,
            error="Refusing to fetch from Seller Central -- this tool only reads public image links you provide.",
        )

    try:
        resp = requests.get(
            url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0 (ASIN Forge image checker)"}
        )
    except requests.RequestException as e:
        return FetchedImage(ok=False, error=f"Could not fetch the image: {e}")

    if resp.status_code != 200:
        return FetchedImage(ok=False, error=f"Image link returned HTTP {resp.status_code}")

    data = resp.content
    if not data:
        return FetchedImage(ok=False, error="Image link returned no data")
    if len(data) > MAX_IMAGE_BYTES:
        return FetchedImage(
            ok=False,
            error=f"Image is {len(data) / 1_048_576:.1f} MB, over the {MAX_IMAGE_BYTES // 1_048_576} MB limit",
        )

    content_type = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
    media_type = content_type if content_type in SUPPORTED_MEDIA_TYPES else _sniff_media_type(data)
    if media_type is None:
        return FetchedImage(
            ok=False,
            error=f"This link didn't return a recognizable image (content-type: {content_type or 'unknown'})",
        )

    return FetchedImage(ok=True, media_type=media_type, data=data)


# ---------------------------------------------------------------------------
# Parsing input (paste box or spreadsheet) into {Identifier_1, Identifier_2, Image_URL} rows
# ---------------------------------------------------------------------------


def split_identifiers(name_block: str) -> tuple[str, str]:
    """Splits whatever name text sat in front of one image link into
    (identifier_1, identifier_2) -- identifier_2 is the one actually
    checked against the image.

    - Two or more lines: first line -> identifier_1, the rest joined -> identifier_2.
    - One line with a comma: text before the first comma -> identifier_1,
      everything after -> identifier_2.
    - One line with no comma: identifier_1 is empty, the whole line is
      identifier_2 (there's only one identifier, so that's the name).
    """
    lines = [l.strip() for l in name_block.splitlines() if l.strip()]
    if len(lines) >= 2:
        return lines[0], ", ".join(lines[1:])

    only = lines[0] if lines else ""
    if "," in only:
        first, _, rest = only.partition(",")
        return first.strip(), rest.strip()
    return "", only.strip()


def _looks_like_url(line: str) -> bool:
    return line.lower().startswith(("http://", "https://"))


def parse_pasted_pairs(text: str) -> tuple[list[dict], list[dict]]:
    """Parses a pasted block of 'name(s) then image link' entries, e.g.:

        Homedics Tabletop Water Fountain, Home Decor Soothing Sound Machine
        https://m.media-amazon.com/images/I/61vEjplUwlL._AC_SL1500_.jpg

        Another Product Name
        https://m.media-amazon.com/images/I/xyz.jpg

    Blank lines between entries are optional. Returns (rows, problems).
    """
    rows: list[dict] = []
    problems: list[dict] = []
    pending: list[str] = []

    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if _looks_like_url(line):
            if not pending:
                problems.append({"Line": line, "Problem": "Image link with no name above it"})
                continue
            id1, id2 = split_identifiers("\n".join(pending))
            pending = []
            if not id2 and not id1:
                problems.append({"Line": line, "Problem": "No name to check against this image"})
                continue
            rows.append({"Identifier_1": id1, "Identifier_2": id2, "Image_URL": line})
        else:
            pending.append(line)

    if pending:
        problems.append({"Line": " / ".join(pending), "Problem": "Name given with no image link after it"})

    return rows, problems


def guess_name1_column(columns: list[str]) -> str | None:
    return guess_column(
        columns,
        prefer=["identifier 1", "identifier_1", "main name", "sku", "title", "name 1"],
        avoid=["link", "url", "image"],
    )


def guess_name2_column(columns: list[str]) -> str | None:
    return guess_column(
        columns,
        prefer=["identifier 2", "identifier_2", "product name", "item name", "secondary name", "name"],
        avoid=["link", "url", "image"],
    )


def guess_image_column(columns: list[str]) -> str | None:
    return guess_column(
        columns,
        prefer=["main image", "image url", "image link", "image", "link", "url"],
        avoid=["video", "document"],
    )


def build_rows_from_table(
    df: pd.DataFrame, id1_col: str | None, id2_col: str | None, link_col: str
) -> tuple[list[dict], list[dict]]:
    """Same row shape as parse_pasted_pairs, but read from spreadsheet
    columns the user picked instead of parsed out of pasted text."""
    rows: list[dict] = []
    problems: list[dict] = []

    for _, row in df.iterrows():
        id1 = str(row.get(id1_col, "") or "").strip() if id1_col else ""
        id2 = str(row.get(id2_col, "") or "").strip() if id2_col else ""
        url = str(row.get(link_col, "") or "").strip()

        if not url and not id1 and not id2:
            continue
        if not url:
            problems.append({"Identifier_1": id1, "Identifier_2": id2, "Image_URL": "", "Problem": "No image link"})
            continue
        if not id1 and not id2:
            problems.append({"Identifier_1": id1, "Identifier_2": id2, "Image_URL": url, "Problem": "No name to check"})
            continue

        rows.append({"Identifier_1": id1, "Identifier_2": id2, "Image_URL": url})

    return rows, problems


# ---------------------------------------------------------------------------
# Result shape (filled in by whichever checker ran -- see clip_match.py)
# ---------------------------------------------------------------------------


@dataclass
class MatchRow:
    index: int
    identifier_1: str
    identifier_2: str
    image_url: str
    match: str = ""
    reason: str = ""


def results_to_dataframe(results: list[MatchRow]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Identifier 1": r.identifier_1,
                "Name checked": r.identifier_2 or r.identifier_1,
                "Image URL": r.image_url,
                "Match": r.match,
                "Reason": r.reason,
            }
            for r in results
        ]
    )


def results_to_xlsx_bytes(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Image match results", index=False)
    return buf.getvalue()