from src.wallets.fedimint_wallet import FedimintWallet
from src.identity.did import DIDIdentity

class BaseAgent:
    def __init__(self, name: str, role: str):
        self.name = name
        self.role = role
        self.did_identity = DIDIdentity()
        self.wallet = FedimintWallet(owner=self.name)

    @property
    def id(self) -> str:
        return self.did_identity.did

    def identify(self) -> dict:
        return {
            "name": self.name,
            "role": self.role,
            "did": self.id
        }

    def balance(self) -> int:
        return self.wallet.get_balance()

    def receive_token(self, token: dict) -> bool:
        return self.wallet.redeem_token(token)

    def send_token(self, amount_sat: int, recipient: str) -> dict:
        return self.wallet.mint_token(amount_sat, recipient)
