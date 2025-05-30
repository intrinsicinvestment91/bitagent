import uuid

class FedimintWallet:
    def __init__(self, wallet_id=None, federation_name="DefaultFed", owner=""):
        self.wallet_id = wallet_id or str(uuid.uuid4())
        self.federation_name = federation_name
        self.owner = owner
        self.balance = 0
        self.received_tokens = []

    def mint_token(self, amount_sat: int, recipient: str = "unknown") -> dict:
        token = {
            "token_id": str(uuid.uuid4()),
            "amount_sat": amount_sat,
            "sender": self.owner,
            "recipient": recipient,
            "redeemed": False
        }
        self.balance -= amount_sat
        return token

    def accept_token(self, token: dict, required_amount: int) -> bool:
        if token["amount_sat"] >= required_amount and not token.get("redeemed", False):
            token["redeemed"] = True
            self.balance += token["amount_sat"]
            self.received_tokens.append(token)
            return True
        return False

    def redeem_token(self, token: dict) -> bool:
        """
        Accept ecash token from another agent.
        """
        if not token.get("redeemed", False):
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

    def __repr__(self):
        return f"<FedimintWallet owner={self.owner} balance_sat={self.balance}>"
