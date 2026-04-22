from lnbits_client import LNbitsClient

from lnbits_client import LNbitsClient
from config import API_KEY, API_BASE

client = LNbitsClient(api_key, api_base)

wallet_info = client.get_wallet_info()
if wallet_info:
    print("Wallet Name:", wallet_info.get("name"))
    print("Balance (sats):", wallet_info.get("balance"))
    print("Wallet ID:", wallet_info.get("id"))
else:
    print("❌ Failed to fetch wallet info.")
