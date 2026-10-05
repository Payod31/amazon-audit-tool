import csv
from pathlib import Path

from src.core.models import Listing
from src.providers.base import DataProvider


def _number(value, cast):
    value = (value or "").strip()
    if value == "":
        return None
    try:
        return cast(value)
    except ValueError:
        return None


def _yes_no(value):
    value = (value or "").strip().lower()
    if value in ("yes", "y", "true", "1"):
        return True
    if value in ("no", "n", "false", "0"):
        return False
    return None


def _pipe_list(value):
    """Turns 'url1|url2|url3' into ['url1', 'url2', 'url3']. Empty -> []."""
    value = (value or "").strip()
    if not value:
        return []
    return [v.strip() for v in value.split("|") if v.strip()]


class CsvProvider(DataProvider):
    name = "csv_upload"

    def __init__(self, path):
        self.path = Path(path)
        self.rows = {}
        self._load()

    def _load(self):
        # utf-8-sig also handles CSVs saved by Excel
        with open(self.path, newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                key = (row["asin"].strip().upper(), row["marketplace"].strip())
                self.rows[key] = row

    def list_asins(self):
        return list(self.rows.keys())

    def get_listing(self, asin, marketplace):
        row = self.rows.get((asin.strip().upper(), marketplace))
        if row is None:
            raise KeyError(f"{asin} / {marketplace} not found in {self.path.name}")

        bullets = [row.get(f"bullet_{i}", "").strip() for i in range(1, 6)]
        bullets = [b for b in bullets if b]

        return Listing(
            asin=row["asin"].strip().upper(),
            marketplace=row["marketplace"].strip(),
            language=row["language"].strip(),
            title=row.get("title", "").strip(),
            bullets=bullets,
            description=row.get("description", "").strip(),
            brand=row.get("brand", "").strip(),
            price=_number(row.get("price"), float),
            rating=_number(row.get("rating"), float),
            review_count=_number(row.get("review_count"), int),
            image_count=_number(row.get("image_count"), int),
            has_aplus=_yes_no(row.get("has_aplus")),
            buy_box_seller=row.get("buy_box_seller", "").strip(),
            fulfilled_by=row.get("fulfilled_by", "").strip(),
            image_urls=_pipe_list(row.get("image_urls")),
            main_image_url=row.get("main_image_url", "").strip(),
            has_video=_yes_no(row.get("has_video")),
            aplus_basic_desktop_urls=_pipe_list(row.get("aplus_basic_desktop_urls")),
            aplus_premium_desktop_urls=_pipe_list(row.get("aplus_premium_desktop_urls")),
            aplus_premium_mobile_urls=_pipe_list(row.get("aplus_premium_mobile_urls")),
            source=self.name,
        )