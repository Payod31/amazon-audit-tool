import yaml

from src.auditor.basic_rules import RULES_PATH


def load_weights():
    with open(RULES_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f).get("weights", {})


def score_findings(findings):
    weights = load_weights()
    earned = 0
    total = 0
    for f in findings:
        if f["status"] in ("UNKNOWN", "REVIEW"):
            continue
        w = weights.get(f["check"], 10)
        total += w
        if f["status"] == "PASS":
            earned += w
    if total == 0:
        return None
    return round(earned / total * 100)