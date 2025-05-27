# BitAgent

A lightweight, modular framework for AI agents to transact autonomously using Bitcoin-based ecash (Fedimint), Nostr, and decentralized identity (DID).

## 🚀 Project Goal

Enable AI agents to:

- Offer and purchase digital services
- Pay using ecash tokens (Fedimint-compatible)
- Discover each other via Nostr
- Identify and verify each other with DIDs (future phase)

## ✅ Current Capabilities

- Mock Fedimint wallet for ecash token minting, sending, and receiving
- ServiceAgent and DataBot AI agents that simulate service-for-payment exchange
- Full simulation: Agent pays and receives data in exchange

## 📂 Project Structure

bitagent/
├── src/
│ ├── agents/ # Cambot, DataBot, etc.
│ ├── wallets/ # FedimintWallet
│ ├── protocols/ # Future: Nostr, DID, payment flows
│ ├── utils/ # Future: config, logging
├── examples/ # Simulations and usage demos
├── data/ # Example data payloads
├── README.md


## 📦 Run the Demo

1. Clone the repo:

```bash
git clone https://github.com/YOUR_USERNAME/bitagent.git
cd bitagent

    Run simulation:

python -m examples.data_transaction_simulation

You should see an AI agent pay another AI for data using ecash.
🛣 Roadmap

    ✅ Ecash payments between agents

    🧠 Nostr-based discovery

    🪪 DID-based identity

    ⚡ Lightning fallback support

    📜 Message signing and receipts

🤝 Contributing

This project is early but open. Issues, PRs, and discussion are welcome. Let's build open-source AI economic infrastructure together.
🧠 License

MIT — open and permissive
