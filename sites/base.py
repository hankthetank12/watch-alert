from abc import ABC, abstractmethod


class BaseScraper(ABC):
    """
    Implement this for each watch dealer site, then register the instance
    in sites/__init__.py. That's the only change needed to add a new site.
    """

    @property
    @abstractmethod
    def key(self) -> str:
        """Unique machine-readable identifier used for state file naming, e.g. 'windvintage'."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable display name used in logs and email alerts."""
        ...

    @property
    @abstractmethod
    def base_url(self) -> str:
        """Primary URL that is scraped."""
        ...

    @abstractmethod
    def fetch_inventory(self) -> dict:
        """
        Fetch and parse the current inventory.

        Returns a dict keyed by a stable unique slug:
            { slug: { "title": str, "url": str, **extra } }

        Raises RuntimeError if the scrape fails or returns 0 items.
        The caller will catch this and skip the cycle without touching state.
        """
        ...

    def enrich(self, watches: list[dict]) -> None:
        """
        Optionally fetch extra details (e.g. price) for a list of new watches.
        Modifies each watch dict in place. Override in subclasses as needed.
        """
        pass
