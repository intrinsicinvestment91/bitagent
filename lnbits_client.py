import requests

class LNbitsClient:
    def __init__(self, api_key, api_base="https://legend.lnbits.com"):
        self.api_key = api_key
        self.api_base = api_base.rstrip("/")
        self.headers = {
            "X-Api-Key": self.api_key,
            "Content-type": "application/json"
        }

    def get_wallet_info(self):
        url = f"{self.api_base}/api/v1/wallet"
        response = requests.get(url, headers=self.headers)
        if response.ok:
            return response.json()
        else:
            print("❌ Failed to fetch wallet info.")
            print("Response:", response.text)
            return None

    def create_invoice(self, amount: int, memo: str = ""):
        url = f"{self.api_base}/api/v1/payments"
        payload = {
            "out": False,
            "amount": amount,
            "memo": memo
        }
        response = requests.post(url, json=payload, headers=self.headers)
        if response.ok:
            invoice = response.json()
            print("🧾 Invoice created:", invoice.get("bolt11"))
            return invoice
        else:
            print("❌ Failed to create invoice.")
            print("Response:", response.text)
            return None

    def check_invoice(self, checking_id: str) -> bool:
        url = f"{self.api_base}/api/v1/payments/{checking_id}"
        response = requests.get(url, headers=self.headers)
        if response.ok:
            data = response.json()
            return data.get("paid", False)
        else:
            print("❌ Failed to check invoice status.")
            print("Response:", response.text)
            return False
