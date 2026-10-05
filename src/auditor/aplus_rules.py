import yaml

from src.auditor.basic_rules import RULES_PATH
from src.auditor.image_rules import download_image


def _load_aplus_rules():
    with open(RULES_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("aplus", {})


def run_aplus_audit(listing):
    r = _load_aplus_rules()
    specs = r.get("specs", {})
    tolerance = r.get("tolerance_px", 5)
    findings = []

    def add(check, status, severity, finding, fix=""):
        findings.append({
            "check": check, "status": status, "severity": severity,
            "finding": finding, "fix": fix,
        })

    # No A+ at all -> nothing to check here (the "A+ Content" basic check
    # already covers the fact that it's missing)
    if listing.has_aplus is not True:
        add("A+ image dimensions", "UNKNOWN", "-",
            "Listing has no A+ Content, so there are no A+ images to check.")
        return findings

    groups = {
        "basic_desktop": listing.aplus_basic_desktop_urls,
        "premium_desktop": listing.aplus_premium_desktop_urls,
        "premium_mobile": listing.aplus_premium_mobile_urls,
    }

    if not any(groups.values()):
        add("A+ image dimensions", "UNKNOWN", "-",
            "This listing has A+ Content, but no A+ image URLs were provided to check dimensions.")
        return findings

    mismatches = []
    failed_downloads = []
    checked = 0

    for group_name, urls in groups.items():
        spec = specs.get(group_name)
        if not urls:
            continue
        if not spec:
            # We have images for this module type but no spec to check against
            continue
        for url in urls:
            img = download_image(url)
            if img is None:
                failed_downloads.append(f"{group_name}: {url}")
                continue
            checked += 1
            w, h = img.size
            if abs(w - spec["width"]) > tolerance or abs(h - spec["height"]) > tolerance:
                mismatches.append(
                    f"{group_name}: {w}x{h}px, expected {spec['width']}x{spec['height']}px"
                )

    if failed_downloads:
        add("A+ image dimensions", "UNKNOWN", "-",
            f"{len(failed_downloads)} A+ image URL(s) could not be downloaded.",
            "Check the URLs are correct and publicly reachable, then re-run.")
    elif checked == 0:
        add("A+ image dimensions", "UNKNOWN", "-",
            "No A+ images matched a known module type with a spec in rules.yaml, so none were checked.")
    elif mismatches:
        add("A+ image dimensions", "FAIL", "Medium",
            f"{len(mismatches)} A+ image(s) don't match the expected size: " + "; ".join(mismatches),
            "Re-export each A+ module image at the exact pixel size Seller Central specifies for that module.")
    else:
        add("A+ image dimensions", "PASS", "-",
            f"All {checked} checked A+ image(s) match their expected dimensions.")

    return findings