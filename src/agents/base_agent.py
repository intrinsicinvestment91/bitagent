import uuid
from src.identity.did import DIDIdentity


class _SimWallet:
    """Minimal in-memory wallet for agent identity/simulation use only. Not for real payments."""
    def __init__(self):
        self._balance = 0
        self._tokens = []

    def get_balance(self) -> int:
        return self._balance

    def mint_token(self, amount_sat: int, recipient: str) -> dict:
        self._balance -= amount_sat
        return {"token_id": str(uuid.uuid4()), "amount_sat": amount_sat, "recipient": recipient, "redeemed": False}

    def redeem_token(self, token: dict) -> bool:
        if not token.get("redeemed"):
            token["redeemed"] = True
            self._balance += token["amount_sat"]
            self._tokens.append(token)
            return True
        return False


class BaseAgent:
    def __init__(self, name: str, role: str):
        self.name = name
        self.role = role
        self.did_identity = DIDIdentity()
        self.wallet = _SimWallet()

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
