"""
Enhanced peer-to-peer discovery system using DHT, Nostr, and custom protocols.
Implements distributed agent discovery with security and reliability.
"""

from __future__ import annotations

import asyncio
import json
import time
import hashlib
import random
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import aiohttp
import logging

logger = logging.getLogger(__name__)

# Nostr imports (optional dependency).
# RelayManager is intentionally excluded: python-nostr's relay.py uses a
# mutable dataclass default (RelayPolicy) that is rejected by Python 3.13+.
# We replace relay connectivity with a minimal aiohttp WebSocket publisher.
NOSTR_AVAILABLE = False
NOSTR_IMPORT_ERROR = None
try:
    from nostr.event import Event, EventKind
    from nostr.key import PrivateKey, PublicKey
    from nostr.filter import Filter, Filters
    from nostr.message_type import ClientMessageType
    NOSTR_AVAILABLE = True
except Exception as e:
    NOSTR_IMPORT_ERROR = e
    logger.warning("Nostr support unavailable; continuing with DHT-only discovery: %s", e)


async def _ws_publish(url: str, msg: str) -> None:
    """Send one NIP-01 message to a single relay WebSocket, best-effort."""
    timeout = aiohttp.ClientTimeout(connect=5, total=8)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.ws_connect(url, ssl=False, heartbeat=None) as ws:
            await ws.send_str(msg)
            await asyncio.sleep(0.3)  # brief wait for relay ACK


async def _ws_query(url: str, req_msg: str, sub_id: str, per_relay_timeout: float = 5.0) -> List[dict]:
    """
    Query a single Nostr relay and collect EVENT messages until EOSE or timeout.

    Sends a NIP-01 REQ, accumulates EVENT payloads, stops on EOSE or timeout,
    then sends CLOSE. Returns a list of raw event dicts. Best-effort: any
    connection or protocol error returns an empty list.
    """
    events: List[dict] = []
    connect_timeout = aiohttp.ClientTimeout(connect=5, total=per_relay_timeout + 5)
    try:
        async with aiohttp.ClientSession(timeout=connect_timeout) as session:
            async with session.ws_connect(url, ssl=False, heartbeat=None) as ws:
                await ws.send_str(req_msg)
                deadline = asyncio.get_event_loop().time() + per_relay_timeout
                while True:
                    remaining = deadline - asyncio.get_event_loop().time()
                    if remaining <= 0:
                        break
                    try:
                        raw = await asyncio.wait_for(ws.receive_str(), timeout=remaining)
                    except asyncio.TimeoutError:
                        break
                    try:
                        msg = json.loads(raw)
                    except json.JSONDecodeError:
                        logger.debug("Nostr query: malformed message from %s: %.120s", url, raw)
                        continue
                    if not isinstance(msg, list) or len(msg) < 2:
                        continue
                    msg_type = msg[0]
                    if msg_type == "EVENT" and len(msg) == 3 and msg[1] == sub_id:
                        event_data = msg[2]
                        if isinstance(event_data, dict):
                            events.append(event_data)
                    elif msg_type == "EOSE" and msg[1] == sub_id:
                        break
                    elif msg_type in ("NOTICE", "OK", "AUTH"):
                        logger.debug("Nostr query: relay notice from %s: %s", url, msg)
                close_msg = json.dumps(["CLOSE", sub_id])
                try:
                    await ws.send_str(close_msg)
                except Exception:
                    pass
    except Exception as e:
        logger.debug("Nostr query: relay %s unavailable: %s", url, e)
    return events

class DiscoveryProtocol(Enum):
    NOSTR = "nostr"
    DHT = "dht"
    MULTICAST = "multicast"
    DNS = "dns"

@dataclass
class AgentInfo:
    """Information about a discovered agent."""
    agent_id: str
    name: str
    description: str
    endpoint: str
    services: List[str]
    public_key: str
    protocol: str
    last_seen: float
    reputation_score: float = 0.0
    capabilities: Dict[str, any] = None
    
    def __post_init__(self):
        if self.capabilities is None:
            self.capabilities = {}

@dataclass
class DiscoveryQuery:
    """Query for agent discovery."""
    service_type: Optional[str] = None
    agent_id: Optional[str] = None
    capabilities: Optional[Dict[str, any]] = None
    max_results: int = 10
    timeout: float = 30.0

class DHTNode:
    """Distributed Hash Table node for agent discovery."""
    
    def __init__(self, node_id: str = None):
        self.node_id = node_id or self._generate_node_id()
        self.routing_table = {}
        self.agent_registry = {}
        self.peers = set()
        
    def _generate_node_id(self) -> str:
        """Generate a random node ID."""
        return hashlib.sha256(str(random.random()).encode()).hexdigest()[:16]
    
    async def store_agent_info(self, agent_info: AgentInfo, ttl: int = 3600):
        """Store agent information in DHT."""
        key = self._get_key(agent_info.agent_id)
        self.agent_registry[key] = {
            "data": asdict(agent_info),
            "timestamp": time.time(),
            "ttl": ttl
        }
        
        # Replicate to peers
        await self._replicate_to_peers(key, self.agent_registry[key])
    
    async def find_agents(self, query: DiscoveryQuery) -> List[AgentInfo]:
        """Find agents matching the query."""
        results = []
        
        for key, entry in self.agent_registry.items():
            if time.time() - entry["timestamp"] > entry["ttl"]:
                continue  # Expired entry
                
            agent_data = entry["data"]
            agent_info = AgentInfo(**agent_data)
            
            if self._matches_query(agent_info, query):
                results.append(agent_info)
                
            if len(results) >= query.max_results:
                break
        
        # Query peers if not enough results
        if len(results) < query.max_results:
            peer_results = await self._query_peers(query)
            results.extend(peer_results)
        
        return results[:query.max_results]
    
    def _get_key(self, agent_id: str) -> str:
        """Get DHT key for agent ID."""
        return hashlib.sha256(agent_id.encode()).hexdigest()
    
    def _matches_query(self, agent_info: AgentInfo, query: DiscoveryQuery) -> bool:
        """Check if agent matches query criteria."""
        if query.agent_id and agent_info.agent_id != query.agent_id:
            return False
        
        if query.service_type and query.service_type not in agent_info.services:
            return False
        
        if query.capabilities:
            for cap_key, cap_value in query.capabilities.items():
                if agent_info.capabilities.get(cap_key) != cap_value:
                    return False
        
        return True
    
    async def _replicate_to_peers(self, key: str, data: dict):
        """Replicate data to peer nodes."""
        for peer in self.peers:
            try:
                async with aiohttp.ClientSession() as session:
                    await session.post(
                        f"{peer}/dht/store",
                        json={"key": key, "data": data},
                        timeout=aiohttp.ClientTimeout(total=5)
                    )
            except Exception as e:
                logging.warning(f"Failed to replicate to peer {peer}: {e}")
    
    async def _query_peers(self, query: DiscoveryQuery) -> List[AgentInfo]:
        """Query peer nodes for agents."""
        results = []
        
        for peer in self.peers:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"{peer}/dht/query",
                        json=asdict(query),
                        timeout=aiohttp.ClientTimeout(total=query.timeout)
                    ) as response:
                        if response.status == 200:
                            data = await response.json()
                            for agent_data in data.get("agents", []):
                                results.append(AgentInfo(**agent_data))
            except Exception as e:
                logging.warning(f"Failed to query peer {peer}: {e}")
        
        return results

class EnhancedNostrDiscovery:
    """Enhanced Nostr-based agent discovery with filtering and reputation."""
    
    def __init__(self, private_key: str = None):
        if not NOSTR_AVAILABLE:
            raise RuntimeError(f"Nostr dependencies unavailable: {NOSTR_IMPORT_ERROR}")

        if private_key:
            try:
                self.private_key = PrivateKey(bytes.fromhex(private_key.strip()))
                logger.info(
                    "Nostr: persistent identity loaded (pubkey %s...)",
                    self.private_key.public_key.hex()[:16],
                )
            except Exception as e:
                logger.warning(
                    "Nostr: NOSTR_PRIVATE_KEY is invalid (%s) — falling back to ephemeral identity",
                    e,
                )
                self.private_key = PrivateKey()
                logger.info(
                    "Nostr: ephemeral identity active (pubkey %s...)",
                    self.private_key.public_key.hex()[:16],
                )
        else:
            self.private_key = PrivateKey()
            logger.info(
                "Nostr: NOSTR_PRIVATE_KEY not set — ephemeral identity active (pubkey %s...)",
                self.private_key.public_key.hex()[:16],
            )

        self.public_key = self.private_key.public_key
        self.agent_cache = {}
        self.reputation_scores = {}
        self.relays = [
            "wss://relay.damus.io",
            "wss://relay.snort.social",
            "wss://nos.lol",
            "wss://nostr.wine",
            "wss://relay.nostr.band",
        ]
    
    async def broadcast_agent(self, agent_info: AgentInfo):
        """Broadcast agent information via Nostr."""
        content = {
            "agent_id": agent_info.agent_id,
            "name": agent_info.name,
            "description": agent_info.description,
            "endpoint": agent_info.endpoint,
            "services": agent_info.services,
            "public_key": agent_info.public_key,
            "protocol": agent_info.protocol,
            "capabilities": agent_info.capabilities,
            "timestamp": time.time()
        }
        
        event = Event(
            public_key=self.public_key.hex(),
            kind=30078,
            content=json.dumps(content),
            tags=[
                ["t", "bitagent"],
                ["t", "agent-discovery"],
                ["service", *agent_info.services],
                ["endpoint", agent_info.endpoint],
            ],
        )

        self.private_key.sign_event(event)
        await self._publish_event(event)
        logger.info("Broadcasted agent %s via Nostr", agent_info.name)
    
    async def discover_agents(self, query: DiscoveryQuery) -> List[AgentInfo]:
        """Discover agents using Nostr."""
        filters = Filters([
            Filter(
                kinds=[30078],
                tags={"t": ["bitagent", "agent-discovery"]},
                since=int(time.time() - 3600)  # Last hour
            )
        ])
        
        # Add service filter if specified
        if query.service_type:
            filters.filters[0].tags["service"] = [query.service_type]
        
        events = await self._query_events(filters)
        agents = []
        
        for event in events:
            try:
                content = json.loads(event.content)
                agent_info = AgentInfo(
                    agent_id=content["agent_id"],
                    name=content["name"],
                    description=content["description"],
                    endpoint=content["endpoint"],
                    services=content["services"],
                    public_key=content["public_key"],
                    protocol=content["protocol"],
                    last_seen=content["timestamp"],
                    capabilities=content.get("capabilities", {})
                )
                
                # Apply reputation filtering
                if self._check_reputation(agent_info, query):
                    agents.append(agent_info)
                    
            except Exception as e:
                logging.warning(f"Failed to parse agent event: {e}")
        
        return agents[:query.max_results]
    
    def _check_reputation(self, agent_info: AgentInfo, query: DiscoveryQuery) -> bool:
        """Check if agent meets reputation requirements."""
        reputation = self.reputation_scores.get(agent_info.agent_id, 0.0)
        return reputation >= 0.0  # Basic filtering - can be enhanced
    
    async def _publish_event(self, event: Event) -> None:
        """Publish a signed Nostr event to all configured relays concurrently."""
        msg = event.to_message()  # already a complete NIP-01 '["EVENT", {...}]' JSON string
        tasks = [_ws_publish(url, msg) for url in self.relays]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        failed = sum(1 for r in results if isinstance(r, Exception))
        if failed:
            logger.debug("Nostr: %d/%d relay(s) did not acknowledge event", failed, len(self.relays))

    async def _query_events(self, filters) -> List[Event]:
        """
        Query all configured relays for events matching `filters`.

        Sends a NIP-01 REQ to each relay concurrently, collects EVENT messages
        until EOSE or a per-relay timeout, then reconstructs Event objects from
        the raw dicts. Relay failures are best-effort and logged at debug level.
        """
        sub_id = hashlib.sha256(str(time.time()).encode()).hexdigest()[:12]

        # Build the REQ filter payload from the Filters object.
        # Filters is a UserList; to_json_array() returns a list of filter dicts.
        try:
            filter_dicts = filters.to_json_array()
        except Exception as e:
            logger.warning("Nostr: could not serialise filters (%s); aborting query", e)
            return []

        req_msg = json.dumps(["REQ", sub_id] + filter_dicts)

        tasks = [_ws_query(url, req_msg, sub_id) for url in self.relays]
        per_relay_results = await asyncio.gather(*tasks, return_exceptions=True)

        events: List[Event] = []
        for result in per_relay_results:
            if isinstance(result, Exception):
                continue
            for raw in result:
                try:
                    event = Event(
                        public_key=raw.get("pubkey", ""),
                        content=raw.get("content", ""),
                        created_at=raw.get("created_at", int(time.time())),
                        kind=raw.get("kind", 30078),
                        tags=raw.get("tags", []),
                        signature=raw.get("sig", ""),
                    )
                    events.append(event)
                except Exception as e:
                    logger.debug("Nostr: skipping malformed event: %s", e)

        logger.debug("Nostr: query returned %d event(s) across %d relay(s)", len(events), len(self.relays))
        return events

class P2PDiscoveryManager:
    """Main discovery manager coordinating multiple discovery protocols."""
    
    def __init__(self, private_key: str = None):
        self.dht_node = DHTNode()
        self.nostr_discovery = EnhancedNostrDiscovery(private_key) if NOSTR_AVAILABLE else None
        self.discovered_agents = {}
        self.discovery_protocols = [DiscoveryProtocol.DHT]
        if NOSTR_AVAILABLE:
            self.discovery_protocols.append(DiscoveryProtocol.NOSTR)
        
    async def register_agent(self, agent_info: AgentInfo):
        """Register an agent for discovery."""
        # Register with DHT
        await self.dht_node.store_agent_info(agent_info)
        
        # Broadcast via Nostr when available
        if self.nostr_discovery is not None:
            await self.nostr_discovery.broadcast_agent(agent_info)
        
        # Cache locally
        self.discovered_agents[agent_info.agent_id] = agent_info
        
        logging.info(f"Registered agent {agent_info.name} for discovery")
    
    async def discover_agents(self, query: DiscoveryQuery) -> List[AgentInfo]:
        """Discover agents using multiple protocols."""
        all_agents = []
        
        # Use DHT discovery
        if DiscoveryProtocol.DHT in self.discovery_protocols:
            try:
                dht_agents = await self.dht_node.find_agents(query)
                all_agents.extend(dht_agents)
            except Exception as e:
                logging.warning(f"DHT discovery failed: {e}")
        
        # Use Nostr discovery
        if DiscoveryProtocol.NOSTR in self.discovery_protocols and self.nostr_discovery is not None:
            try:
                nostr_agents = await self.nostr_discovery.discover_agents(query)
                all_agents.extend(nostr_agents)
            except Exception as e:
                logging.warning(f"Nostr discovery failed: {e}")
        
        # Remove duplicates and sort by reputation
        unique_agents = {}
        for agent in all_agents:
            if agent.agent_id not in unique_agents:
                unique_agents[agent.agent_id] = agent
            else:
                # Keep the one with higher reputation
                if agent.reputation_score > unique_agents[agent.agent_id].reputation_score:
                    unique_agents[agent.agent_id] = agent
        
        # Sort by reputation score
        sorted_agents = sorted(
            unique_agents.values(),
            key=lambda x: x.reputation_score,
            reverse=True
        )
        
        return sorted_agents[:query.max_results]
    
    async def update_agent_reputation(self, agent_id: str, score_delta: float):
        """Update agent reputation score."""
        if agent_id in self.discovered_agents:
            self.discovered_agents[agent_id].reputation_score += score_delta
            self.discovered_agents[agent_id].reputation_score = max(0.0, min(1.0, 
                self.discovered_agents[agent_id].reputation_score))
    
    def add_peer_node(self, peer_url: str):
        """Add a peer DHT node."""
        self.dht_node.peers.add(peer_url)
    
    def set_discovery_protocols(self, protocols: List[DiscoveryProtocol]):
        """Set which discovery protocols to use."""
        self.discovery_protocols = protocols


# ---------------------------------------------------------------------------
# Module-level singleton — one shared manager for the process lifetime.
# Follows the same lazy pattern as AgentWallet in agent_wallet.py.
# ---------------------------------------------------------------------------

_manager: Optional["P2PDiscoveryManager"] = None


def get_discovery_manager(private_key: Optional[str] = None) -> "P2PDiscoveryManager":
    """Return the process-wide P2PDiscoveryManager, creating it on first call."""
    global _manager
    if _manager is None:
        _manager = P2PDiscoveryManager(private_key)
    return _manager
