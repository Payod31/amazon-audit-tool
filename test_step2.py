import sys

from src.providers.csv_provider import CsvProvider
from src.auditor.basic_rules import run_basic_audit

# Lets Windows print Arabic, German, etc. without crashing
sys.stdout.reconfigure(encoding="utf-8")

provider = CsvProvider("sample_data/sample_listings.csv")
print(f"Data source: {provider.name}")
print(f"Found {len(provider.list_asins())} listings\n")

for asin, marketplace in provider.list_asins():
    listing = provider.get_listing(asin, marketplace)
    findings = run_basic_audit(listing)
    fails = [f for f in findings if f["status"] == "FAIL"]

    print("=" * 70)
    print(f"{listing.asin} | {listing.marketplace} | {listing.language} | brand: {listing.brand}")
    print(f"Title: {listing.title}")
    print(f"Checks failed: {len(fails)} of {len(findings)}")
    print("-" * 70)
    for f in findings:
        print(f"[{f['status']}] {f['check']}: {f['finding']}")
        if f["fix"]:
            print(f"        Fix: {f['fix']}")
    print()