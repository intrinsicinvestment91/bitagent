from src.agents.camera_feed_bot import CameraFeedBot

def run_simulation():
    # Step 1: Create CameraFeedBot
    cam_bot = CameraFeedBot()

    print("\n🆔 Agent Identity:")
    print(cam_bot.identify())

    # Step 2: CameraFeedBot advertises service
    ad = cam_bot.advertise_service()
    print("\n📢 Service Advertisement Event:")
    print(f"kind: {ad['kind']}")
    print(f"pubkey: {ad['pubkey']}")
    print(f"tags: {ad['tags']}")
    print(f"content: {ad['content']}")

    # Step 3: Simulated client requests service and pays
    print("\n🤝 RoutePlannerBot requests service and pays with ecash...")
    token = cam_bot.send_token(amount_sat=5000, recipient="RoutePlannerBot")
    print(f"🔐 RoutePlannerBot issued ecash token: {token}")

    # Step 4: Cambot accepts token
    accepted = cam_bot.receive_token(token)
    if accepted:
        print("✅ CameraFeedBot accepted ecash token from RoutePlannerBot")
    else:
        print("❌ CameraFeedBot rejected token")

    # Step 5: Show final balances
    print("\n📊 Wallet Balances After Transaction:")
    print(f"{cam_bot.name}: {cam_bot.balance()} sats")

if __name__ == "__main__":
    run_simulation()
