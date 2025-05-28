import unittest
from src.agents.camera_feed_bot import CameraFeedBot
from src.agents.databot import DataBot

class TestAgents(unittest.TestCase):

    def test_camera_feed_advertisement_contains_expected_fields(self):
        bot = CameraFeedBot()
        ad = bot.advertise_service()
        self.assertEqual(ad["kind"], 30078)
        self.assertIn("pubkey", ad)
        self.assertIn("tags", ad)
        self.assertIn("content", ad)
        self.assertEqual(ad["content"]["price_sat"], 5000)

    def test_databot_accepts_valid_token_and_returns_data(self):
        databot = DataBot()
        token = {
            "token_id": "abc123",
            "amount_sat": 5000,
            "sender": "Cambot",
            "redeemed": False
        }
        data = databot.serve_data(token)
        self.assertIsNotNone(data)
        self.assertIn("traffic_index", data)

    def test_databot_rejects_token_with_wrong_amount(self):
        databot = DataBot()
        token = {
            "token_id": "abc124",
            "amount_sat": 1000,
            "sender": "Cambot",
            "redeemed": False
        }
        data = databot.serve_data(token)
        self.assertIsNone(data)

    def test_databot_rejects_already_redeemed_token(self):
        databot = DataBot()
        token = {
            "token_id": "abc125",
            "amount_sat": 5000,
            "sender": "Cambot",
            "redeemed": True
        }
        data = databot.serve_data(token)
        self.assertIsNone(data)

if __name__ == "__main__":
    unittest.main()
