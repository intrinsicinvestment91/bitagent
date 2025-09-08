# broadcast_agents.py

import time
import json
import asyncio
from nostr.event import Event, EventKind
from nostr.key import PrivateKey
from nostr.relay_manager import RelayManager
from nostr.message_type import ClientMessageType
from nostr.filter import Filter, Filters

# === Replace this with your persistent private key ===
# Generate one at: https://damus.io/key/
PRIVATE_KEY_HEX = "REPLACE_ME_WITH_YOUR_PRIVATE_KEY"

# List of agents and their info
AGENTS = [
    {
        "name": "PolyglotAgent",
        "description": "Translate and transcribe audio using LNbits",
        "endpoint": "http://localhost:8000/polyglot",
        "services": ["translate", "transcribe"]
    },
    {
        "name": "CoordinatorAgent", 
        "description": "Chains tasks between agents (e.g. translate_audio pipeline)",
        "endpoint": "http://localhost:8000/coordinator",
        "services": ["translate_audio", "chain_tasks"]
    },
    {
        "name": "StreamfinderAgent",
        "description": "Find streaming platforms for movies and TV shows",
        "endpoint": "http://localhost:8000",
        "services": ["streamfinder.search"]
    }
]

# Recommended: create your own relay list
RELAYS = [
    "wss://relay.damus.io",
    "wss://relay.snort.social",
    "wss://nos.lol",
    "wss://nostr.wine"
]


async def broadcast_agent(agent_info, privkey_hex):
    privkey = PrivateKey(bytes.fromhex(privkey_hex))
    pubkey = privkey.public_key.hex()

    content = {
        "agent_name": agent_info["name"],
        "description": agent_info["description"],
        "endpoint": agent_info["endpoint"],
        "services": agent_info["services"],
        "pubkey": pubkey,
        "timestamp": int(time.time())
    }

    event = Event(
        pubkey=pubkey,
        kind=30078,  # Custom agent announcement kind
        content=json.dumps(content)
    )
    privkey.sign_event(event)

    relay_mgr = RelayManager()
    for url in RELAYS:
        relay_mgr.add_relay(url)

    relay_mgr.open_connections({"cert_reqs": 0})  # No SSL verification
    time.sleep(1.25)  # Let relays connect

    msg = json.dumps([ClientMessageType.EVENT, event.to_dict()])
    for relay in relay_mgr.relays.values():
        relay.send_message(msg)

    print(f"✅ Broadcasted {agent_info['name']} to {len(RELAYS)} relays")
    time.sleep(2)
    relay_mgr.close_connections()


async def main():
    for agent in AGENTS:
        await broadcast_agent(agent, PRIVATE_KEY_HEX)


if __name__ == "__main__":
    asyncio.run(main())
