import yaml
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "marketplaces.yaml"

def load_marketplaces():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def get_marketplace(key):
    data = load_marketplaces()
    if key not in data:
        raise ValueError(f"Unknown marketplace '{key}'. Available: {list(data)}")
    return data[key]

def is_rtl(marketplace, language):
    return language in marketplace.get("rtl_languages", [])