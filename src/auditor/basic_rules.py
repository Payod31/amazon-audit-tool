from pathlib import Path

import yaml

RULES_PATH = Path(__file__).resolve().parents[2] / "config" / "rules.yaml"


def load_rules(language):
    with open(RULES_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    rules = dict(data["default"])
    rules.update(data.get("overrides", {}).get(language, {}))
    return rules


def run_basic_audit(listing):
    r = load_rules(listing.language)
    findings = []

    def add(check, status, severity, finding, fix=""):
        findings.append({
            "check": check, "status": status, "severity": severity,
            "finding": finding, "fix": fix,
        })

    # 1. Title length
    n = len(listing.title)
    if n < r["title_min_chars"]:
        add("Title length", "FAIL", "High",
            f"Title has only {n} characters (recommended {r['title_min_chars']}+).",
            "Add brand, product type, key feature, size/quantity and a main keyword.")
    elif n > r["title_max_chars"]:
        add("Title length", "FAIL", "Medium",
            f"Title has {n} characters (limit {r['title_max_chars']}).",
            "Shorten the title and move extra keywords into bullets or backend terms.")
    else:
        add("Title length", "PASS", "-", f"Title length is good ({n} characters).")

    # 2. Bullet points
    b = len(listing.bullets)
    if b < r["min_bullets"]:
        add("Bullet points", "FAIL", "High",
            f"Only {b} bullets (recommended {r['min_bullets']}).",
            "Fill all 5 bullets: benefit first, then the feature, then the proof.")
    else:
        add("Bullet points", "PASS", "-", f"{b} bullets present.")

    # 3. Images
    if listing.image_count is None:
        add("Image count", "UNKNOWN", "-", "Image count missing from the data.")
    elif listing.image_count < r["min_images"]:
        add("Image count", "FAIL", "High",
            f"Only {listing.image_count} images (recommended {r['min_images']}+).",
            "Add infographic, lifestyle, size, comparison and packaging images.")
    else:
        add("Image count", "PASS", "-", f"{listing.image_count} images.")

    # 4. A+ Content
    if listing.has_aplus is False:
        add("A+ Content", "FAIL", "High",
            "No A+ Content on this listing.",
            "Add A+ with a brand story, feature modules and a comparison chart.")
    elif listing.has_aplus is True:
        add("A+ Content", "PASS", "-", "A+ Content present.")
    else:
        add("A+ Content", "UNKNOWN", "-", "A+ status missing from the data.")

    # 5. Rating
    if listing.rating is None:
        add("Rating", "UNKNOWN", "-", "Rating missing from the data.")
    elif listing.rating < r["min_rating"]:
        add("Rating", "FAIL", "High",
            f"Rating is {listing.rating} (target {r['min_rating']}+).",
            "Read the 1-3 star reviews, find repeated complaints, fix the product or the listing promise.")
    else:
        add("Rating", "PASS", "-", f"Rating {listing.rating} is healthy.")

    return findings