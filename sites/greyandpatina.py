import logging
import re
import time
from urllib.parse import urljoin, urlparse

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
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


class GreyAndPatinaScraper(BaseScraper):
    key = "greyandpatina"
    name = "Grey and Patina"
    base_url = "https://www.greyandpatina.com/shop"

    def fetch_inventory(self, max_retries: int = 3) -> dict:
        last_exc = None
        for attempt in range(1, max_retries + 1):
            try:
                with httpx.Client(headers=HEADERS, timeout=30, follow_redirects=True) as client:
                    resp = client.get(self.base_url)
                    resp.raise_for_status()
                inventory = self._parse(resp.text)
                if not inventory:
                    raise RuntimeError("Parsed 0 listings — site structure may have changed")
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

        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"].strip()

            if "/product/" not in href:
                continue

            full_url = urljoin("https://www.greyandpatina.com", href)
            slug = urlparse(full_url).path.strip("/").split("/")[-1]
            if not slug or slug in inventory:
                continue

            # All text (title + SOLD + price) is inside the <a> tag — no img alt
            link_text = a_tag.get_text(separator=" ", strip=True)

            # Extract price directly from link text
            price_match = re.search(r"\$[\d,]+", link_text)
            price = price_match.group(0) if price_match else ""

            # Clean title: strip SOLD label and price
            title = re.sub(r"\bSOLD\b", "", link_text, flags=re.IGNORECASE)
            title = re.sub(r"\$[\d,]+", "", title).strip(" -–")
            if not title:
                continue

            inventory[slug] = {"title": title, "url": full_url, "price": price}

        return inventory
