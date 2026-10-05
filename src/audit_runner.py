from src.auditor.aplus_rules import run_aplus_audit
from src.auditor.basic_rules import run_basic_audit
from src.auditor.image_rules import run_image_audit
from src.auditor.scoring import score_findings


def audit_all(provider):
    summary = []
    issues = []
    for asin, marketplace in provider.list_asins():
        listing = provider.get_listing(asin, marketplace)
        findings = (
            run_basic_audit(listing)
            + run_image_audit(listing)
            + run_aplus_audit(listing)
        )
        fails = sum(1 for f in findings if f["status"] == "FAIL")

        summary.append({
            "ASIN": listing.asin,
            "Marketplace": listing.marketplace,
            "Language": listing.language,
            "Brand": listing.brand,
            "Score (/100)": score_findings(findings),
            "Checks failed": fails,
            "Data source": listing.source,
            "Fetched at": listing.fetched_at,
        })
        for f in findings:
            issues.append({
                "ASIN": listing.asin,
                "Marketplace": listing.marketplace,
                "Check": f["check"],
                "Status": f["status"],
                "Severity": f["severity"],
                "Finding": f["finding"],
                "Fix": f["fix"],
            })
    return summary, issues