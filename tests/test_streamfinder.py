# test_streamfinder.py

import requests
import time

A2A_ENDPOINT = "http://localhost:8000/a2a"
CONFIRM_ENDPOINT = "http://localhost:8000/confirm"

QUERY = "Oppenheimer"

def main():
    # Step 1: Send initial A2A request
    print(f"🔍 Sending streamfinder.search for: {QUERY}")
    a2a_response = requests.post(A2A_ENDPOINT, json={
        "method": "streamfinder.search",
        "params": {"query": QUERY}
    })

    if a2a_response.status_code != 200:
        print("❌ Failed to contact /a2a endpoint:", a2a_response.text)
        return

    a2a_data = a2a_response.json()
    print("🧾 Invoice response:", a2a_data)

    if "payment_required" not in a2a_data:
        print("❌ Unexpected response:", a2a_data)
        return

    payment_hash = a2a_data["payment_hash"]
    payment_request = a2a_data["payment_request"]

    print("\n⚡ Please pay this Lightning invoice to continue:")
    print(payment_request)

    # Step 2: Wait for user to pay the invoice manually
    input("\n➡️ Press Enter once payment has been made...")

    # Step 3: Confirm payment
    print("✅ Confirming payment...")
    confirm_response = requests.post(CONFIRM_ENDPOINT, json={
        "payment_hash": payment_hash,
        "query": QUERY
    })

    if confirm_response.status_code != 200:
        print("❌ Failed to contact /confirm endpoint:", confirm_response.text)
        return

    result = confirm_response.json()
    print("📺 Search result:\n", result)

if __name__ == "__main__":
    main()
