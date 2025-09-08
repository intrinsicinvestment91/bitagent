"""
Enhanced peer-to-peer discovery system using DHT, Nostr, and custom protocols.
Implements distributed agent discovery with security and reliability.
"""

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

# Nostr imports
from nostr.event import Event, EventKind
from nostr.key import PrivateKey, PublicKey
from nostr.relay_manager import RelayManager
from nostr.filter import Filter, Filters
from nostr.message_type import ClientMessageType

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
        self.private_key = PrivateKey(bytes.fromhex(private_key)) if private_key else PrivateKey()
        self.public_key = self.private_key.public_key
        self.relay_manager = RelayManager()
        self.agent_cache = {}
        self.reputation_scores = {}
        
        # Add default relays
        self.relays = [
            "wss://relay.damus.io",
            "wss://relay.snort.social",
            "wss://nos.lol",
            "wss://nostr.wine",
            "wss://relay.nostr.band"
        ]
        
        for relay in self.relays:
            self.relay_manager.add_relay(relay)
    
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
            pubkey=self.public_key.hex(),
            kind=30078,  # Custom agent announcement kind
            content=json.dumps(content),
            tags=[
                ["t", "bitagent"],
                ["t", "agent-discovery"],
                ["service", *agent_info.services],
                ["endpoint", agent_info.endpoint]
            ]
        )
        
        self.private_key.sign_event(event)
        
        await self._publish_event(event)
        logging.info(f"Broadcasted agent {agent_info.name} via Nostr")
    
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
    
    async def _publish_event(self, event: Event):
        """Publish event to Nostr relays."""
        self.relay_manager.open_connections({"cert_reqs": 0})
        await asyncio.sleep(1.25)  # Let relays connect
        
        msg = json.dumps([ClientMessageType.EVENT, event.to_dict()])
        for relay in self.relay_manager.relays.values():
            relay.send_message(msg)
        
        await asyncio.sleep(2)
        self.relay_manager.close_connections()
    
    async def _query_events(self, filters: Filters) -> List[Event]:
        """Query events from Nostr relays."""
        events = []
        
        self.relay_manager.open_connections({"cert_reqs": 0})
        await asyncio.sleep(1.25)
        
        # Subscribe to events
        subscription_id = f"agent-discovery-{int(time.time())}"
        msg = json.dumps([ClientMessageType.REQUEST, subscription_id, filters.to_json_array()])
        
        for relay in self.relay_manager.relays.values():
            relay.send_message(msg)
        
        # Collect events
        await asyncio.sleep(5)  # Wait for responses
        
        for relay in self.relay_manager.relays.values():
            events.extend(relay.events)
        
        self.relay_manager.close_connections()
        return events

class P2PDiscoveryManager:
    """Main discovery manager coordinating multiple discovery protocols."""
    
    def __init__(self, private_key: str = None):
        self.dht_node = DHTNode()
        self.nostr_discovery = EnhancedNostrDiscovery(private_key)
        self.discovered_agents = {}
        self.discovery_protocols = [DiscoveryProtocol.NOSTR, DiscoveryProtocol.DHT]
        
    async def register_agent(self, agent_info: AgentInfo):
        """Register an agent for discovery."""
        # Register with DHT
        await self.dht_node.store_agent_info(agent_info)
        
        # Broadcast via Nostr
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
        if DiscoveryProtocol.NOSTR in self.discovery_protocols:
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
