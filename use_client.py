from lnbits_client import LNbitsClient

api_key = input("Enter LNbits Admin API Key: ").strip()
client = LNbitsClient(api_key)

wallet = client.get_wallet_info()
print("Wallet Balance:", wallet["balance"])

invoice = client.create_invoice(amount_sats=1000, memo="Agent Test Invoice")
if invoice:
    print("⚡ Payment Request:", invoice["payment_request"])
    print("🔍 Checking ID:", invoice["checking_id"])
