# BitAgent

A lightweight, modular framework for AI agents to transact autonomously using Bitcoin-based ecash (Fedimint), the Lightning Network (via LNbits), Nostr, and decentralized identity (DID).

---

## 🚀 Project Goal

Enable AI agents to:

- Offer and purchase digital services
- Pay using ecash tokens (Fedimint-compatible)
- Pay using Lightning Network via LNbits ⚡
- Discover each other via Nostr
- Identify and verify each other with DIDs (future phase)
- Coordinate tasks in multi-agent workflows (MCPS-style orchestration)

---

## ✅ Current Capabilities

- 🔁 Ecash and Lightning payments between agents (Fedimint + LNbits)
- 🤖 Modular service agents:
  - `PolyglotAgent`: Translate and transcribe with LNbits paywall
  - `CoordinatorAgent`: Chain other agents to fulfill complex tasks
  - `CameraBot`, `DataBot`: Simulated service-for-payment AI agents
- 🧠 MCPS-style orchestration: Agents calling agents, payments included
- 📡 Self-contained LNbits payment validation
- 🧪 Full simulation and testable services

---

## 📂 Project Structure

bitagent/
├── src/
│ ├── agents/
│ │ ├── polyglot_agent/ # Translation and transcription service
│ │ ├── coordinator_agent/ # MCPS coordinator for chaining agents
│ │ ├── service_agent/ # Generic service agent logic
│ │ ├── databot/ # Example service bot
│ ├── wallets/ # FedimintWallet, LNbitsWallet
│ ├── protocols/ # Nostr, DID (planned)
│ ├── utils/ # Logging, config (planned)
├── examples/ # Usage demos
├── data/ # Example payloads


---

## 🧪 How to Run Agents

### 1. Install dependencies:

```bash
pip install -r requirements.txt

Make sure to also install:

pip install deep-translator openai-whisper aiohttp

2. Configure your .env with LNbits credentials:

LNBITS_API_KEY=your_admin_key_here
LNBITS_WALLET_ID=your_wallet_id_here
LNBITS_BASE_URL=https://legend.lnbits.com  # or your self-hosted URL

3. Run PolyglotAgent (port 8000):

python src/agents/polyglot_agent/run.py

4. Run CoordinatorAgent (port 8001):

python src/agents/coordinator_agent/run.py

🔁 Agent Workflow Example

Use CoordinatorAgent to:

    Accept an audio file

    Transcribe via PolyglotAgent

    Translate the transcription

    Return final output in JSON

Endpoint: POST /translate_audio (form-data with audio=yourfile.wav)
🛣 Roadmap

    ✅ Ecash payments between agents

    ✅ Lightning Network (LNbits) agent payments

    🧠 Nostr-based discovery

    🪪 DID-based identity

    📜 Message signing and receipts

    🤖 CoordinatorAgent multi-agent task pipelines

    🧩 Plugin ecosystem for service agents

🤝 Contributing

## 🧠 Streamfinder Agent (A2A Compliant)

Streamfinder is a modular agent that accepts Lightning payments and returns movie/TV streaming platform info via JSON-RPC.

**Features:**
- JSON-RPC over `/a2a`
- Invoice generation + payment check via LNbits
- Movie/TV search logic
- `/confirm` endpoint to trigger result after payment

**Note:** Other agents in this repo are not yet A2A-compatible and will need to be updated to support this modular JSON-RPC pattern.


This project is early but open. Issues, PRs, and discussion are welcome. Let's build open-source AI economic infrastructure together.
🧠 License

MIT — open and permissive
(You may run and monetize your own agents, but please consider contributing improvements upstream.)


---

## ✅ Next Step: Apply the Update

You can replace your current `README.md` with the content above, then run:

```bash
git add README.md
git commit -m "Update README with PolyglotAgent and CoordinatorAgent info"
git push origin main
