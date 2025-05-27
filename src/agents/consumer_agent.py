import uuid

class ConsumerAgent:
    def __init__(self, name):
        self.name = name
        self.did = self.generate_mock_did()

    def generate_mock_did(self):
        # Mock DID
        return f"did:example:{uuid.uuid4()}"

    def discover_service(self, nostr_event):
        # Parse advertised Nostr event
        print(f"\n🔍 {self.name} discovered service:")
        for k, v in nostr_event.items():
            print(f"{k}: {v}")
        return nostr_event

    def pay_invoice(self, invoice):
        # Simulate invoice payment
        print(f"\n⚡ {self.name} is paying invoice {invoice['invoice']}")
        # In a real implementation, you'd use LNbits/Lightning SDKs
        print(f"✅ Payment simulated!")
