from lnbits_client import LNbitsClient
from dotenv import load_dotenv
import os

load_dotenv()


class AgentWallet:
    def __init__(self):
        api_key = os.getenv("LNBITS_API_KEY")
        api_base = os.getenv("LNBITS_URL")
        if not api_key:
            raise ValueError("LNBITS_API_KEY not set")
        if not api_base:
            raise ValueError("LNBITS_URL not set")
        self.client = LNbitsClient(api_key, api_base)

    def create_invoice(self, amount: int, memo: str = "BitAgent Invoice") -> dict:
        invoice = self.client.create_invoice(amount, memo)
        print("📦 Raw invoice response:", invoice)
        if invoice:
            print("🧾 Invoice created:", invoice.get("bolt11"))
            return invoice
        else:
            print("❌ Failed to create invoice")
            return {}

    def check_invoice(self, checking_id: str) -> bool:
        status = self.client.check_invoice(checking_id)
        print("✅ Paid" if status else "⏳ Pending")
        return status

    def get_balance(self) -> int:
        wallet = self.client.get_wallet_info()
        balance = wallet.get("balance", 0) if wallet else 0
        print("💰 Wallet balance:", balance)
        return balance

    def get_wallet_id(self) -> str:
        wallet = self.client.get_wallet_info()
        wallet_id = wallet.get("id", "") if wallet else ""
        print("🆔 Wallet ID:", wallet_id)
        return wallet_id
