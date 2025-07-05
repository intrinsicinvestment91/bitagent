# streamfinder.py

import json
import logging

class StreamfinderAgent:
    def __init__(self, config_path: str = None):
        self.name = "Streamfinder"
        self.version = "0.1"
        self.price_sats = 100  # flat fee per search
        self.config = self.load_config(config_path)
        logging.info(f"{self.name} v{self.version} initialized.")

    def load_config(self, path):
        if path:
            try:
                with open(path, "r") as f:
                    return json.load(f)
            except Exception as e:
                logging.warning(f"Could not load config from {path}: {e}")
        return {}

    def get_price(self):
        """Return the cost (in sats) for a stream search request."""
        return self.price_sats

    def perform_search(self, query: str) -> dict:
        """
        Simulate a platform availability search.
        Replace this logic with a real API like JustWatch or Reelgood later.
        """
        dummy_db = {
            "Oppenheimer": ["Peacock", "Amazon Prime Video"],
            "Breaking Bad": ["Netflix"],
            "The Matrix": ["HBO Max", "Amazon Prime Video", "iTunes"],
        }

        matches = {
            title: platforms
            for title, platforms in dummy_db.items()
            if query.lower() in title.lower()
        }

        if not matches:
            return {
                "query": query,
                "found": False,
                "message": "No matching title found.",
            }

        return {
            "query": query,
            "found": True,
            "results": matches,
        }
