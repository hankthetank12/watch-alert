#!/usr/bin/env python3
"""Multi-site watch inventory alert system."""

import argparse
import logging
import logging.handlers
import os
import sys

from dotenv import load_dotenv

load_dotenv()

from sites import REGISTRY
from sites.base import BaseScraper
from state import get_new_watches, load_state, save_state
from notifier import send_alert

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _setup_logging() -> None:
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    root.addHandler(console)

    rotating = logging.handlers.RotatingFileHandler(
        "app.log", maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    rotating.setFormatter(fmt)
    root.addHandler(rotating)


logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Per-site scrape + diff (no email here)
# ---------------------------------------------------------------------------

def _check_site(scraper: BaseScraper, force_alert: bool = False) -> tuple[list[dict], dict | None]:
    """
    Scrape one site and return (new_watches, current_inventory).
    Returns ([], None) on scrape failure so the caller can skip saving state.
    """
    logger.info("[%s] Checking inventory...", scraper.name)
    try:
        current = scraper.fetch_inventory()
    except RuntimeError as exc:
        logger.error("[%s] Scrape failed, skipping: %s", scraper.name, exc)
        return [], None

    previous = load_state(scraper.key)

    if previous is None:
        save_state(scraper.key, current)
        logger.info("[%s] Baseline saved: %d watches", scraper.name, len(current))
        return [], None  # no alert on first run

    if force_alert:
        new_watches = [{"slug": s, **d} for s, d in current.items()]
        logger.info("[%s] --force-alert: %d watches", scraper.name, len(new_watches))
    else:
        new_watches = get_new_watches(current, previous)

    if new_watches:
        scraper.enrich(new_watches)
        logger.info("[%s] %d new watch(es):", scraper.name, len(new_watches))
        for w in new_watches:
            partner_tag = " [partner]" if w.get("is_partner") else ""
            price_tag = f" {w['price']}" if w.get("price") else ""
            logger.info("  + %s%s%s — %s", w["title"], price_tag, partner_tag, w["url"])
    else:
        logger.info("[%s] No new watches.", scraper.name)

    return new_watches, current


# ---------------------------------------------------------------------------
# Main cycle — checks all sites, sends one consolidated email
# ---------------------------------------------------------------------------

def run_all_sites(test_mode: bool = False, force_alert: bool = False,
                  only_sites: list[str] | None = None) -> None:
    sites = {k: v for k, v in REGISTRY.items() if not only_sites or k in only_sites}
    if not sites:
        logger.warning("No matching sites. Available: %s", list(REGISTRY))
        return

    new_by_site: dict[str, list[dict]] = {}
    current_by_site: dict[str, dict] = {}

    for key, scraper in sites.items():
        try:
            new_watches, current = _check_site(scraper, force_alert=force_alert)
        except Exception as exc:
            logger.exception("Unhandled error checking %s: %s", scraper.name, exc)
            continue

        if current is None:
            continue  # scrape failed or first-run baseline — skip

        if new_watches:
            new_by_site[scraper.name] = new_watches
        current_by_site[key] = current

    # Send one email covering all sites with new watches
    if new_by_site:
        if test_mode:
            logger.info("--test mode: would send alert covering: %s",
                        {k: len(v) for k, v in new_by_site.items()})
        else:
            try:
                send_alert(new_by_site)
            except Exception as exc:
                logger.error("Email failed (%s) — state will still be saved", exc)

    # Save state for every site that scraped successfully (after email attempt)
    for key, current in current_by_site.items():
        if not force_alert:
            save_state(key, current)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Multi-site watch inventory alert system")
    parser.add_argument("--once", action="store_true", help="Run one check and exit (for cron)")
    parser.add_argument("--test", action="store_true", help="Print alerts without sending email")
    parser.add_argument("--force-alert", action="store_true", help="Alert on entire current inventory")
    parser.add_argument("--sites", nargs="+", metavar="KEY",
                        help=f"Only check these site keys (available: {list(REGISTRY)})")
    parser.add_argument("--list-sites", action="store_true", help="Print registered sites and exit")
    return parser.parse_args()


def main() -> None:
    _setup_logging()
    args = _parse_args()

    if args.list_sites:
        print("Registered sites:")
        for key, scraper in REGISTRY.items():
            print(f"  {key:20s}  {scraper.name}  ({scraper.base_url})")
        return

    kwargs = dict(test_mode=args.test, force_alert=args.force_alert, only_sites=args.sites)

    if args.once or args.test or args.force_alert:
        run_all_sites(**kwargs)
        return

    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
    except ImportError:
        logger.error("APScheduler not installed. Run: pip install apscheduler")
        sys.exit(1)

    interval = int(os.environ.get("CHECK_INTERVAL_MINUTES", "15"))
    logger.info("Starting scheduler — %d site(s), every %d min. Ctrl+C to stop.",
                len(args.sites or REGISTRY), interval)

    scheduler = BlockingScheduler()
    scheduler.add_job(
        lambda: run_all_sites(**kwargs),
        trigger="interval",
        minutes=interval,
        id="inventory_check",
        max_instances=1,
    )

    run_all_sites(**kwargs)  # immediate first run

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped.")


if __name__ == "__main__":
    main()
