# ai-bitcoin-payments
Enable AI agents to discover each other, verify identity via DIDs, and pay for services using the Bitcoin Lightning Network and Nostr.
AI Bitcoin Payments

This open-source project enables autonomous AI agents to discover each other, verify identities using DIDs, and pay for services using the Bitcoin Lightning Network — all without running full Bitcoin nodes.
Technologies Used

    Bitcoin Lightning Network (via LNbits)

    DIDs (Decentralized Identifiers)

    Nostr (decentralized communication and discovery)

    Python

Project Structure

src/
├── agents/       # AI agent logic (e.g., CamBot, LogiBot)
├── identity/     # DID creation and trust handling
├── network/      # LNbits and Nostr interfaces
examples/         # Simulations and test runs
docs/             # Architecture briefs, flow diagrams, specs

Getting Started

    Clone the repository:

git clone https://github.com/YOUR_USERNAME/ai-bitcoin-payments.git
cd ai-bitcoin-payments

    Install dependencies:

pip install -r requirements.txt

    Run the sample simulation:

python examples/simulate_agents.py

License

MIT License
