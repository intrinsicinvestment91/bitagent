import uuid
from typing import TYPE_CHECKING, Protocol, runtime_checkable
from src.identity.did import DIDIdentity

if TYPE_CHECKING:
    from src.core.payment import PaymentProvider


@runtime_checkable
class AgentProtocol(Protocol):
    def identify(self) -> dict: ...
    def get_info(self) -> dict: ...
    def list_services(self) -> list: ...
    def get_agent_id(self) -> str: ...
    def get_did(self) -> str: ...


def validate_agent_info(info: dict) -> bool:
    required_keys = {"id", "name", "role", "did", "description", "services"}
    if not isinstance(info, dict):
        return False
    if not required_keys.issubset(info.keys()):
        return False
    if not isinstance(info.get("id"), str) or not info["id"].strip():
        return False
    if not isinstance(info.get("name"), str) or not info["name"].strip():
        return False
    if not isinstance(info.get("role"), str) or not info["role"].strip():
        return False
    if not isinstance(info.get("did"), str) or not info["did"].strip():
        return False
    if not isinstance(info.get("description"), str):
        return False
    if not isinstance(info.get("services"), list):
        return False
    return True


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

    def accept_token(self, token: dict, required_amount: int) -> bool:
        amount_sat = token.get("amount_sat", 0)
        if amount_sat < required_amount:
            return False
        return self.redeem_token(token)


class BaseAgent(AgentProtocol):
    def __init__(
        self,
        name: str,
        role: str,
        description: str | None = None,
        services: list[str] | None = None,
        payment_provider: "PaymentProvider | None" = None,
    ):
        self.name = name
        self.role = role
        self.description = description or ""
        self.services = list(services) if services is not None else []
        self.payment_provider = payment_provider
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

    def get_info(self) -> dict:
        return {
            "id": self.get_agent_id(),
            "agent_id": self.get_agent_id(),
            "name": self.name,
            "role": self.role,
            "did": self.get_did(),
            "description": self.description,
            "services": self.list_services(),
        }

    def list_services(self) -> list[str]:
        return list(self.services)

    def get_agent_id(self) -> str:
        return self.id

    def get_did(self) -> str:
        return self.id

    def balance(self) -> int:
        return self.wallet.get_balance()

    def receive_token(self, token: dict) -> bool:
        if self.payment_provider is not None:
            return self.payment_provider.receive(str(token), int(token.get("amount_sat", 0)))
        return self.wallet.redeem_token(token)

    def send_token(self, amount_sat: int, recipient: str) -> dict | bool:
        if self.payment_provider is not None:
            return self.payment_provider.send(amount_sat, recipient)
        return self.wallet.mint_token(amount_sat, recipient)
