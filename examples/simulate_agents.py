from src.agents.service_agent import ServiceAgent

def run_simulation():
    # Step 1: Create two service agents
    cam_bot = ServiceAgent(
        name="CameraFeedBot",
        description="Provides 5-minute HD traffic feed",
        price_sat=5000
    )

    route_bot = ServiceAgent(
        name="RoutePlannerBot",
        description="Consumes traffic feed to optimize delivery route",
        price_sat=5000  # Route bot is a client in this case
    )

    # Step 2: CamBot advertises service
    ad = cam_bot.advertise_service()
    print("\n📢 Service Advertisement Event:")
    print(f"kind: {ad['kind']}")
    print(f"pubkey: {ad['pubkey']}")
    print(f"tags: {ad['tags']}")
    print(f"content: {ad['content']}")

    # Step 3: RoutePlannerBot "discovers" and pays with ecash
    print("\n🤝 RoutePlannerBot requests service and pays with ecash...")
    token = route_bot.offer_ecash_token()

    # Step 4: CamBot accepts token and delivers service
    success = cam_bot.accept_ecash_token(token)

    # Step 5: Show final balances
    print("\n📊 Wallet Balances After Transaction:")
    print(f"{cam_bot.name}: {cam_bot.get_balance()} sats")
    print(f"{route_bot.name}: {route_bot.get_balance()} sats")

if __name__ == "__main__":
    run_simulation()
