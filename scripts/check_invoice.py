import os
import requests
from dotenv import load_dotenv

load_dotenv()

LNBIT_API_KEY = os.getenv("LNBITS_API_KEY")
LNBIT_API_BASE = os.getenv("LNBITS_API_BASE")

# Replace with your checking_id or pass via CLI
checking_id = input("Enter invoice checking_id: ").strip()

url = f"{LNBIT_API_BASE}/api/v1/payments/{checking_id}"
headers = {"X-Api-Key": LNBIT_API_KEY}

response = requests.get(url, headers=headers)

print("Raw Response:", response.status_code, response.text)

if response.ok:
    data = response.json()
    paid = data.get("paid", False)
    print("Invoice Status:", "✅ PAID" if paid else "⏳ PENDING")
else:
    print("Failed to check invoice status.")
