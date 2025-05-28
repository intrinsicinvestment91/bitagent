from src.agents.base_agent import BaseAgent

class CameraFeedBot(BaseAgent):
    def __init__(self):
        super().__init__("CameraFeedBot", "traffic_camera")
        self.price_sat = 5000

    def provide_data(self):
        return {
            "city": "Oslo",
            "traffic_index": 0.73,
            "timestamp": "2025-05-27T12:00:00Z"
        }

    def advertise_service(self):
        return {
            "kind": 30078,
            "pubkey": "npub" + self.id[-12:],  # placeholder for Nostr pubkey
            "tags": [["t", "service:ai"], ["price", str(self.price_sat)]],
            "content": {
                "service": "Provides 5-minute HD traffic feed",
                "did": self.id,
                "price_sat": self.price_sat,
                "note": "offered by CameraFeedBot"
            }
        }
