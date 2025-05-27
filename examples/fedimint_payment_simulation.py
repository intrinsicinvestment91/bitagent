from src.wallets.fedimint_wallet import FedimintWallet

def run_simulation():
    # Create two wallets: sender and receiver
    alice = FedimintWallet(wallet_id="AliceBot")
    bob = FedimintWallet(wallet_id="BobBot")

    print("\n💰 Alice mints 3000 sats worth of ecash...")
    token = alice.mint_tokens(3000)
    print(f"Token minted: {token}")

    print("\n📤 Alice sends token to Bob...")
    success = bob.receive_tokens(token)
    if success:
        print("✅ Bob received and redeemed the token.")
    else:
        print("❌ Token was invalid or already redeemed.")

    print("\n📊 Final balances:")
    print(f"Alice: {alice.get_balance()} sats")
    print(f"Bob:   {bob.get_balance()} sats")

if __name__ == "__main__":
    run_simulation()
