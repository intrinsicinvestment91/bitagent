import os
import requests
from dotenv import load_dotenv

load_dotenv()

LNBITS_ADMIN_KEY = os.getenv("LNBITS_ADMIN_KEY")
LNBITS_ENDPOINT = os.getenv("LNBITS_ENDPOINT")

headers = {
    "X-Api-Key": LNBITS_ADMIN_KEY,
    "Content-type": "application/json"
}

# Test: get wallet details
response = requests.get(f"{LNBITS_ENDPOINT}/api/v1/wallet", headers=headers)

if response.status_code == 200:
    wallet = response.json()
    print("Wallet Info:")
    print(wallet)
else:
    print(f"Error {response.status_code}: {response.text}")
