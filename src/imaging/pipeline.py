import io
import zipfile

from src.auditor.image_rules import download_image
from src.imaging.processor import fit_and_pad, save_jpg_under_size_limit


def prepare_listing_images(listing, target_size=2000, jpg_quality=90,
                            also_png=False, min_fill_warning=85):
    """
    Downloads every image for a listing, fits/pads each to a
    target_size x target_size square on pure white, and names them
    using Amazon's own bulk-upload convention: ASIN.MAIN.jpg,
    ASIN.PT01.jpg, ASIN.PT02.jpg, etc.
    """
    target_w = target_h = target_size
    items = []

    sources = []
    if listing.main_image_url:
        sources.append(("MAIN", listing.main_image_url))
    for i, url in enumerate(listing.image_urls, start=1):
        if url == listing.main_image_url:
            continue
        sources.append((f"PT{i:02d}", url))

    for role, url in sources:
        img = download_image(url)
        if img is None:
            items.append({
                "role": role, "url": url, "ok": False,
                "warning": "Could not download this image -- check the URL is correct and reachable.",
            })
            continue

        canvas, fill_percent, upscale_factor = fit_and_pad(
            img, target_w, target_h, bg_rgb=(255, 255, 255)
        )

        warnings = []
        if fill_percent < min_fill_warning:
            warnings.append(
                f"Product fills only ~{fill_percent}% of the frame after padding "
                f"(Amazon recommends {min_fill_warning}%+ for the main image). "
                "The source photo may need to be cropped tighter before this will "
                "pass Amazon's automated check -- padding alone can't fix this."
            )
        if upscale_factor and upscale_factor > 2:
            warnings.append(
                f"Source image was enlarged {upscale_factor}x to reach {target_size}px -- "
                "it may look soft. A higher-resolution source photo is recommended."
            )

        jpg_bytes, quality_used = save_jpg_under_size_limit(canvas, jpg_quality)
        if quality_used < jpg_quality:
            warnings.append(
                f"JPG quality was auto-reduced to {quality_used} to stay under "
                "Amazon's 10 MB file size limit."
            )

        png_bytes = None
        if also_png:
            buf = io.BytesIO()
            canvas.save(buf, format="PNG")
            png_bytes = buf.getvalue()

        items.append({
            "role": role, "url": url, "ok": True,
            "filename_jpg": f"{listing.asin}.{role}.jpg",
            "filename_png": f"{listing.asin}.{role}.png" if also_png else None,
            "jpg_bytes": jpg_bytes,
            "png_bytes": png_bytes,
            "fill_percent": fill_percent,
            "warnings": warnings,
            "preview": canvas,
        })

    return items


def build_zip(items):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for item in items:
            if not item["ok"]:
                continue
            zf.writestr(item["filename_jpg"], item["jpg_bytes"])
            if item.get("filename_png"):
                zf.writestr(item["filename_png"], item["png_bytes"])
    return buffer.getvalue()