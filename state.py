import json
import logging
import os

logger = logging.getLogger(__name__)

DEFAULT_STATE_DIR = "."


def _state_path(site_key: str) -> str:
    state_dir = os.environ.get("STATE_DIR", DEFAULT_STATE_DIR)
    # Allow per-site override via STATE_FILE_WINDVINTAGE, STATE_FILE_HODINKEE, etc.
    env_override = os.environ.get(f"STATE_FILE_{site_key.upper()}")
    if env_override:
        return env_override
    return os.path.join(state_dir, f"state_{site_key}.json")


def load_state(site_key: str) -> dict | None:
    """Return previously saved inventory for a site, or None on first run."""
    path = _state_path(site_key)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("[%s] Failed to load state from %s: %s", site_key, path, exc)
        return None


def save_state(site_key: str, inventory: dict) -> None:
    path = _state_path(site_key)
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(inventory, f, indent=2, ensure_ascii=False)
        logger.debug("[%s] State saved to %s (%d watches)", site_key, path, len(inventory))
    except OSError as exc:
        logger.error("[%s] Failed to save state to %s: %s", site_key, path, exc)


def get_new_watches(current: dict, previous: dict) -> list[dict]:
    """Return watches present in current but absent in previous, each with its slug included."""
    return [{"slug": slug, **data} for slug, data in current.items() if slug not in previous]
