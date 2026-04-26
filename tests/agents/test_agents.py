import unittest
from unittest.mock import Mock
from src.agents.camera_feed_bot import CameraFeedBot
from src.agents.databot import DataBot
from src.agents.base_agent import AgentProtocol, BaseAgent, validate_agent_info

class TestAgents(unittest.TestCase):

    def test_base_agent_legacy_constructor_and_identify_shape(self):
        agent = BaseAgent("alice", "consumer")
        identity = agent.identify()

        self.assertEqual(identity, {"name": "alice", "role": "consumer", "did": agent.id})
        self.assertIsInstance(identity["did"], str)
        self.assertTrue(identity["did"].startswith("did:"))

    def test_base_agent_get_info_and_service_metadata(self):
        agent = BaseAgent(
            "service-agent",
            "provider",
            description="Provides sample service",
            services=["translate", "search"],
        )

        info = agent.get_info()
        self.assertEqual(info["id"], agent.id)
        self.assertEqual(info["agent_id"], agent.id)
        self.assertEqual(info["name"], "service-agent")
        self.assertEqual(info["role"], "provider")
        self.assertEqual(info["did"], agent.id)
        self.assertEqual(info["description"], "Provides sample service")
        self.assertEqual(info["services"], ["translate", "search"])
        self.assertIsInstance(agent.list_services(), list)

    def test_validate_agent_info_accepts_base_agent_info(self):
        agent = BaseAgent("alice", "consumer")
        self.assertTrue(validate_agent_info(agent.get_info()))

    def test_validate_agent_info_fails_on_missing_required_key(self):
        info = {
            "id": "id-1",
            "name": "alice",
            "role": "consumer",
            "did": "did:example:alice",
            "description": "desc",
        }
        self.assertFalse(validate_agent_info(info))

    def test_validate_agent_info_fails_on_wrong_services_type(self):
        info = {
            "id": "id-1",
            "name": "alice",
            "role": "consumer",
            "did": "did:example:alice",
            "description": "desc",
            "services": "not-a-list",
        }
        self.assertFalse(validate_agent_info(info))

    def test_validate_agent_info_fails_on_empty_id(self):
        info = {
            "id": "",
            "name": "alice",
            "role": "consumer",
            "did": "did:example:alice",
            "description": "desc",
            "services": [],
        }
        self.assertFalse(validate_agent_info(info))

    def test_base_agent_default_services_and_did_accessors(self):
        agent = BaseAgent("bob", "consumer")

        self.assertEqual(agent.list_services(), [])
        self.assertEqual(agent.get_did(), agent.id)
        self.assertEqual(agent.get_agent_id(), agent.id)

    def test_base_agent_satisfies_agent_protocol(self):
        agent = BaseAgent("alice", "consumer")
        self.assertIsInstance(agent, AgentProtocol)

    def test_base_agent_receive_token_delegates_to_payment_provider(self):
        mock_provider = Mock()
        mock_provider.receive.return_value = True
        agent = BaseAgent("alice", "consumer", payment_provider=mock_provider)
        token = {"token_id": "t1", "amount_sat": 42, "redeemed": False}

        result = agent.receive_token(token)

        self.assertTrue(result)
        mock_provider.receive.assert_called_once_with(str(token), 42)

    def test_base_agent_send_token_delegates_to_payment_provider(self):
        mock_provider = Mock()
        mock_provider.send.return_value = True
        agent = BaseAgent("alice", "consumer", payment_provider=mock_provider)

        result = agent.send_token(21, "recipient-node")

        self.assertTrue(result)
        mock_provider.send.assert_called_once_with(21, "recipient-node")

    def test_base_agent_legacy_send_receive_without_provider(self):
        agent = BaseAgent("legacy", "consumer")
        outgoing = agent.send_token(10, "recipient")

        self.assertIsInstance(outgoing, dict)
        self.assertEqual(outgoing["amount_sat"], 10)
        self.assertEqual(agent.balance(), -10)

        incoming = {"token_id": "incoming-1", "amount_sat": 10, "redeemed": False}
        self.assertTrue(agent.receive_token(incoming))
        self.assertEqual(agent.balance(), 0)

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
