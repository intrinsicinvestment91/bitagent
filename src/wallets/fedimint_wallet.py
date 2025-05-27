import uuid
import json

class FedimintWallet:
    def __init__(self, wallet_id, federation_name="Test Federation"):
        self.wallet_id = wallet_id
        self.federation_name = federation_name
        self.balance = 0
        self.received_tokens = []

    def mint_tokens(self, sats: int):
        """Simulate minting ecash from BTC (mock only)."""
        token = {
            "token_id": str(uuid.uuid4()),
            "amount_sat": sats,
            "sender": self.wallet_id,
            "redeemed": False
        }
        self.balance += sats
        return token

    def receive_tokens(self, token):
        """Accept ecash token from another agent."""
        if not token["redeemed"]:
            self.received_tokens.append(token)
            self.balance += token["amount_sat"]
            token["redeemed"] = True
            return True
        else:
            return False

    def get_balance(self):
        return self.balance

    def export_wallet_state(self):
        return {
            "wallet_id": self.wallet_id,
            "balance": self.balance,
            "federation": self.federation_name,
            "tokens": self.received_tokens
        }
