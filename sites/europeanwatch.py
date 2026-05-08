import logging
import re
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
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


class EuropeanWatchScraper(BaseScraper):
    key = "europeanwatch"
    name = "European Watch Co."
    base_url = "https://www.europeanwatch.com/new"

    def fetch_inventory(self, max_retries: int = 3) -> dict:
        last_exc = None
        for attempt in range(1, max_retries + 1):
            try:
                # verify=False needed: TLS cert covers europeanwatchco.com but not
                # the www.europeanwatch.com subdomain served from the same host
                with httpx.Client(headers=HEADERS, timeout=30,
                                  follow_redirects=True, verify=False) as client:
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

        for a_tag in soup.find_all("a", href=re.compile(r"^/watch/")):
            href = a_tag["href"]

            # Only process the card anchor — it contains h3 tags for brand/model.
            # The duplicate "View Watch" anchor has no h3 children.
            h3_tags = a_tag.find_all("h3")
            if len(h3_tags) < 2:
                continue

            # Numeric ID at the end of the slug is the stable watch identifier
            watch_id = href.rstrip("/").split("-")[-1]
            if not watch_id.isdigit() or watch_id in inventory:
                continue

            brand = h3_tags[0].get_text(strip=True)
            model = h3_tags[1].get_text(strip=True)
            if not brand or not model:
                continue
            title = f"{brand} {model}"

            price_tag = a_tag.find("p")
            price = price_tag.get_text(strip=True) if price_tag else ""

            full_url = f"https://www.europeanwatch.com{href}"
            inventory[watch_id] = {"title": title, "url": full_url, "price": price}

        return inventory
