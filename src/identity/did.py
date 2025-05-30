import uuid

class DIDIdentity:
    def __init__(self, method: str = "example"):
        self.method = method
        self.did = self.generate_did()

    def generate_did(self) -> str:
        unique_id = str(uuid.uuid4())
        return f"did:{self.method}:{unique_id}"

    def __repr__(self):
        return f"<DIDIdentity {self.did}>"
