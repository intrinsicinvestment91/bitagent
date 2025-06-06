from agent_wallet import get_wallet_id, get_balance, create_invoice, check_invoice_status

# Step 1: Test getting wallet ID and balance
print("🔎 Fetching wallet info...")
wallet_id = get_wallet_id()
balance = get_balance()

if wallet_id is not None:
    print("✅ Wallet Info:")
    print("  Wallet ID:", wallet_id)
    print("  Balance (sats):", balance)
else:
    print("❌ Could not retrieve wallet info.")

# Step 2: Test invoice creation
print("\n🧾 Creating test invoice for 1000 sats...")
invoice = create_invoice(1000, memo="Test from test_agent_wallet.py")
if invoice:
    print("✅ Invoice created:")
    print("  Payment Request (bolt11):", invoice.get("bolt11"))
    print("  Checking ID:", invoice.get("checking_id"))

    # Step 3: Check invoice status
    print("\n🔍 Checking status of created invoice...")
    paid = check_invoice_status(invoice.get("checking_id"))
    print("  Status:", "✅ PAID" if paid else "⏳ PENDING")
else:
    print("❌ Invoice creation failed.")
