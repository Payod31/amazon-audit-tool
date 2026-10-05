"""Image Prep from a link template (table, Excel or CSV).

You give direct image links; this module downloads them once, lets you see
which ones would need enlarging to fill a square, and then builds a ZIP
named like:
    Main_Secondary_Country_01.jpg   (Secondary is optional)
"""
import io
import re
import zipfile
from pathlib import Path

import pandas as pd
import requests
import yaml
from PIL import Image, ImageOps

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MAX_BYTES = 10 * 1024 * 1024  # Amazon's 10MB cap
BASE_COLUMNS = ["Main_Name", "Secondary_Name", "Country_Code"]
HEADERS = {"User-Agent": "ASINForge/1.0 (personal image prep tool)"}
ILLEGAL_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
IMAGE_COL_PATTERN = re.compile(r"^image(?:[\s_\-]*link)?[\s_\-]*(\d+)$", re.IGNORECASE)
BASE_KEYS = {
    "mainname": "Main_Name",
    "secondaryname": "Secondary_Name",
    "countrycode": "Country_Code",
}

# ---------- settings ----------
def load_prep_settings():
    """Reads image_prep: from config/rules.yaml, with safe defaults."""
    settings = {"target_size": 2000, "jpg_quality": 92, "min_fill_percent_warning": 85}
    try:
        with open(PROJECT_ROOT / "config" / "rules.yaml", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        settings.update(data.get("image_prep") or {})
    except Exception:
        pass
    return settings

# ---------- template / table ----------
def column_names(n_images):
    return BASE_COLUMNS + [f"Image_{i}" for i in range(1, n_images + 1)]

def blank_df(n_images, rows=5):
    return pd.DataFrame([[""] * len(column_names(n_images))] * rows,
                        columns=column_names(n_images))

def make_template_df(n_images=9):
    cols = column_names(n_images)
    sample = "https://picsum.photos/id/1/1500/1500"
    row1 = ["Nike", "AirMax", "US", sample, sample]
    row2 = ["Brand7", "", "DE", sample]
    rows = []
    for r in (row1, row2):
        r = r + [""] * (len(cols) - len(r))
        rows.append(r[: len(cols)])
    return pd.DataFrame(rows, columns=cols)

def template_xlsx_bytes(n_images=9):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df = make_template_df(n_images)
        df.to_excel(writer, index=False, sheet_name="Links")
        ws = writer.sheets["Links"]
        for i, col in enumerate(df.columns, start=1):
            letter = ws.cell(row=1, column=i).column_letter
            ws.column_dimensions[letter].width = 18 if i <= 3 else 40
            if i <= 3:  # keep names like 007 as text
                for r in range(2, 202):
                    ws.cell(row=r, column=i).number_format = "@"
    return buf.getvalue()

def template_csv_bytes(n_images=9):
    return make_template_df(n_images).to_csv(index=False).encode("utf-8-sig")

# ---------- reading data ----------
def normalize_columns(df):
    """Fixes header spelling (spaces/case) and returns a clean DataFrame."""
    rename = {}
    for col in df.columns:
        key = re.sub(r"[\s_\-]+", "", str(col).lower())
        if key in BASE_KEYS:
            rename[col] = BASE_KEYS[key]
        else:
            m = IMAGE_COL_PATTERN.match(str(col).strip())
            if m:
                rename[col] = f"Image_{int(m.group(1))}"
    df = df.rename(columns=rename).fillna("")
    for col in BASE_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    return df.reset_index(drop=True)

def find_image_columns(df):
    """Returns [(number, column_name), ...] sorted by number."""
    found = []
    for col in df.columns:
        m = IMAGE_COL_PATTERN.match(str(col).strip())
        if m:
            found.append((int(m.group(1)), col))
    return sorted(found)

def cell(row, col):
    v = row.get(col, "")
    return "" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v).strip()

# ---------- naming ----------
def clean_part(value):
    s = "" if value is None else str(value)
    s = ILLEGAL_CHARS.sub("", s.strip())
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"_+", "-", s)  # "_" is reserved as the separator
    return s.strip("-. ")

def build_filename(main, secondary, country, number):
    parts = [
        clean_part(main),
        clean_part(secondary),
        clean_part(country).upper(),
        f"{number:02d}",
    ]
    return "_".join(p for p in parts if p) + ".jpg"

# ---------- downloading and processing ----------
def download_image_bytes(url, timeout=30, max_bytes=30 * 1024 * 1024):
    if not url.lower().startswith(("http://", "https://")):
        raise ValueError("Link must start with http:// or https://")
    r = requests.get(url, headers=HEADERS, timeout=timeout, stream=True)
    r.raise_for_status()
    if "text/html" in r.headers.get("Content-Type", "").lower():
        raise ValueError("Link opens a web page, not an image file")
    data = bytearray()
    for chunk in r.iter_content(65536):
        data.extend(chunk)
        if len(data) > max_bytes:
            raise ValueError("Image is larger than 30MB")
    return bytes(data)

def to_rgb_on_white(img):
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        img = img.convert("RGBA")
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[-1])
        return bg
    return img.convert("RGB")

def pad_to_square(img, size, allow_upscale=False):
    """Resize to fit, then center on a white square. Never crops or stretches.

    If allow_upscale is False and the photo is smaller than `size`, it is kept
    at its own size (centered on the white canvas) instead of being enlarged.
    Returns (canvas, fill_percent, applied_scale, was_clamped).
    """
    w, h = img.size
    raw_scale = size / max(w, h)
    scale = raw_scale if allow_upscale else min(raw_scale, 1.0)
    nw, nh = max(1, round(w * scale)), max(1, round(h * scale))
    resized = img.resize((nw, nh), Image.LANCZOS) if scale != 1.0 else img
    canvas = Image.new("RGB", (size, size), (255, 255, 255))
    canvas.paste(resized, ((size - nw) // 2, (size - nh) // 2))
    fill_percent = (nw * nh) / (size * size) * 100
    clamped = (not allow_upscale) and raw_scale > 1.0
    return canvas, fill_percent, scale, clamped

def save_jpg_under_limit(img, quality):
    q = int(quality)
    while True:
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=q, optimize=True)
        data = buf.getvalue()
        if len(data) <= MAX_BYTES or q <= 50:
            return data, q
        q -= 5

def process_one(raw, pad, settings, is_main, allow_upscale=False):
    notes = []
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(raw)))
    orig_w, orig_h = img.size
    img = to_rgb_on_white(img)
    if max(orig_w, orig_h) < 1000:
        notes.append(f"Original is only {orig_w}x{orig_h}px (Amazon wants 1000px+ for zoom)")
    if pad:
        img, fill, scale, clamped = pad_to_square(
            img, int(settings["target_size"]), allow_upscale=allow_upscale
        )
        if clamped:
            notes.append(
                f"Kept at its original {orig_w}x{orig_h}px, centered on the square (not enlarged)"
            )
        elif scale > 1.0:
            notes.append(f"Enlarged x{scale:.2f} as chosen -- may look soft")
        if is_main and fill < float(settings["min_fill_percent_warning"]):
            notes.append(f"Photo fills only {fill:.0f}% of the frame (Amazon wants 85%+ product fill)")
    data, q = save_jpg_under_limit(img, settings["jpg_quality"])
    if len(data) > MAX_BYTES:
        notes.append("Still over 10MB even at low quality")
    elif q < int(settings["jpg_quality"]):
        notes.append(f"JPG quality lowered to {q} to stay under 10MB")
    return data, notes

# ---------- preview thumbnails (for on-screen use only, never saved) ----------
def preview_thumbnail(raw, max_side=220):
    """A small JPEG of the original, just to show which file this is."""
    img = to_rgb_on_white(ImageOps.exif_transpose(Image.open(io.BytesIO(raw))))
    w, h = img.size
    scale = min(1.0, max_side / max(w, h))
    if scale < 1.0:
        img = img.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return buf.getvalue()

def zoom_compare_crops(raw, target_size, orig_w, orig_h, crop_frac=0.3, display_scale=2):
    """A real close-up comparison, so softness from enlarging is actually visible.

    Crops the SAME region from the not-enlarged canvas and the enlarged canvas,
    then blows both crops up the same way (nearest-neighbor, so no extra
    smoothing is added on top of whatever the enlarge step already did).
    Shrinking both to one small thumbnail (the old approach) hides exactly the
    difference this is meant to show.
    """
    img = to_rgb_on_white(ImageOps.exif_transpose(Image.open(io.BytesIO(raw))))

    original_canvas, _, _, _ = pad_to_square(img, target_size, allow_upscale=False)
    enlarged_canvas, _, _, _ = pad_to_square(img, target_size, allow_upscale=True)

    crop_px = int(target_size * crop_frac)
    crop_px = max(40, min(crop_px, orig_w, orig_h, target_size))
    half = crop_px // 2
    cx, cy = target_size // 2, target_size // 2
    box = (cx - half, cy - half, cx - half + crop_px, cy - half + crop_px)

    crop_orig = original_canvas.crop(box)
    crop_enl = enlarged_canvas.crop(box)

    disp = (crop_px * display_scale, crop_px * display_scale)
    crop_orig = crop_orig.resize(disp, Image.NEAREST)
    crop_enl = crop_enl.resize(disp, Image.NEAREST)

    def _jpeg(im):
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=90)
        return buf.getvalue()

    return _jpeg(crop_orig), _jpeg(crop_enl)

# ---------- phase 1: download once, inspect ----------
def _rows_links(df):
    """Yields (table_row, main, secondary, country, num, url) for every filled link cell."""
    img_cols = find_image_columns(df)
    for idx, row in df.iterrows():
        table_row = idx + 1
        country = clean_part(cell(row, "Country_Code"))
        main = cell(row, "Main_Name")
        secondary = cell(row, "Secondary_Name")
        for num, c in img_cols:
            url = cell(row, c)
            if url:
                yield table_row, main, secondary, country, num, url

def fetch_and_inspect(df, target_size, progress=None):
    """Downloads every link once and flags which ones would need enlarging.

    Returns a list of item dicts (key, table_row, name, url, error?, raw,
    orig_w, orig_h, needs_upscale, raw_scale, country_warning?).
    """
    items = []
    used_names = set()
    links = list(_rows_links(df))
    total = len(links)
    done = 0

    for table_row, main, secondary, country, num, url in links:
        done += 1
        if progress:
            progress(done, total)

        item = {
            "key": f"{table_row}:{num}", "table_row": table_row,
            "main": main, "secondary": secondary, "country": country,
            "num": num, "url": url, "name": "",
        }
        if country and not re.fullmatch(r"[A-Za-z]{2}", country):
            item["country_warning"] = f"Country code '{country}' is not 2 letters"

        if not clean_part(main):
            item["error"] = "Main_Name is empty"
            items.append(item)
            continue

        name = build_filename(main, secondary, country, num)
        if name in used_names:
            item["name"] = name
            item["error"] = "Duplicate file name (two rows share the same names)"
            items.append(item)
            continue
        used_names.add(name)
        item["name"] = name

        try:
            raw = download_image_bytes(url)
        except Exception as e:
            item["error"] = str(e)[:200]
            items.append(item)
            continue

        try:
            img = ImageOps.exif_transpose(Image.open(io.BytesIO(raw)))
            orig_w, orig_h = img.size
        except Exception as e:
            item["error"] = f"Could not read the image: {e}"[:200]
            items.append(item)
            continue

        raw_scale = target_size / max(orig_w, orig_h)
        item.update({
            "raw": raw, "orig_w": orig_w, "orig_h": orig_h,
            "raw_scale": raw_scale, "needs_upscale": raw_scale > 1.0 + 1e-6,
        })
        items.append(item)

    return items

# ---------- phase 2: build the ZIP from already-downloaded items ----------
def finalize_zip(items, settings, pad, decisions):
    """decisions: {item_key: True/False} -- True means enlarge that one."""
    report = []
    zbuf = io.BytesIO()

    with zipfile.ZipFile(zbuf, "w", zipfile.ZIP_DEFLATED) as zf:
        for item in items:
            table_row, name, url = item["table_row"], item.get("name", ""), item["url"]
            if item.get("error"):
                report.append((table_row, name, "FAILED", item["error"], url))
                continue
            allow_upscale = bool(decisions.get(item["key"], False))
            try:
                data, notes = process_one(
                    item["raw"], pad, settings,
                    is_main=(item["num"] == 1), allow_upscale=allow_upscale,
                )
            except Exception as e:
                report.append((table_row, name, "FAILED", str(e)[:200], url))
                continue
            zf.writestr(name, data)
            notes = ([item["country_warning"]] if item.get("country_warning") else []) + notes
            report.append((table_row, name, "WARNING" if notes else "OK", "; ".join(notes), url))

    report_df = pd.DataFrame(
        report, columns=["Table row", "File name", "Status", "Details", "Link"]
    )
    return zbuf.getvalue(), report_df