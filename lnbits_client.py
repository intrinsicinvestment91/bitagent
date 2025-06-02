import requests

class LNbitsClient:
    def __init__(self, api_key, api_base="https://demo.lnbits.com"):
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
            return None
