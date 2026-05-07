"""
Template for adding a new watch dealer site.

Steps:
  1. Copy this file to sites/<yoursite>.py
  2. Fill in key, name, base_url, and implement fetch_inventory()
  3. Import and register it in sites/__init__.py:
       from .yoursite import YourSiteScraper
       REGISTRY["yoursite"] = YourSiteScraper()
  4. That's it — main.py picks it up automatically.
"""

import logging
import time

import httpx
from bs4 import BeautifulSoup

from .base import BaseScraper

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}


class ExampleScraper(BaseScraper):
    key = "example"               # used for state_example.json and --sites flag
    name = "Example Watch Co."    # shown in logs and email subject
    base_url = "https://example-watches.com/inventory"

    def fetch_inventory(self, max_retries: int = 3) -> dict:
        last_exc = None
        for attempt in range(1, max_retries + 1):
            try:
                with httpx.Client(headers=HEADERS, timeout=30, follow_redirects=True) as client:
                    resp = client.get(self.base_url)
                    resp.raise_for_status()
                inventory = self._parse(resp.text)
                if not inventory:
                    raise RuntimeError("Parsed 0 items — check the CSS selectors")
                logger.info("[%s] Scraped %d listing(s)", self.name, len(inventory))
                return inventory
            except (httpx.HTTPError, RuntimeError) as exc:
                last_exc = exc
                if attempt < max_retries:
                    wait = 2 ** attempt
                    logger.warning("[%s] Attempt %d/%d failed: %s — retrying in %ds",
                                   self.name, attempt, max_retries, exc, wait)
                    time.sleep(wait)
        raise RuntimeError(f"Scrape failed after {max_retries} attempts") from last_exc

    def _parse(self, html: str) -> dict:
        soup = BeautifulSoup(html, "html.parser")
        inventory = {}

        # TODO: adapt these selectors to the target site's HTML structure
        for card in soup.select(".product-card"):
            a_tag = card.find("a", href=True)
            if not a_tag:
                continue

            href = a_tag["href"].strip()
            full_url = href if href.startswith("http") else self.base_url.rstrip("/") + "/" + href.lstrip("/")
            title = card.select_one(".product-title")
            title = title.get_text(strip=True) if title else a_tag.get_text(strip=True)
            if not title:
                continue

            # Derive a stable slug from the URL path
            from urllib.parse import urlparse
            slug = urlparse(full_url).path.strip("/") or full_url

            if slug not in inventory:
                inventory[slug] = {"title": title, "url": full_url}

        return inventory
