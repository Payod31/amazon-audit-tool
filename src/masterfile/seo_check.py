"""
Checks an Amazon masterfile's SEO-relevant content fields -- Item Name,
Bullet Points (Key Product Features), Product Description, and Generic
Keywords -- against Amazon's general, widely-published listing style-guide
rules (length limits, no promotional language, no HTML, no contact info,
and so on), then hands back the SAME masterfile with a cell comment on
every flagged field explaining exactly what's wrong, right where it needs
fixing.

This only works on an actual Amazon masterfile (the Seller Central
flat-file export) -- an Amplifi file is rejected, since the whole point is
to annotate the real file the user uploads back to Seller Central, not a
different file shape.

This only reads a masterfile the user already has on disk -- nothing here
ever talks to Seller Central or any Amazon service. Exact limits can vary
by category, so treat the results as a first-pass check to catch obvious
problems before upload, not a guarantee that Amazon will approve the
listing.

A field being "mandatory" in Amazon's schema doesn't always mean it has to
be filled in in THIS particular file: a partial update only touches the
fields it's actually changing (brand, parentage, and plenty of other
mandatory fields are commonly left blank there on purpose, inherited from
whatever's already on the live listing), while creating a new product or
doing a full update is expected to carry the whole thing, SEO fields
included. So every check function takes a `mode` ("create", "full_update"
or "partial_update") and only flags a blank Item Name / Bullet Points /
Product Description / Generic Keywords as a problem when mode is NOT
"partial_update" -- the caller (the UI) asks the user which of the three
this file is, via a radio button, since that intent isn't reliably
recoverable from the file itself.
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass

import openpyxl
from openpyxl.comments import Comment

from src.masterfile.fill_template import detect_source_kind
from src.masterfile.schema import _find_template_sheet, _parse_settings

# ---------------------------------------------------------------------------
# Tunable limits. These are Amazon's general published style-guide numbers;
# some categories allow more or less -- adjust here if yours differs.
# ---------------------------------------------------------------------------


@dataclass
class SeoLimits:
    item_name_max: int = 200
    bullet_point_max: int = 255
    bullet_point_recommended_max: int = 200
    expected_bullet_count: int = 5
    product_description_max: int = 2000
    generic_keywords_max_bytes: int = 250


# What this masterfile is for, picked by the user (it isn't reliably
# recoverable from the file itself). Only "partial_update" relaxes the
# "field is missing" checks below -- "create" and "full_update" both
# expect the SEO content fields to be fully filled in, same as before.
MASTERFILE_MODES = [
    ("create", "Creating a new product", "All fields are expected to be fully filled in."),
    ("full_update", "Full update", "Replacing the whole listing -- treated the same as creating a new one."),
    ("partial_update", "Partial update", "Only specific fields are being changed -- a blank Item Name, "
        "Bullet Points, Product Description or Generic Keywords is expected and won't be flagged."),
]
DEFAULT_MASTERFILE_MODE = "create"
_VALID_MODES = {key for key, _, _ in MASTERFILE_MODES}


def mode_labels() -> list[str]:
    """Display labels in the fixed order above, for a radio button."""
    return [label for _, label, _ in MASTERFILE_MODES]


def mode_key_for_label(label: str) -> str:
    for key, lbl, _ in MASTERFILE_MODES:
        if lbl == label:
            return key
    raise ValueError(f"Unknown masterfile mode label: {label!r}")


def mode_help_for_label(label: str) -> str:
    for _, lbl, help_text in MASTERFILE_MODES:
        if lbl == label:
            return help_text
    return ""


def default_mode_label() -> str:
    for key, label, _ in MASTERFILE_MODES:
        if key == DEFAULT_MASTERFILE_MODE:
            return label
    return MASTERFILE_MODES[0][1]


def _skip_missing_checks(mode: str) -> bool:
    if mode not in _VALID_MODES:
        raise ValueError(
            f"Unknown masterfile mode {mode!r} -- expected one of {sorted(_VALID_MODES)}."
        )
    return mode == "partial_update"


# Attribute-path substrings (case-insensitive) that identify each logical
# SEO field, regardless of exactly how a given template names its column
# (e.g. "bullet_point1" vs "bullet_point#1.value" vs "key_product_feature...").
FIELD_PATTERNS = {
    "item_name": ["item_name"],
    "bullet_point": ["bullet_point", "key_product_feature"],
    "product_description": ["product_description"],
    "generic_keyword": ["generic_keyword", "search_term"],
}

SKU_PATTERNS = ["item_sku", "contribution_sku", "sku"]

PROMOTIONAL_PHRASES = [
    "free shipping", "% off", "best seller", "bestseller", "guarantee",
    "guaranteed", "sale", "discount", "lowest price", "cheap", "cheapest",
    "top rated", "#1 ", "#1,", "limited time", "deal of the day", "promo",
    "promotion", "clearance", "satisfaction guarantee",
]


def _promo_pattern(phrase: str) -> re.Pattern:
    """Word-boundary-wraps a phrase only on the side(s) where it starts/ends
    with an alphanumeric character -- this is what keeps "sale" from
    matching inside "sales@example.com" or "wholesale", while still letting
    a symbol-led phrase like "% off" match right after a digit (e.g.
    "20% off"), where a plain \\b wouldn't apply cleanly on the "%" side."""
    prefix = r"\b" if phrase[0].isalnum() else ""
    suffix = r"\b" if phrase[-1].isalnum() else ""
    return re.compile(prefix + re.escape(phrase) + suffix, re.IGNORECASE)


_PROMO_PATTERNS = [(_promo_pattern(p), p) for p in PROMOTIONAL_PHRASES]

FORBIDDEN_TITLE_SYMBOLS = set("!*$?_{}^~")

HTML_TAG_RE = re.compile(r"<[^>]+>")

# <br> / <br/> / <br /> (any number of them, back to back or not) are just
# line breaks, not real markup -- Amazon tolerates them in these fields, so
# they're stripped out before the HTML check runs and never get flagged.
BR_TAG_RE = re.compile(r"<\s*br\s*/?\s*>", re.IGNORECASE)


def _has_real_html(text: str) -> bool:
    """True if `text` contains HTML markup OTHER than <br> tags -- <br> and
    repeated <br><br> are removed first so they're never the reason this
    returns True, and no finding/comment gets raised just for using them."""
    return bool(HTML_TAG_RE.search(BR_TAG_RE.sub("", text)))

CONTACT_INFO_RE = re.compile(
    r"(?P<email>[\w.+-]+@[\w-]+\.[\w.-]+)"
    r"|(?P<url>https?://\S+|www\.\S+)"
    r"|(?P<phone>(?:\+?\d{1,3}[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4})",
    re.IGNORECASE,
)

_NUMBER_RE = re.compile(r"(\d+)")


@dataclass
class SeoFinding:
    sku: str
    field: str
    severity: str  # "error" | "warning" | "info"
    message: str

    def to_dict(self) -> dict:
        return {"SKU": self.sku, "Field": self.field, "Severity": self.severity, "Message": self.message}


def _find_value(row: dict, patterns: list[str]) -> str | None:
    for key, value in row.items():
        key_l = key.lower()
        if any(p in key_l for p in patterns) and value not in (None, ""):
            return str(value)
    return None


def _find_values(row: dict, patterns: list[str]) -> list[tuple[str, str]]:
    """All (key, value) pairs matching any of the given patterns, sorted by
    whatever trailing number is in the key (bullet_point1 before
    bullet_point2, etc.) so results read in the natural order."""
    matches = []
    for key, value in row.items():
        key_l = key.lower()
        if any(p in key_l for p in patterns) and value not in (None, ""):
            matches.append((key, str(value)))

    def sort_key(item):
        m = _NUMBER_RE.search(item[0])
        return int(m.group(1)) if m else 0

    return sorted(matches, key=sort_key)


def _sku_for_row(row: dict) -> str:
    return _find_value(row, SKU_PATTERNS) or "(no SKU found)"


def _contains_promotional_language(text: str) -> str | None:
    for pattern, phrase in _PROMO_PATTERNS:
        if pattern.search(text):
            return phrase
    return None


def _check_item_name(sku: str, row: dict, limits: SeoLimits, mode: str) -> list[SeoFinding]:
    findings: list[SeoFinding] = []
    value = _find_value(row, FIELD_PATTERNS["item_name"])

    if not value:
        if not _skip_missing_checks(mode):
            findings.append(SeoFinding(sku, "Item Name", "error", "Item Name is missing."))
        return findings

    length = len(value)
    if length > limits.item_name_max:
        findings.append(SeoFinding(
            sku, "Item Name", "error",
            f"{length} characters -- exceeds the {limits.item_name_max}-character limit "
            f"by {length - limits.item_name_max}.",
        ))

    if value.isupper():
        findings.append(SeoFinding(sku, "Item Name", "warning", "Entire title is in ALL CAPS."))

    bad_symbols = sorted(set(value) & FORBIDDEN_TITLE_SYMBOLS)
    if bad_symbols:
        findings.append(SeoFinding(
            sku, "Item Name", "warning",
            f"Contains symbol(s) Amazon discourages in titles: {' '.join(bad_symbols)}",
        ))

    if _has_real_html(value):
        findings.append(SeoFinding(sku, "Item Name", "error", "Contains HTML markup."))

    promo = _contains_promotional_language(value)
    if promo:
        findings.append(SeoFinding(sku, "Item Name", "warning", f'Contains promotional language: "{promo}".'))

    if "  " in value:
        findings.append(SeoFinding(sku, "Item Name", "info", "Contains double spaces."))

    return findings


def _check_bullets(sku: str, row: dict, limits: SeoLimits, mode: str) -> list[SeoFinding]:
    findings: list[SeoFinding] = []
    bullets = _find_values(row, FIELD_PATTERNS["bullet_point"])
    skip_missing = _skip_missing_checks(mode)

    if not bullets:
        if not skip_missing:
            findings.append(SeoFinding(sku, "Bullet Points", "error", "No bullet points / key product features found."))
        return findings

    if len(bullets) < limits.expected_bullet_count and not skip_missing:
        findings.append(SeoFinding(
            sku, "Bullet Points", "warning",
            f"Only {len(bullets)} of the usual {limits.expected_bullet_count} bullet points are filled in.",
        ))

    for key, value in bullets:
        label = f"Bullet Point ({key})"
        length = len(value)

        if length > limits.bullet_point_max:
            findings.append(SeoFinding(
                sku, label, "error",
                f"{length} characters -- exceeds the {limits.bullet_point_max}-character hard limit "
                f"by {length - limits.bullet_point_max}.",
            ))
        elif length > limits.bullet_point_recommended_max:
            findings.append(SeoFinding(
                sku, label, "info",
                f"{length} characters -- over the recommended {limits.bullet_point_recommended_max} for "
                f"readability, though still under the hard limit.",
            ))

        if value and not value[0].isupper():
            findings.append(SeoFinding(sku, label, "info", "Doesn't start with a capital letter."))

        if _has_real_html(value):
            findings.append(SeoFinding(sku, label, "error", "Contains HTML markup."))

        if value.isupper():
            findings.append(SeoFinding(sku, label, "warning", "Entire bullet is in ALL CAPS."))

        promo = _contains_promotional_language(value)
        if promo:
            findings.append(SeoFinding(sku, label, "warning", f'Contains promotional language: "{promo}".'))

        if CONTACT_INFO_RE.search(value):
            findings.append(SeoFinding(sku, label, "warning", "Looks like it contains contact info (email/URL/phone number)."))

    return findings


def _check_description(sku: str, row: dict, limits: SeoLimits, mode: str) -> list[SeoFinding]:
    findings: list[SeoFinding] = []
    value = _find_value(row, FIELD_PATTERNS["product_description"])

    if not value:
        if not _skip_missing_checks(mode):
            findings.append(SeoFinding(sku, "Product Description", "warning", "Product Description is missing."))
        return findings

    length = len(value)
    if length > limits.product_description_max:
        findings.append(SeoFinding(
            sku, "Product Description", "error",
            f"{length} characters -- exceeds the {limits.product_description_max}-character limit "
            f"by {length - limits.product_description_max}.",
        ))

    if _has_real_html(value):
        findings.append(SeoFinding(
            sku, "Product Description", "warning",
            "Contains HTML markup (only expected if this listing uses A+ Content).",
        ))

    if CONTACT_INFO_RE.search(value):
        findings.append(SeoFinding(sku, "Product Description", "warning", "Looks like it contains contact info (email/URL/phone number)."))

    promo = _contains_promotional_language(value)
    if promo:
        findings.append(SeoFinding(sku, "Product Description", "warning", f'Contains promotional language: "{promo}".'))

    return findings


def _check_generic_keywords(sku: str, row: dict, limits: SeoLimits, mode: str) -> list[SeoFinding]:
    findings: list[SeoFinding] = []
    keywords = _find_values(row, FIELD_PATTERNS["generic_keyword"])

    if not keywords:
        if not _skip_missing_checks(mode):
            findings.append(SeoFinding(sku, "Generic Keywords", "info", "No generic keywords / search terms filled in."))
        return findings

    combined = " ".join(v for _, v in keywords)
    byte_length = len(combined.encode("utf-8"))
    if byte_length > limits.generic_keywords_max_bytes:
        findings.append(SeoFinding(
            sku, "Generic Keywords", "error",
            f"{byte_length} bytes -- exceeds the {limits.generic_keywords_max_bytes}-byte limit "
            f"by {byte_length - limits.generic_keywords_max_bytes}.",
        ))

    if "," in combined:
        findings.append(SeoFinding(
            sku, "Generic Keywords", "warning",
            "Contains commas -- Amazon wants keywords space-separated, not comma-separated.",
        ))

    title = _find_value(row, FIELD_PATTERNS["item_name"]) or ""
    title_words = {w.lower() for w in re.findall(r"[a-zA-Z0-9]+", title) if len(w) > 2}
    keyword_words = {w.lower() for w in re.findall(r"[a-zA-Z0-9]+", combined) if len(w) > 2}
    overlap = sorted(title_words & keyword_words)
    if overlap:
        shown = ", ".join(overlap[:10]) + (" ..." if len(overlap) > 10 else "")
        findings.append(SeoFinding(
            sku, "Generic Keywords", "info",
            f"Repeats word(s) already in the title (wastes the byte limit): {shown}",
        ))

    promo = _contains_promotional_language(combined)
    if promo:
        findings.append(SeoFinding(sku, "Generic Keywords", "warning", f'Contains promotional/subjective language: "{promo}".'))

    return findings


# Comment box background color per severity -- so a glance at the color
# tells you how serious the issue is, without opening every note. Picked
# to match Excel's own familiar "Light Red/Yellow/Blue Fill" palette.
SEVERITY_COLORS = {
    "error": "#FFC7CE",    # light red
    "warning": "#FFEB9C",  # light amber/yellow
    "info": "#BDD7EE",     # light blue
}
_SEVERITY_ORDER = ("error", "warning", "info")


def _color_for_severities(severities: list[str]) -> str:
    """The color for a cell with one or more findings is driven by the
    MOST severe one present (error beats warning beats info), same
    priority order used for the per-SKU status rollup."""
    present = set(severities)
    for level in _SEVERITY_ORDER:
        if level in present:
            return SEVERITY_COLORS[level]
    return SEVERITY_COLORS["info"]


def _estimate_comment_box_size(messages: list[str], width: int = 340) -> int:
    """Estimates a comment box height tall enough to show every message on
    its own wrapped line or lines, so several messages combined onto one
    cell don't overlap/get clipped -- the actual bug behind "multiple
    comments on the cell ... not properly visible". Rough monospace-ish
    estimate: ~6px per character at the note's default font size."""
    chars_per_line = max(10, width // 6)
    line_height = 15
    total_lines = 0
    for msg in messages:
        total_lines += max(1, -(-len(msg) // chars_per_line))  # ceil(len/chars_per_line)
    return min(500, 24 + total_lines * line_height)


# Field names as the check_* functions above produce them, mapped back to
# the column that field's data actually lives in -- so a finding can be
# written as a comment on the exact cell it's about.
_BULLET_KEY_RE = re.compile(r"^Bullet Point \((.+)\)$")


def _first_col(attr_to_col: dict[str, int], patterns: list[str]) -> int | None:
    matches = [(attr, col) for attr, col in attr_to_col.items() if any(p in attr.lower() for p in patterns)]
    if not matches:
        return None

    def sort_key(item):
        m = _NUMBER_RE.search(item[0])
        return int(m.group(1)) if m else 0

    matches.sort(key=sort_key)
    return matches[0][1]


def _column_for_finding(f: SeoFinding, attr_to_col: dict[str, int]) -> int | None:
    if f.field == "Item Name":
        return _first_col(attr_to_col, FIELD_PATTERNS["item_name"])
    if f.field == "Bullet Points":
        return _first_col(attr_to_col, FIELD_PATTERNS["bullet_point"])
    m = _BULLET_KEY_RE.match(f.field)
    if m:
        return attr_to_col.get(m.group(1))
    if f.field == "Product Description":
        return _first_col(attr_to_col, FIELD_PATTERNS["product_description"])
    if f.field == "Generic Keywords":
        return _first_col(attr_to_col, FIELD_PATTERNS["generic_keyword"])
    return None


def _annotate_row(
    ws,
    r: int,
    attr_to_col: dict[str, int],
    row_findings: list[SeoFinding],
    sku_col: int | None,
    color_by_cell: dict[tuple[int, int], str],
) -> None:
    """Writes every finding for this row as a cell comment -- on the exact
    column the finding is about when one can be identified, or on the SKU
    cell as a fallback (e.g. "only 2 of 5 bullets filled in" isn't about
    any one cell). Multiple findings on the same cell are combined into
    ONE comment box, sized to fit every line so they don't overlap or get
    clipped, and colored by the most severe finding in it -- the color is
    recorded in color_by_cell (row, col) -> hex, applied after the
    workbook is saved (see _recolor_comment_boxes)."""
    by_col: dict[int, list[SeoFinding]] = {}
    for f in row_findings:
        col = _column_for_finding(f, attr_to_col)
        if col is None:
            col = sku_col
        if col is None:
            continue
        by_col.setdefault(col, []).append(f)

    for col, finds in by_col.items():
        width = 340
        messages = [f"[{f.severity.upper()}] {f.field}: {f.message}" for f in finds]
        text = "\n".join(messages)
        height = _estimate_comment_box_size(messages, width=width)
        ws.cell(row=r, column=col).comment = Comment(text, "ASIN Forge SEO Check", height=height, width=width)
        color_by_cell[(r, col)] = _color_for_severities([f.severity for f in finds])


# openpyxl writes every cell comment's little popup box as a VML shape
# inside xl/drawings/commentsDrawingN.vml, always with a fixed pale-yellow
# fillcolor and no per-comment coloring hook in its public API. These
# regexes find each comment shape (matched by its fixed
# type="#_x0000_t202" marker, NOT by namespace prefix -- openpyxl/lxml
# auto-generates prefixes like "ns0:", "ns2:", ... and they aren't
# guaranteed to read the same across versions) and recolor + reposition it
# after the workbook is already saved.
_SHAPE_BLOCK_RE = re.compile(r'<(\w+:shape)(?=[^>]*\btype="#_x0000_t202")[^>]*>.*?</\1>', re.DOTALL)
_ROW_RE = re.compile(r"<\w+:Row>(\d+)</\w+:Row>")
_COL_RE = re.compile(r"<\w+:Column>(\d+)</\w+:Column>")
_FILLCOLOR_RE = re.compile(r'fillcolor="[^"]*"')
_FILL2_RE = re.compile(r'(<\w+:fill\b[^>]*\bcolor2=")[^"]*(")')
_MARGIN_LEFT_RE = re.compile(r"margin-left:[^;]+;")
_MARGIN_TOP_RE = re.compile(r"margin-top:[^;]+;")


def _recolor_vml_text(text: str, color_by_cell: dict[tuple[int, int], str]) -> str:
    def _replace(m: re.Match) -> str:
        block = m.group(0)
        row_m = _ROW_RE.search(block)
        col_m = _COL_RE.search(block)
        if not row_m or not col_m:
            return block
        # openpyxl stores Row/Column 0-indexed; our tracking is 1-indexed
        # (matching ws.cell(row=..., column=...)).
        row, col = int(row_m.group(1)) + 1, int(col_m.group(1)) + 1
        color = color_by_cell.get((row, col))
        if not color:
            return block

        # Only the shape's own opening tag (before its first ">") carries
        # the fillcolor/style we want to change -- everything after that,
        # like the nested <...:textbox style="..."> div, must stay alone.
        open_end = block.index(">") + 1
        open_tag, rest = block[:open_end], block[open_end:]

        open_tag = _FILLCOLOR_RE.sub(f'fillcolor="{color}"', open_tag, count=1)
        # Stagger each box's position a little by its row/col so several
        # comments don't all render stacked at the exact same spot when
        # "Show All Comments" is used -- purely cosmetic, doesn't affect
        # the per-cell hover popup, which Excel positions at the cell.
        margin_left = 40 + (col % 8) * 45
        margin_top = 2 + (row % 12) * 14
        open_tag = _MARGIN_LEFT_RE.sub(f"margin-left:{margin_left}pt;", open_tag)
        open_tag = _MARGIN_TOP_RE.sub(f"margin-top:{margin_top}pt;", open_tag)

        rest = _FILL2_RE.sub(lambda mm: f"{mm.group(1)}{color}{mm.group(2)}", rest, count=1)

        return open_tag + rest

    return _SHAPE_BLOCK_RE.sub(_replace, text)


def _recolor_comment_boxes(xlsx_bytes: bytes, color_by_cell: dict[tuple[int, int], str]) -> bytes:
    """Re-opens the just-saved xlsx/xlsm as a zip, recolors every comment's
    VML shape per color_by_cell, and returns the modified file bytes.
    Every other part of the archive is copied through untouched."""
    if not color_by_cell:
        return xlsx_bytes

    src = zipfile.ZipFile(io.BytesIO(xlsx_bytes), "r")
    out_buf = io.BytesIO()
    with zipfile.ZipFile(out_buf, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename.lower().endswith(".vml"):
                text = _recolor_vml_text(data.decode("utf-8"), color_by_cell)
                data = text.encode("utf-8")
            dst.writestr(item, data)
    return out_buf.getvalue()


def check_and_annotate_masterfile(
    data: bytes,
    filename: str,
    mode: str = DEFAULT_MASTERFILE_MODE,
    limits: SeoLimits | None = None,
) -> tuple[list[SeoFinding], list[str], bytes]:
    """Checks every product row in an uploaded Amazon masterfile against
    the SEO content rules, writes a cell comment on every flagged field,
    and returns (findings, skus_checked, annotated_file_bytes) -- the last
    one is the SAME file, same format, with comments added, ready to
    download.

    mode is one of the MASTERFILE_MODES keys ("create", "full_update",
    "partial_update") -- only "partial_update" suppresses the "this field
    is blank" findings, since a partial update is expected to leave
    untouched fields blank.

    Raises ValueError if the file isn't an Amazon masterfile (e.g. it's an
    Amplifi file instead) -- this tool only reads and annotates the real
    Seller Central flat-file export. Also raises ValueError if `mode` isn't
    one of the known keys."""
    if mode not in _VALID_MODES:
        raise ValueError(f"Unknown masterfile mode {mode!r} -- expected one of {sorted(_VALID_MODES)}.")

    limits = limits or SeoLimits()
    keep_vba = filename.lower().endswith(".xlsm")
    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=False, keep_vba=keep_vba)

    if detect_source_kind(wb) != "amazon_masterfile":
        raise ValueError(
            "This only works on an Amazon masterfile (the Seller Central flat-file "
            "export) -- this file looks like an Amplifi file instead. Upload the "
            "masterfile you want checked."
        )

    ws = _find_template_sheet(wb)
    settings = _parse_settings(ws.cell(row=1, column=1).value)
    attribute_row = int(settings.get("attributeRow", 5))
    data_row_start = int(settings.get("dataRow", 7))

    attr_by_col: dict[int, str] = {}
    for c in range(1, ws.max_column + 1):
        attr = ws.cell(row=attribute_row, column=c).value
        if attr:
            attr_by_col[c] = str(attr).strip()
    attr_to_col = {attr: col for col, attr in attr_by_col.items()}
    sku_col = _first_col(attr_to_col, SKU_PATTERNS)

    skus_checked: list[str] = []
    findings: list[SeoFinding] = []
    color_by_cell: dict[tuple[int, int], str] = {}

    for r in range(data_row_start, ws.max_row + 1):
        row_dict: dict[str, object] = {}
        for c, attr in attr_by_col.items():
            v = ws.cell(row=r, column=c).value
            if v not in (None, ""):
                row_dict[attr] = v
        if not row_dict:
            continue  # blank row -- nothing to check or annotate

        sku = _sku_for_row(row_dict)
        skus_checked.append(sku)

        row_findings: list[SeoFinding] = []
        row_findings += _check_item_name(sku, row_dict, limits, mode)
        row_findings += _check_bullets(sku, row_dict, limits, mode)
        row_findings += _check_description(sku, row_dict, limits, mode)
        row_findings += _check_generic_keywords(sku, row_dict, limits, mode)
        findings.extend(row_findings)

        _annotate_row(ws, r, attr_to_col, row_findings, sku_col, color_by_cell)

    buf = io.BytesIO()
    wb.save(buf)
    annotated_bytes = _recolor_comment_boxes(buf.getvalue(), color_by_cell)
    return findings, skus_checked, annotated_bytes


def summarize_by_sku(findings: list[SeoFinding], skus_checked: list[str]) -> list[dict]:
    """One row per SKU (including clean ones, from skus_checked) with
    counts of errors/warnings/notes and an overall status: 'Blocked' if
    any error, 'Needs review' if only warnings, 'Minor notes' if only
    info-level notes, 'Looks good' if completely clean."""
    by_sku: dict[str, list[SeoFinding]] = {sku: [] for sku in skus_checked}
    for f in findings:
        by_sku.setdefault(f.sku, []).append(f)

    rows = []
    for sku in by_sku:  # preserves insertion order from skus_checked
        items = by_sku[sku]
        errors = sum(1 for i in items if i.severity == "error")
        warnings = sum(1 for i in items if i.severity == "warning")
        notes = sum(1 for i in items if i.severity == "info")
        if errors:
            status = "Blocked"
        elif warnings:
            status = "Needs review"
        elif notes:
            status = "Minor notes"
        else:
            status = "Looks good"
        rows.append({"SKU": sku, "Status": status, "Errors": errors, "Warnings": warnings, "Notes": notes})
    return rows