import unittest
from src.wallets.fedimint_wallet import FedimintWallet

class TestFedimintWallet(unittest.TestCase):
    def test_initial_balance_is_zero(self):
        wallet = FedimintWallet(wallet_id="test-wallet", federation_name="TestFed")
        self.assertEqual(wallet.get_balance(), 0)

    def test_mint_tokens_increases_balance(self):
        wallet = FedimintWallet(wallet_id="test-wallet", federation_name="TestFed")
        token = {
            "token_id": "123abc",
            "amount_sat": 2000,
            "sender": "TestAgent",
            "redeemed": False
        }
        result = wallet.receive_tokens(token)
        self.assertTrue(result)
        self.assertEqual(wallet.get_balance(), 2000)
        self.assertTrue(token["redeemed"])

    def test_redeeming_same_token_twice_fails(self):
        wallet = FedimintWallet(wallet_id="test-wallet", federation_name="TestFed")
        token = {
            "token_id": "abc123",
            "amount_sat": 3000,
            "sender": "AnotherBot",
            "redeemed": False
        }
        wallet.receive_tokens(token)
        result = wallet.receive_tokens(token)
        self.assertFalse(result)
        self.assertEqual(wallet.get_balance(), 3000)  # Still only once

if __name__ == "__main__":
    unittest.main()
