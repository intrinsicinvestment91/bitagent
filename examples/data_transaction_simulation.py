from src.agents.databot import DataBot
from src.agents.service_agent import ServiceAgent

def run_simulation():
    # Create buyer and seller agents
    databot = DataBot()
    cambot = ServiceAgent(
        name="CameraFeedBot",
        description="Buys traffic data for AI routing",
        price_sat=5000
    )

    # Cambot mints token to pay
    print("\n🤖 Cambot preparing payment...")
    token = cambot.wallet.mint_tokens(5000)

    # Cambot sends token to Databot and requests data
    print("\n🛰 Sending token to Databot and requesting data...")
    data = databot.serve_data(token)

    # Cambot receives data
    if data:
        print("\n📥 Cambot received data:")
        print(data)

    # Show balances
    print("\n📊 Final Balances:")
    print(f"{cambot.name}: {cambot.get_balance()} sats")
    print(f"{databot.name}: {databot.get_balance()} sats")

if __name__ == "__main__":
    run_simulation()
