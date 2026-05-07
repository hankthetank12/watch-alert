import logging
import os
import re
import time
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup, NavigableString

from .base import BaseScraper

logger = logging.getLogger(__name__)

PARTNER_DOMAINS = {"kith.com", "www.kith.com", "mrporter.com", "www.mrporter.com",
                   "net-a-porter.com", "www.net-a-porter.com"}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

KITH_SECTION_MARKER = "Kith Beverly Hills"


class WindVintageScraper(BaseScraper):
    key = "windvintage"
    name = "Wind Vintage"
    base_url = "https://www.windvintage.com/"

    def fetch_inventory(self, max_retries: int = 3) -> dict:
        last_exc = None
        for attempt in range(1, max_retries + 1):
            try:
                with httpx.Client(headers=HEADERS, timeout=30, follow_redirects=True) as client:
                    resp = client.get(self.base_url)
                    resp.raise_for_status()
                inventory = self._parse(resp.text)
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

    def _parse(self, html: str) -> dict:
        soup = BeautifulSoup(html, "html.parser")
        inventory = {}

        # Walk the document in order, stopping when we hit the Kith section heading
        for node in soup.descendants:
            if isinstance(node, NavigableString) and KITH_SECTION_MARKER in node:
                break  # everything from here on is partner/external sections

            if not getattr(node, "name", None) == "a":
                continue

            a_tag = node
            href = (a_tag.get("href") or "").strip()
            if not href or href.startswith("#") or href.startswith("mailto:"):
                continue

            full_url = urljoin(self.base_url, href)
            if urlparse(full_url).netloc in PARTNER_DOMAINS:
                continue

            # Must be a listing card (wraps an image)
            if not a_tag.find("img"):
                continue

            img = a_tag.find("img")
            title = (img.get("alt") or "").strip() or a_tag.get_text(separator=" ", strip=True)
            if not title:
                continue

            slug = urlparse(full_url).path.strip("/") or full_url
            if slug in inventory:
                continue

            inventory[slug] = {"title": title, "url": full_url}

        return inventory

    def enrich(self, watches: list[dict]) -> None:
        """Fetch the price from each new watch's individual page."""
        with httpx.Client(headers=HEADERS, timeout=15, follow_redirects=True) as client:
            for watch in watches:
                watch["price"] = self._fetch_price(watch["url"], client)
                if watch["price"]:
                    logger.debug("[%s] Price for %s: %s", self.name, watch["title"], watch["price"])

    def _fetch_price(self, url: str, client: httpx.Client) -> str:
        try:
            resp = client.get(url)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            for node in soup.find_all(string=re.compile(r"PRICE", re.IGNORECASE)):
                # Price is in an adjacent <a> (mailto link) or sibling text
                parent = node.parent
                a = parent.find_next("a")
                if a:
                    text = a.get_text(strip=True)
                    if "$" in text:
                        return text
                # Also check for plain text price after the PRICE: label
                siblings = list(parent.next_siblings)
                for sib in siblings[:3]:
                    text = sib.get_text(strip=True) if hasattr(sib, "get_text") else str(sib).strip()
                    if "$" in text:
                        return text
        except Exception as exc:
            logger.debug("[%s] Could not fetch price for %s: %s", self.name, url, exc)
        return ""
