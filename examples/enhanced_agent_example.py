#!/usr/bin/env python3
"""
Enhanced BitAgent Example - Demonstrates the new security and P2P features.
This example shows how to use the enhanced BitAgent framework with:
- Secure authentication and encryption
- Peer-to-peer discovery
- Escrow payments
- Trust and reputation systems
- Comprehensive monitoring
"""

import asyncio
import json
import time
import logging
from typing import Dict, Any, List

# Import enhanced modules
import sys
sys.path.append('/home/charlie/bitagent/src')

from security.authentication import AuthenticationManager, RateLimiter
from security.encryption import EncryptionManager, KeyExchange
from security.secure_communication import SecureCommunicationManager, MessageType, SecurityLevel
from security.payment_security import PaymentSecurityManager, EscrowStatus
from identity.enhanced_did import EnhancedDIDManager, TrustLevel
from monitoring.audit_logger import AuditLogger, EventType, SecurityEvent
from monitoring.performance_monitor import PerformanceMonitor, AgentPerformanceTracker
from network.p2p_discovery import P2PDiscoveryManager, AgentInfo, DiscoveryQuery

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class EnhancedBitAgent:
    """Enhanced BitAgent with full security and P2P capabilities."""
    
    def __init__(self, agent_id: str, name: str, description: str, services: List[str]):
        self.agent_id = agent_id
        self.name = name
        self.description = description
        self.services = services
        
        # Initialize security components
        self.auth_manager = AuthenticationManager()
        self.encryption_manager = EncryptionManager()
        self.comm_manager = SecureCommunicationManager(agent_id, self.auth_manager)
        self.payment_security = PaymentSecurityManager()
        
        # Initialize identity and trust
        self.did_manager = EnhancedDIDManager()
        self.did = self.did_manager.create_did(agent_id)
        
        # Initialize monitoring
        self.audit_logger = AuditLogger(f"audit_{agent_id}.log")
        self.performance_monitor = PerformanceMonitor()
        self.performance_tracker = AgentPerformanceTracker(agent_id, self.performance_monitor)
        
        # Initialize discovery
        self.discovery_manager = P2PDiscoveryManager()
        
        # Generate API key
        self.api_key = self.auth_manager.generate_api_key(agent_id, ["read", "write", "admin"])
        
        # Register for discovery
        self.agent_info = AgentInfo(
            agent_id=agent_id,
            name=name,
            description=description,
            endpoint=f"http://localhost:8000/{agent_id}",
            services=services,
            public_key=self.comm_manager.key_exchange.get_public_key_bytes().hex(),
            protocol="https",
            last_seen=time.time()
        )
        
        logger.info(f"Enhanced BitAgent {name} initialized with DID: {self.did}")
    
    async def start(self):
        """Start the agent and register for discovery."""
        # Start performance monitoring
        self.performance_monitor.start_monitoring()
        
        # Register agent for discovery
        await self.discovery_manager.register_agent(self.agent_info)
        
        # Log startup
        self.audit_logger.log_event(
            EventType.SYSTEM,
            self.agent_id,
            "agent_startup",
            {"services": self.services, "did": self.did}
        )
        
        logger.info(f"Agent {self.name} started and registered for discovery")
    
    async def stop(self):
        """Stop the agent gracefully."""
        # Stop performance monitoring
        self.performance_monitor.stop_monitoring()
        
        # Log shutdown
        self.audit_logger.log_event(
            EventType.SYSTEM,
            self.agent_id,
            "agent_shutdown",
            {}
        )
        
        logger.info(f"Agent {self.name} stopped")
    
    async def discover_services(self, service_type: str) -> List[AgentInfo]:
        """Discover agents providing a specific service."""
        query = DiscoveryQuery(
            service_type=service_type,
            max_results=10
        )
        
        agents = await self.discovery_manager.discover_agents(query)
        
        # Log discovery
        self.audit_logger.log_event(
            EventType.DISCOVERY,
            self.agent_id,
            "service_discovery",
            {"service_type": service_type, "found_agents": len(agents)}
        )
        
        return agents
    
    async def request_service(self, target_agent_id: str, service: str, 
                            parameters: Dict[str, Any], amount_sats: int) -> Dict[str, Any]:
        """Request a service from another agent with secure payment."""
        start_time = time.time()
        
        try:
            # Discover the target agent
            agents = await self.discover_services(service)
            target_agent = next((a for a in agents if a.agent_id == target_agent_id), None)
            
            if not target_agent:
                raise ValueError(f"Agent {target_agent_id} not found")
            
            # Create escrow payment
            escrow = self.payment_security.create_escrow_payment(
                self.agent_id, target_agent_id, amount_sats, f"{service} service"
            )
            
            # Establish secure communication channel
            target_public_key = bytes.fromhex(target_agent.public_key)
            channel_id = await self.comm_manager.establish_secure_channel(
                target_agent_id, target_public_key, SecurityLevel.SECURE
            )
            
            # Send service request
            request_data = {
                "service": service,
                "parameters": parameters,
                "escrow_id": escrow.escrow_id,
                "amount_sats": amount_sats
            }
            
            success = await self.comm_manager.send_secure_message(
                channel_id, MessageType.REQUEST, request_data
            )
            
            if not success:
                raise Exception("Failed to send service request")
            
            # Log the request
            self.audit_logger.log_communication(
                self.agent_id, target_agent_id, "service_request", True,
                {"service": service, "escrow_id": escrow.escrow_id}
            )
            
            # Record performance
            duration_ms = (time.time() - start_time) * 1000
            self.performance_tracker.record_request(duration_ms, True, service)
            
            return {
                "status": "request_sent",
                "escrow_id": escrow.escrow_id,
                "channel_id": channel_id,
                "duration_ms": duration_ms
            }
            
        except Exception as e:
            # Log error
            duration_ms = (time.time() - start_time) * 1000
            self.performance_tracker.record_request(duration_ms, False, service)
            
            self.audit_logger.log_event(
                EventType.AGENT_ACTION,
                self.agent_id,
                "service_request_failed",
                {"error": str(e), "target_agent": target_agent_id},
                severity="ERROR",
                result="failure"
            )
            
            raise
    
    async def handle_service_request(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle incoming service requests."""
        start_time = time.time()
        
        try:
            service = request_data.get("service")
            parameters = request_data.get("parameters", {})
            escrow_id = request_data.get("escrow_id")
            
            # Process the service
            result = await self._process_service(service, parameters)
            
            # Log successful processing
            duration_ms = (time.time() - start_time) * 1000
            self.audit_logger.log_event(
                EventType.AGENT_ACTION,
                self.agent_id,
                "service_processed",
                {"service": service, "escrow_id": escrow_id},
                result="success",
                duration_ms=duration_ms
            )
            
            return {
                "status": "success",
                "result": result,
                "processing_time_ms": duration_ms
            }
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            
            self.audit_logger.log_event(
                EventType.AGENT_ACTION,
                self.agent_id,
                "service_processing_failed",
                {"error": str(e)},
                severity="ERROR",
                result="failure",
                duration_ms=duration_ms
            )
            
            return {
                "status": "error",
                "error": str(e),
                "processing_time_ms": duration_ms
            }
    
    async def _process_service(self, service: str, parameters: Dict[str, Any]) -> Any:
        """Process a service request (implement your service logic here)."""
        if service == "translation":
            text = parameters.get("text", "")
            target_language = parameters.get("target_language", "es")
            
            # Mock translation (replace with real implementation)
            translations = {
                "es": "Hola mundo",
                "fr": "Bonjour le monde",
                "de": "Hallo Welt"
            }
            
            return {
                "original_text": text,
                "translated_text": translations.get(target_language, text),
                "target_language": target_language
            }
        
        elif service == "transcription":
            audio_data = parameters.get("audio_data", "")
            
            # Mock transcription (replace with real implementation)
            return {
                "transcribed_text": "This is a mock transcription of the audio data",
                "confidence": 0.95
            }
        
        else:
            raise ValueError(f"Unknown service: {service}")
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics."""
        return self.performance_tracker.get_performance_stats()
    
    def get_security_report(self) -> Dict[str, Any]:
        """Get security report."""
        return self.audit_logger.generate_security_report()
    
    def get_trust_score(self) -> float:
        """Get current trust score."""
        trust_score = self.did_manager.get_agent_reputation(self.agent_id)
        return trust_score.overall_score if trust_score else 0.0

async def main():
    """Main example demonstrating enhanced BitAgent capabilities."""
    logger.info("Starting Enhanced BitAgent Example")
    
    # Create agents
    translation_agent = EnhancedBitAgent(
        "translation_agent_001",
        "Polyglot Translator",
        "Advanced translation services with AI",
        ["translation"]
    )
    
    transcription_agent = EnhancedBitAgent(
        "transcription_agent_001", 
        "Audio Transcriber",
        "High-quality audio transcription services",
        ["transcription"]
    )
    
    coordinator_agent = EnhancedBitAgent(
        "coordinator_agent_001",
        "Task Coordinator", 
        "Orchestrates complex multi-agent workflows",
        ["translation", "transcription", "coordination"]
    )
    
    try:
        # Start agents
        await asyncio.gather(
            translation_agent.start(),
            transcription_agent.start(),
            coordinator_agent.start()
        )
        
        # Wait for discovery to propagate
        await asyncio.sleep(2)
        
        # Demonstrate service discovery
        logger.info("Discovering translation services...")
        translation_services = await coordinator_agent.discover_services("translation")
        logger.info(f"Found {len(translation_services)} translation services")
        
        # Demonstrate service request
        logger.info("Requesting translation service...")
        result = await coordinator_agent.request_service(
            "translation_agent_001",
            "translation",
            {"text": "Hello, world!", "target_language": "es"},
            100  # 100 sats
        )
        logger.info(f"Service request result: {result}")
        
        # Demonstrate performance monitoring
        await asyncio.sleep(1)
        stats = coordinator_agent.get_performance_stats()
        logger.info(f"Performance stats: {stats}")
        
        # Demonstrate security reporting
        security_report = coordinator_agent.get_security_report()
        logger.info(f"Security report: {json.dumps(security_report, indent=2)}")
        
        # Demonstrate trust scores
        trust_score = coordinator_agent.get_trust_score()
        logger.info(f"Trust score: {trust_score}")
        
    except Exception as e:
        logger.error(f"Error in main example: {e}")
    
    finally:
        # Stop agents
        await asyncio.gather(
            translation_agent.stop(),
            transcription_agent.stop(), 
            coordinator_agent.stop()
        )
        
        logger.info("Enhanced BitAgent Example completed")

if __name__ == "__main__":
    asyncio.run(main())
