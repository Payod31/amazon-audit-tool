from abc import ABC, abstractmethod


class DataProvider(ABC):
    """Every data source (CSV, SP-API, Keepa...) must implement these."""

    name = "base"

    @abstractmethod
    def get_listing(self, asin, marketplace):
        """Return a Listing object for this ASIN and marketplace."""

    def list_asins(self):
        """Return all (asin, marketplace) pairs this source knows about."""
        return []