from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Listing:
    asin: str
    marketplace: str
    language: str
    title: str = ""
    bullets: list = field(default_factory=list)
    description: str = ""
    brand: str = ""
    price: float | None = None
    rating: float | None = None
    review_count: int | None = None
    image_count: int | None = None
    has_aplus: bool | None = None
    buy_box_seller: str = ""
    fulfilled_by: str = ""
    # Images (Step 4a)
    image_urls: list = field(default_factory=list)
    main_image_url: str = ""
    has_video: bool | None = None
    # A+ images, by module type (Step 4b)
    aplus_basic_desktop_urls: list = field(default_factory=list)
    aplus_premium_desktop_urls: list = field(default_factory=list)
    aplus_premium_mobile_urls: list = field(default_factory=list)
    # Provenance: where this data came from and when
    source: str = "unknown"
    fetched_at: str = field(
        default_factory=lambda: datetime.now().isoformat(timespec="seconds")
    )