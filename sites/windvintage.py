import logging
import os
import time
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from .base import BaseScraper

logger = logging.getLogger(__name__)

PARTNER_DOMAINS = {"kith.com", "www.kith.com", "mrporter.com", "www.mrporter.com"}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


class WindVintageScraper(BaseScraper):
    key = "windvintage"
    name = "Wind Vintage"
    base_url = "https://www.windvintage.com/"

    def fetch_inventory(self, max_retries: int = 3) -> dict:
        include_partner = os.environ.get("INCLUDE_PARTNER_LISTINGS", "true").lower() != "false"
        last_exc = None

        for attempt in range(1, max_retries + 1):
            try:
                with httpx.Client(headers=HEADERS, timeout=30, follow_redirects=True) as client:
                    resp = client.get(self.base_url)
                    resp.raise_for_status()
                inventory = self._parse(resp.text, include_partner=include_partner)
                if not inventory:
                    raise RuntimeError("Parsed 0 watches — site structure may have changed")
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

    def _parse(self, html: str, include_partner: bool) -> dict:
        soup = BeautifulSoup(html, "html.parser")
        inventory = {}

        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"].strip()
            if not href or href.startswith("#") or href.startswith("mailto:"):
                continue

            full_url = urljoin(self.base_url, href)
            domain = urlparse(full_url).netloc
            is_partner = domain in PARTNER_DOMAINS

            if is_partner and not include_partner:
                continue

            # Listing cards always wrap an image
            if not a_tag.find("img"):
                continue

            img = a_tag.find("img")
            title = (img.get("alt") or "").strip() or a_tag.get_text(separator=" ", strip=True)
            if not title:
                continue

            slug = urlparse(full_url).path.strip("/") or full_url
            if slug in inventory:
                continue

            inventory[slug] = {
                "title": title,
                "url": full_url,
                "is_partner": is_partner,
            }

        return inventory
