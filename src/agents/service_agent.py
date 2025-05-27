import uuid
from src.wallets.fedimint_wallet import FedimintWallet

class ServiceAgent:
    def __init__(self, name, description, price_sat):
        self.name = name
        self.description = description
        self.price_sat = price_sat
        self.did = self.generate_mock_did()
        self.nostr_pubkey = self.generate_mock_pubkey()
        self.wallet = FedimintWallet(wallet_id=self.name)

    def generate_mock_did(self):
        return f"did:example:{uuid.uuid4()}"

    def generate_mock_pubkey(self):
        return f"npub1{uuid.uuid4().hex[:20]}"

    def advertise_service(self):
        nostr_event = {
            "kind": 30078,
            "pubkey": self.nostr_pubkey,
            "tags": [
                ["t", "service:ai"],
                ["price", str(self.price_sat)],
            ],
            "content": {
                "service": self.description,
                "did": self.did,
                "price_sat": self.price_sat,
                "note": f"offered by {self.name}"
            }
        }
        return nostr_event

    def generate_invoice(self):
        invoice = {
            "invoice": f"lnbc{self.price_sat}..."
        }
        return invoice

    def offer_ecash_token(self):
        token = self.wallet.mint_tokens(self.price_sat)
        print(f"🔐 {self.name} issued ecash token: {token}")
        return token

    def accept_ecash_token(self, token):
        success = self.wallet.receive_tokens(token)
        if success:
            print(f"✅ {self.name} accepted ecash token from {token['sender']}")
        else:
            print(f"❌ {self.name} rejected token (already redeemed or invalid)")
        return success

    def get_balance(self):
        return self.wallet.get_balance()
