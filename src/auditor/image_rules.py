from io import BytesIO

import requests
import yaml
from PIL import Image

from src.auditor.basic_rules import RULES_PATH

TIMEOUT_SECONDS = 10


def _load_image_rules():
    with open(RULES_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("images", {})


def download_image(url):
    """Downloads an image from a URL and returns a Pillow Image, or None on failure."""
    try:
        response = requests.get(url, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
        return Image.open(BytesIO(response.content))
    except Exception:
        return None


def _is_likely_white_background(img, threshold=235):
    """
    HEURISTIC ONLY. Samples the four corner pixels and checks if they're
    close to white. This is a rough guess, not a reliable detector of
    Amazon's actual main-image rule -- always have a human confirm before
    telling a client their main image fails this check.
    """
    img = img.convert("RGB")
    width, height = img.size
    corners = [(0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1)]
    for x, y in corners:
        r, g, b = img.getpixel((x, y))
        if min(r, g, b) < threshold:
            return False
    return True


def run_image_audit(listing):
    r = _load_image_rules()
    min_px = r.get("min_long_edge_px", 1000)
    findings = []

    def add(check, status, severity, finding, fix=""):
        findings.append({
            "check": check, "status": status, "severity": severity,
            "finding": finding, "fix": fix,
        })

    # 1. Resolution of gallery images
    if not listing.image_urls:
        add("Image resolution", "UNKNOWN", "-",
            "No image URLs were provided for this listing, so resolution could not be checked.")
    else:
        small_images = []
        failed_downloads = 0
        for url in listing.image_urls:
            img = download_image(url)
            if img is None:
                failed_downloads += 1
                continue
            if max(img.size) < min_px:
                small_images.append((url, img.size))

        if failed_downloads:
            add("Image resolution", "UNKNOWN", "-",
                f"{failed_downloads} of {len(listing.image_urls)} image URL(s) could not be downloaded.",
                "Check the URLs are correct and publicly reachable, then re-run.")
        elif small_images:
            worst = small_images[0]
            add("Image resolution", "FAIL", "Medium",
                f"{len(small_images)} of {len(listing.image_urls)} image(s) are under {min_px}px "
                f"on the long edge (smallest: {worst[1][0]}x{worst[1][1]}). Shoppers lose pinch-to-zoom.",
                f"Re-upload images at {min_px}px or larger on the long edge.")
        else:
            add("Image resolution", "PASS", "-",
                f"All {len(listing.image_urls)} images meet the {min_px}px minimum.")

    # 2. Main image background (heuristic)
    if not listing.main_image_url:
        add("Main image background", "UNKNOWN", "-",
            "No main image URL was provided, so the background could not be checked.")
    else:
        img = download_image(listing.main_image_url)
        if img is None:
            add("Main image background", "UNKNOWN", "-",
                "The main image URL could not be downloaded.")
        elif _is_likely_white_background(img):
            add("Main image background", "PASS", "-",
                "Main image corners look white -- consistent with Amazon's main image rule.")
        else:
            add("Main image background", "REVIEW", "Medium",
                "Main image corners are not clearly white. This is a rough automatic check, "
                "not a certain one -- confirm by eye before telling the client it's wrong.",
                "If confirmed, replace with a pure white (RGB 255,255,255) background main image.")

    # 3. Video presence
    if listing.has_video is None:
        add("Product video", "UNKNOWN", "-", "Video presence was not provided in the data.")
    elif listing.has_video:
        add("Product video", "PASS", "-", "Listing has a product video.")
    else:
        add("Product video", "FAIL", "Low",
            "No product video.",
            "Add a 30-90 second video covering key features and use-case.")

    return findings