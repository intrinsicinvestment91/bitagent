import uuid
from src.wallets.fedimint_wallet import FedimintWallet

class BaseAgent:
    def __init__(self, name, role):
        self.name = name
        self.role = role
        self.id = f"did:example:{uuid.uuid4()}"
        self.wallet = FedimintWallet(owner=self.name)

    def identify(self):
        return {
            "name": self.name,
            "role": self.role,
            "did": self.id,
        }

    def balance(self):
        return self.wallet.get_balance()

    def receive_token(self, token: dict):
        return self.wallet.redeem_token(token)

    def send_token(self, amount_sat: int, recipient: str):
        return self.wallet.mint_token(amount_sat, recipient)
