from lnbits_client import LNbitsClient
import os
from dotenv import load_dotenv

# ✅ Load the environment variables
load_dotenv()

# ✅ Get environment variables
api_key = os.getenv("LNBITS_API_KEY")
api_base = os.getenv("LNBITS_API_BASE", "https://demo.lnbits.com")

if not api_key:
    raise ValueError("❌ LNBITS_API_KEY not found in .env file")

# ✅ Initialize LNbits client
client = LNbitsClient(api_key, api_base)


def create_invoice(amount: int, memo: str = "BitAgent Invoice") -> dict:
    """Create an invoice with specified amount and memo."""
    invoice = client.create_invoice(amount, memo)
    print("📦 Raw invoice response:", invoice)
    if invoice:
        print("🧾 Invoice created:", invoice.get("bolt11"))
        return invoice
    else:
        print("❌ Failed to create invoice")
        return {}


def check_invoice_status(checking_id: str) -> bool:
    """Check if an invoice has been paid."""
    status = client.check_invoice(checking_id)
    print("✅ Paid" if status else "⏳ Pending")
    return status


def get_balance() -> int:
    """Get wallet balance in sats."""
    wallet = client.get_wallet_info()
    balance = wallet.get("balance", 0) if wallet else 0
    print("💰 Wallet balance:", balance)
    return balance


def get_wallet_id() -> str:
    """Return wallet ID."""
    wallet = client.get_wallet_info()
    wallet_id = wallet.get("id", "") if wallet else ""
    print("🆔 Wallet ID:", wallet_id)
    return wallet_id
