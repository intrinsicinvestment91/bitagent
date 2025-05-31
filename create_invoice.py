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

data = {
    "out": False,
    "amount": 100,  # Amount in sats
    "memo": "Test invoice from BitAgent"
}

response = requests.post(f"{LNBITS_ENDPOINT}/api/v1/payments", headers=headers, json=data)

if response.status_code == 201:
    invoice = response.json()
    print("✅ Invoice Created:")
    print("⚡ BOLT11 Invoice:", invoice["bolt11"])
    print("🔑 Payment Hash:", invoice["payment_hash"])
else:
    print(f"❌ Error {response.status_code}: {response.text}")
