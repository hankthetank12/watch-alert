"""
Site registry — add a new watch dealer by:
  1. Creating sites/<yoursite>.py implementing BaseScraper
  2. Importing it here and adding an instance to REGISTRY

main.py picks up all entries automatically.
"""

from .windvintage import WindVintageScraper
from .greyandpatina import GreyAndPatinaScraper
from .thekeystone import TheKeystoneScraper
from .sheartime import SheartimeScraper

REGISTRY: dict = {
    "windvintage":   WindVintageScraper(),
    "greyandpatina": GreyAndPatinaScraper(),
    # "thekeystone":   TheKeystoneScraper(),
    # "sheartime":     SheartimeScraper(),
}
