import logging
import re
import time
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from .base import BaseScraper

logger = logging.getLogger(__name__)


def _find_nearby_price(a_tag) -> str:
    """Climb up the DOM tree from an anchor tag looking for a $price."""
    node = a_tag.parent
    for _ in range(6):
        if node is None:
            break
        text = node.get_text(separator=" ", strip=True)
        m = re.search(r"\$[\d,]+", text)
        if m:
            return m.group(0)
        node = node.parent
    return ""


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


class TheKeystoneScraper(BaseScraper):
    key = "thekeystone"
    name = "The Keystone"
    base_url = "https://thekeystone.com/collections/all-watches"

    def fetch_inventory(self, max_retries: int = 3) -> dict:
        inventory = {}
        page = 1
        with httpx.Client(headers=HEADERS, timeout=30, follow_redirects=True) as client:
            while True:
                url = f"{self.base_url}?sort_by=created-descending&page={page}"
                last_exc = None
                page_inventory = None
                for attempt in range(1, max_retries + 1):
                    try:
                        resp = client.get(url)
                        resp.raise_for_status()
                        page_inventory = self._parse(resp.text)
                        break
                    except httpx.HTTPError as exc:
                        last_exc = exc
                        if attempt < max_retries:
                            wait = 2 ** attempt
                            logger.warning("[%s] Page %d attempt %d/%d failed: %s — retrying in %ds",
                                           self.name, page, attempt, max_retries, exc, wait)
                            time.sleep(wait)
                if page_inventory is None:
                    raise RuntimeError(f"Scrape failed on page {page} after {max_retries} attempts") from last_exc
                if not page_inventory:
                    break
                new_slugs = {k: v for k, v in page_inventory.items() if k not in inventory}
                inventory.update(new_slugs)
                if len(new_slugs) < len(page_inventory):
                    # All remaining slugs already seen — stop paginating
                    break
                page += 1

        if not inventory:
            raise RuntimeError("Parsed 0 listings — site structure may have changed")
        logger.info("[%s] Scraped %d listing(s) across %d page(s)", self.name, len(inventory), page - 1)
        return inventory

    def _parse(self, html: str) -> dict:
        soup = BeautifulSoup(html, "html.parser")
        inventory = {}

        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"].strip()

            if "/products/" not in href:
                continue

            full_url = urljoin("https://www.thekeystone.com", href)
            slug = urlparse(full_url).path.strip("/").split("/")[-1]
            if not slug or slug in inventory:
                continue

            # Title is in the img alt attribute
            img = a_tag.find("img")
            title = (img.get("alt") or "").strip() if img else ""
            if not title:
                title = a_tag.get_text(separator=" ", strip=True)
            if not title:
                continue

            # Strip "- The Keystone Watches" suffix and leading "Brand - Brand ..." duplication
            title = re.sub(r"\s*-\s*The Keystone Watches$", "", title, flags=re.IGNORECASE).strip()
            title = re.sub(r"^([^-]+)\s*-\s*\1", r"\1", title).strip()

            # Price is outside the <a> tag — climb up the DOM to find it
            price = _find_nearby_price(a_tag)

            inventory[slug] = {"title": title, "url": full_url, "price": price}

        return inventory
