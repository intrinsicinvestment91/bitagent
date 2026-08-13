"""Streamfinder — the A2A JSON-RPC reference implementation.

This agent exists to demonstrate the agent-to-agent request shape, not to answer
real questions about streaming availability. Its dataset is three hardcoded
titles. It used to charge 100 sats for that, which meant callers paid real money
for fabricated results; it is now free and every response says so.

To turn this into a real service, replace ``perform_search`` with a call to an
actual availability API (JustWatch, Reelgood, TMDB watch-providers) and register
a non-zero price in ``src/payments/catalog.py``. The catalog will reject a price
above zero while ``synthetic=True``, so the label and the price cannot drift
apart.
"""

import json
import logging

from src.payments import get_service

SERVICE_ID = "streamfinder.search"

#: Fixed demo dataset. Not a data source — see the module docstring.
DEMO_TITLES: dict[str, list[str]] = {
    "Oppenheimer": ["Peacock", "Amazon Prime Video"],
    "Breaking Bad": ["Netflix"],
    "The Matrix": ["HBO Max", "Amazon Prime Video", "iTunes"],
}

_DEMO_NOTICE = (
    "Demo output. Streamfinder is the A2A reference implementation and answers "
    "from a fixed three-title dataset, not a real streaming availability API. "
    "It is free of charge."
)


class StreamfinderAgent:
    def __init__(self, config_path: str = None):
        self.name = "Streamfinder"
        self.version = "0.2"
        self.config = self.load_config(config_path)
        logging.info("%s v%s initialized (synthetic demo).", self.name, self.version)

    def load_config(self, path):
        if path:
            try:
                with open(path) as f:
                    return json.load(f)
            except OSError as e:
                logging.warning("Could not load config from %s: %s", path, e)
        return {}

    @property
    def price_sats(self) -> int:
        return get_service(SERVICE_ID).effective_price

    def get_price(self) -> int:
        """Cost in sats for a search. Zero — this agent returns demo data."""
        return self.price_sats

    def get_info(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            **get_service(SERVICE_ID).info(),
        }

    def perform_search(self, query: str) -> dict:
        """Look a title up in the fixed demo dataset."""
        matches = {
            title: platforms
            for title, platforms in DEMO_TITLES.items()
            if query.lower() in title.lower()
        }

        result = {
            "query": query,
            "found": bool(matches),
            "synthetic": True,
            "notice": _DEMO_NOTICE,
        }
        if matches:
            result["results"] = matches
        else:
            result["message"] = f"No matching title in the demo dataset ({', '.join(DEMO_TITLES)})."
        return result
