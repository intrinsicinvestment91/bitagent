import time
from lnbits_client import LNbitsClient

# Step 1: Initialize LNbits client
API_KEY = "de3ebbe2caf64e4b95a7a6bdf4d8f6c2"
BASE_URL = "https://demo.lnbits.com"
client = LNbitsClient(API_KEY, BASE_URL)

# Step 2: Get wallet info
print("🔎 Fetching wallet info...")
wallet_info = client.get_wallet_info()

if wallet_info:
    print("✅ Wallet Info:")
    print("  🆔 ID:", wallet_info.get("id"))
    print("  💰 Balance (sats):", wallet_info.get("balance"))
else:
    print("❌ Failed to get wallet info.")
    exit(1)

# Step 3: Create test invoice
print("\n🧾 Creating invoice for 10 sats...")
invoice = client.create_invoice(10, memo="Test from test_agent_wallet.py")

if invoice:
    # Try both common keys just in case
    bolt11 = invoice.get("payment_request") or invoice.get("bolt11")
    checking_id = invoice.get("checking_id")

    print("✅ Invoice created:")
    print("  ⚡ bolt11:", bolt11)
    print("  🔍 Checking ID:", checking_id)
else:
    print("❌ Invoice creation failed.")
    exit(1)

# Step 4: Poll for payment status
def wait_for_payment(checking_id):
    print(f"\n🔄 Waiting for payment...")
    while True:
        paid = client.check_invoice(checking_id)
        if paid:
            print("✅ Invoice has been PAID!")
            break
        else:
            print("⏳ Still pending... checking again in 10 seconds.")
            time.sleep(10)

wait_for_payment(checking_id)
