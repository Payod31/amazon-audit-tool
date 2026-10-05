"""
Reorganize a messy image-name/link export into a clean table:
one row per product (Main_Name, Secondary_Name), with that product's
image links laid out HORIZONTALLY in numbered columns (Image_1, Image_2, ...)
instead of one link per row.

No scraping involved anywhere here -- this only reorganizes a spreadsheet
the user already has (an export, or any file they paste/upload). It never
fetches or touches Amazon Seller Central.
"""

from __future__ import annotations

import io
import os
import re
from dataclasses import dataclass, field

import pandas as pd

# Matches a trailing run of digits right before the file extension, e.g.
# "...US_ISP_05.jpg" -> number "05". This is intentionally the ONLY thing
# we rely on to find the image number -- everything else about the
# filename's shape (how many middle segments, what they say) is ignored.
TRAILING_NUMBER_RE = re.compile(r"(\d+)\s*$")


@dataclass
class ParsedName:
    raw: str
    main: str = ""
    secondary: str = ""
    number: int | None = None
    ok: bool = True
    reason: str = ""


def read_any_table(data: bytes, filename: str) -> pd.DataFrame:
    """Read an uploaded .xlsx/.xls/.csv into a DataFrame, all-strings-ish."""
    ext = os.path.splitext(filename)[1].lower()
    buf = io.BytesIO(data)
    if ext in (".xlsx", ".xlsm", ".xls"):
        df = pd.read_excel(buf, dtype=str, engine=None if ext != ".xls" else None)
    else:
        df = pd.read_csv(buf, dtype=str, keep_default_na=False)
    df = df.fillna("")
    df.columns = [str(c).strip() for c in df.columns]
    return df


def guess_column(columns: list[str], prefer: list[str], avoid: list[str] = ()) -> str | None:
    """Best-effort guess of which column holds filenames vs. links."""
    cols_lower = {c: c.lower() for c in columns}

    def score(col: str) -> int:
        low = cols_lower[col]
        s = 0
        for i, kw in enumerate(prefer):
            if low == kw:
                s += (len(prefer) - i) * 100  # exact match wins outright
            elif kw in low:
                s += (len(prefer) - i) * 10
        for kw in avoid:
            if kw in low:
                s -= 50
        return s

    ranked = sorted(columns, key=score, reverse=True)
    if not ranked:
        return None
    return ranked[0] if score(ranked[0]) > 0 else None


def non_empty_columns(df: pd.DataFrame) -> list[str]:
    """Columns that have at least one non-blank value, in their original
    order. Export files often carry a long list of headers that are blank
    for every row (other locales, other asset types, etc.) -- those are
    filtered out so the user only has to choose among columns that could
    actually hold a filename or a link."""
    out = []
    for c in df.columns:
        col = df[c].astype(str).str.strip()
        if (col != "").any():
            out.append(c)
    return out


def guess_name_column(columns: list[str]) -> str | None:
    return guess_column(
        columns,
        prefer=["filename", "file name", "image name", "name"],
        avoid=["master", "link", "url", "document", "video"],
    )


def guess_link_column(columns: list[str]) -> str | None:
    return guess_column(
        columns,
        prefer=["image master file", "master file", "link", "url", "image"],
        avoid=["video", "document"],
    )


def _strip_ext(name: str) -> tuple[str, str]:
    base, ext = os.path.splitext(name.strip())
    return base, ext


def parse_filename(raw: str, delimiter: str = "_", has_secondary: bool = True) -> ParsedName:
    raw = (raw or "").strip()
    if not raw:
        return ParsedName(raw=raw, ok=False, reason="Empty filename")

    base, _ext = _strip_ext(raw)
    if not base:
        return ParsedName(raw=raw, ok=False, reason="Nothing before the file extension")

    m = TRAILING_NUMBER_RE.search(base)
    if not m:
        return ParsedName(raw=raw, ok=False, reason="No image number found at the end of the filename")

    number = int(m.group(1))
    head = base[: m.start()].rstrip(delimiter or "_")

    if not head:
        return ParsedName(raw=raw, ok=False, reason="No name segments before the number")

    parts = [p for p in head.split(delimiter) if p != ""] if delimiter else [head]
    if not parts:
        return ParsedName(raw=raw, ok=False, reason="Could not split the filename into segments")

    main = parts[0]
    secondary = parts[1] if (has_secondary and len(parts) > 1) else ""

    return ParsedName(raw=raw, main=main, secondary=secondary, number=number, ok=True)


@dataclass
class BuildResult:
    table: pd.DataFrame
    problems: pd.DataFrame
    max_images: int
    group_count: int
    row_count: int


def build_horizontal_table(
    df: pd.DataFrame,
    name_col: str,
    link_col: str,
    delimiter: str = "_",
    has_secondary: bool = True,
) -> BuildResult:
    """
    Groups rows by (Main_Name, Secondary_Name) parsed from `name_col`,
    and arranges each group's `link_col` values horizontally by image
    number, sorted A-Z by Main then Secondary name.
    """
    groups: dict[tuple[str, str], dict[int, str]] = {}
    order: list[tuple[str, str]] = []
    problems: list[dict] = []

    for _, row in df.iterrows():
        raw_name = str(row.get(name_col, "") or "")
        link = str(row.get(link_col, "") or "")

        if not raw_name and not link:
            continue

        parsed = parse_filename(raw_name, delimiter=delimiter, has_secondary=has_secondary)
        if not parsed.ok:
            problems.append({
                "Filename": raw_name,
                "Link": link,
                "Problem": parsed.reason,
            })
            continue

        key = (parsed.main, parsed.secondary)
        if key not in groups:
            groups[key] = {}
            order.append(key)

        slot = groups[key]
        if parsed.number in slot:
            problems.append({
                "Filename": raw_name,
                "Link": link,
                "Problem": (
                    f"Duplicate image number {parsed.number:02d} for "
                    f"{parsed.main}" + (f" / {parsed.secondary}" if parsed.secondary else "")
                    + f" -- kept '{slot[parsed.number]}', this one was dropped from the table "
                      "(it's listed here so nothing is lost)."
                ),
            })
            continue

        slot[parsed.number] = link

    max_images = max((max(slot.keys()) for slot in groups.values() if slot), default=0)

    order_sorted = sorted(order, key=lambda k: (k[0].lower(), k[1].lower()))

    rows = []
    for main, secondary in order_sorted:
        slot = groups[(main, secondary)]
        row = {"Main_Name": main, "Secondary_Name": secondary}
        for n in range(1, max_images + 1):
            row[f"Image_{n}"] = slot.get(n, "")
        rows.append(row)

    columns = ["Main_Name", "Secondary_Name"] + [f"Image_{n}" for n in range(1, max_images + 1)]
    table = pd.DataFrame(rows, columns=columns) if rows else pd.DataFrame(columns=["Main_Name", "Secondary_Name"])

    problems_df = pd.DataFrame(problems, columns=["Filename", "Link", "Problem"]) if problems else pd.DataFrame(
        columns=["Filename", "Link", "Problem"]
    )

    return BuildResult(
        table=table,
        problems=problems_df,
        max_images=max_images,
        group_count=len(order_sorted),
        row_count=len(df),
    )


def result_to_xlsx_bytes(result: BuildResult) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        result.table.to_excel(writer, sheet_name="Reorganized", index=False)
        if not result.problems.empty:
            result.problems.to_excel(writer, sheet_name="Problems", index=False)
    return buf.getvalue()


def result_to_csv_bytes(result: BuildResult) -> bytes:
    return result.table.to_csv(index=False).encode("utf-8")