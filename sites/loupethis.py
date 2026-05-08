import logging
import re
import time

import httpx

from .base import BaseScraper

logger = logging.getLogger(__name__)

SANITY_PROJECT_ID = "j0ua8uvr"
SANITY_DATASET = "production"
SANITY_API_VERSION = "2021-10-21"

# Fetch the 300 most recently created auction documents
GROQ_QUERY = (
    '*[_type == "auction"] | order(_createdAt desc) [0..299]'
    '{_id, inventoryNumber, "title": seoSettings.title,'
    ' "priceRange": content[_type == "auctionScorecard"][0].range}'
)


def _slugify(title: str) -> str:
    slug = title.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"\s+", "-", slug)
    return slug.strip("-")


def _format_price(price_range: dict | None) -> str:
    if not price_range:
        return ""
    start = price_range.get("start")
    end = price_range.get("end")
    if start and end:
        return f"Est. ${start:,}–${end:,}"
    if start:
        return f"Est. ${start:,}+"
    return ""


class LoupeThisScraper(BaseScraper):
    key = "loupethis"
    name = "Loupe This"
    base_url = "https://www.loupethis.com/auctions"

    def fetch_inventory(self, max_retries: int = 3) -> dict:
        api_url = (
            f"https://{SANITY_PROJECT_ID}.api.sanity.io"
            f"/v{SANITY_API_VERSION}/data/query/{SANITY_DATASET}"
        )
        last_exc = None
        for attempt in range(1, max_retries + 1):
            try:
                with httpx.Client(timeout=30) as client:
                    resp = client.get(api_url, params={"query": GROQ_QUERY})
                    resp.raise_for_status()
                    data = resp.json()
                inventory = self._parse(data.get("result", []))
                if not inventory:
                    raise RuntimeError("Parsed 0 listings — API response may have changed")
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

    def _parse(self, results: list) -> dict:
        inventory = {}
        for item in results:
            inv_num = (item.get("inventoryNumber") or "").strip()
            if not inv_num:
                continue

            title = (item.get("title") or "").strip()
            if not title:
                continue

            slug = _slugify(title)
            url = f"https://www.loupethis.com/auctions/{slug}"
            price = _format_price(item.get("priceRange"))

            inventory[inv_num] = {"title": title, "url": url, "price": price}

        return inventory
