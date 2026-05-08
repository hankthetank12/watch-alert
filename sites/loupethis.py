import logging
import re
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx

from .base import BaseScraper

logger = logging.getLogger(__name__)

SANITY_PROJECT_ID = "j0ua8uvr"
SANITY_DATASET = "production"
SANITY_API_VERSION = "2021-10-21"

# Only fetch auctions created within this window.
# Loupe This auctions run 2–4 weeks, so 60 days captures all live ones
# while excluding years of ended auction history.
_ACTIVE_WINDOW_DAYS = 60


def _build_query() -> str:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=_ACTIVE_WINDOW_DAYS)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    return (
        f'*[_type == "auction" && _createdAt > "{cutoff}"]'
        ' | order(_createdAt desc)'
        '{_id, inventoryNumber, "title": seoSettings.title, content}'
    )


def _slugify(title: str) -> str:
    slug = title.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"\s+", "-", slug)
    return slug.strip("-")


def _extract_price(content) -> str:
    if not content:
        return ""
    for block in content:
        if isinstance(block, dict) and block.get("_type") == "auctionScorecard":
            r = block.get("range") or {}
            start = r.get("start")
            end = r.get("end")
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
        # Build URL manually so the query string is encoded exactly once
        base = f"https://{SANITY_PROJECT_ID}.api.sanity.io/v{SANITY_API_VERSION}/data/query/{SANITY_DATASET}"
        api_url = f"{base}?{urlencode({'query': _build_query()})}"

        last_exc = None
        for attempt in range(1, max_retries + 1):
            try:
                with httpx.Client(timeout=30, follow_redirects=True) as client:
                    resp = client.get(api_url)
                    if resp.status_code != 200:
                        raise RuntimeError(
                            f"API returned HTTP {resp.status_code}: {resp.text[:200]}"
                        )
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
            price = _extract_price(item.get("content"))

            inventory[inv_num] = {"title": title, "url": url, "price": price}

        return inventory
