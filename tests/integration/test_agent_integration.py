"""
Integration tests for BitAgent system.
Tests complete workflows and agent interactions.
"""

import pytest
import asyncio
import json
import time
from unittest.mock import Mock, patch, AsyncMock
import tempfile
import os

# Import modules
import sys
sys.path.append('/home/charlie/bitagent/src')

from security.authentication import AuthenticationManager
from security.encryption import EncryptionManager
from security.secure_communication import SecureCommunicationManager, MessageType, SecurityLevel
from security.payment_security import PaymentSecurityManager
from identity.enhanced_did import EnhancedDIDManager, TrustLevel
from monitoring.audit_logger import AuditLogger, EventType
from network.p2p_discovery import P2PDiscoveryManager, AgentInfo, DiscoveryQuery, DiscoveryProtocol

class TestAgentWorkflow:
    """Test complete agent workflows."""
    
    def setup_method(self):
        self.auth_manager = AuthenticationManager()
        self.encryption_manager = EncryptionManager()
        self.payment_security = PaymentSecurityManager()
        self.did_manager = EnhancedDIDManager()
        self.audit_logger = AuditLogger()
        self.discovery_manager = P2PDiscoveryManager()
    
    @pytest.mark.asyncio
    async def test_agent_registration_workflow(self):
        """Test complete agent registration workflow."""
        agent_id = "test_agent_001"
        
        # Step 1: Create DID
        did = self.did_manager.create_did(agent_id)
        assert did is not None
        
        # Step 2: Issue capability credential
        credential = self.did_manager.issue_verifiable_credential(
            did, "agent-capability", {"services": ["translation", "transcription"]}
        )
        assert credential is not None
        
        # Step 3: Generate API key
        api_key = self.auth_manager.generate_api_key(agent_id, ["read", "write"])
        assert api_key is not None
        
        # Step 4: Register for discovery
        agent_info = AgentInfo(
            agent_id=agent_id,
            name="Test Translation Agent",
            description="Provides translation services",
            endpoint="http://localhost:8000",
            services=["translation"],
            public_key="test_public_key",
            protocol="https",
            last_seen=time.time()
        )
        
        await self.discovery_manager.register_agent(agent_info)
        
        # Step 5: Log registration event
        self.audit_logger.log_event(
            EventType.AGENT_ACTION,
            agent_id,
            "agent_registration",
            {"did": did, "services": ["translation"]}
        )
        
        # Verify registration
        events = self.audit_logger.get_events(EventType.AGENT_ACTION)
        assert len(events) == 1
        assert events[0].agent_id == agent_id
    
    @pytest.mark.asyncio
    async def test_secure_service_request_workflow(self):
        """Test secure service request workflow."""
        # Setup agents
        client_agent = "client_agent"
        service_agent = "service_agent"
        
        # Create DIDs
        client_did = self.did_manager.create_did(client_agent)
        service_did = self.did_manager.create_did(service_agent)
        
        # Generate API keys
        client_api_key = self.auth_manager.generate_api_key(client_agent)
        service_api_key = self.auth_manager.generate_api_key(service_agent)
        
        # Setup communication managers
        client_comm = SecureCommunicationManager(client_agent, self.auth_manager)
        service_comm = SecureCommunicationManager(service_agent, self.auth_manager)
        
        # Establish secure channel
        service_public_key = service_comm.key_exchange.get_public_key_bytes()
        channel_id = await client_comm.establish_secure_channel(
            service_agent, service_public_key, SecurityLevel.SECURE
        )
        
        # Create escrow payment
        escrow = self.payment_security.create_escrow_payment(
            client_agent, service_agent, 1000, "Translation service"
        )
        
        # Fund escrow (mock)
        with patch.object(self.payment_security, '_verify_payment', return_value=True):
            self.payment_security.fund_escrow(escrow.escrow_id, "payment_hash")
        
        # Send service request
        request_data = {
            "service": "translation",
            "text": "Hello world",
            "target_language": "es",
            "escrow_id": escrow.escrow_id
        }
        
        success = await client_comm.send_secure_message(
            channel_id, MessageType.REQUEST, request_data
        )
        
        assert success is True
        
        # Log the transaction
        self.audit_logger.log_payment(
            client_agent, escrow.escrow_id, 1000, True
        )
        
        # Verify logging
        payment_events = self.audit_logger.get_events(EventType.PAYMENT)
        assert len(payment_events) == 1
    
    @pytest.mark.asyncio
    async def test_dispute_resolution_workflow(self):
        """Test dispute resolution workflow."""
        # Create escrow
        escrow = self.payment_security.create_escrow_payment(
            "buyer", "seller", 1000, "Test service"
        )
        
        # Fund escrow
        with patch.object(self.payment_security, '_verify_payment', return_value=True):
            self.payment_security.fund_escrow(escrow.escrow_id, "payment_hash")
        
        # Create dispute
        dispute = self.payment_security.create_dispute(
            escrow.escrow_id, "buyer", "Service not delivered as promised"
        )
        
        # Log dispute creation
        self.audit_logger.log_security_event(
            "buyer", "dispute_created", {"dispute_id": dispute.dispute_id}
        )
        
        # Resolve dispute
        resolution_success = self.payment_security.resolve_dispute(
            dispute.dispute_id, "arbitrator_1", "Service was delivered correctly", None
        )
        
        assert resolution_success is True
        
        # Log resolution
        self.audit_logger.log_security_event(
            "arbitrator_1", "dispute_resolved", {"dispute_id": dispute.dispute_id}
        )
        
        # Verify resolution
        dispute_info = self.payment_security.get_dispute_info(dispute.dispute_id)
        assert dispute_info["status"] == "resolved"
    
    @pytest.mark.asyncio
    async def test_agent_discovery_workflow(self):
        """Test agent discovery workflow."""
        # Register multiple agents
        agents = [
            AgentInfo(
                agent_id="agent_1",
                name="Translation Agent",
                description="Provides translation services",
                endpoint="http://localhost:8001",
                services=["translation"],
                public_key="pubkey1",
                protocol="https",
                last_seen=time.time()
            ),
            AgentInfo(
                agent_id="agent_2",
                name="Transcription Agent",
                description="Provides transcription services",
                endpoint="http://localhost:8002",
                services=["transcription"],
                public_key="pubkey2",
                protocol="https",
                last_seen=time.time()
            ),
            AgentInfo(
                agent_id="agent_3",
                name="Multi-service Agent",
                description="Provides multiple services",
                endpoint="http://localhost:8003",
                services=["translation", "transcription"],
                public_key="pubkey3",
                protocol="https",
                last_seen=time.time()
            )
        ]
        
        for agent in agents:
            await self.discovery_manager.register_agent(agent)
        
        # Search for translation services
        query = DiscoveryQuery(
            service_type="translation",
            max_results=10
        )
        
        found_agents = await self.discovery_manager.discover_agents(query)
        
        # Should find agents 1 and 3
        assert len(found_agents) >= 2
        agent_ids = [agent.agent_id for agent in found_agents]
        assert "agent_1" in agent_ids
        assert "agent_3" in agent_ids
    
    def test_trust_score_calculation_workflow(self):
        """Test trust score calculation workflow."""
        agent_id = "test_agent"
        
        # Simulate interactions
        interactions = [
            {"success": True, "payment_success": 1, "quality_score": 0.9, "response_time": 1.0, "uptime": 0.95},
            {"success": True, "payment_success": 1, "quality_score": 0.8, "response_time": 2.0, "uptime": 0.90},
            {"success": True, "payment_success": 1, "quality_score": 0.85, "response_time": 1.5, "uptime": 0.92},
            {"success": False, "payment_success": 0, "quality_score": 0.3, "response_time": 10.0, "uptime": 0.50},
            {"success": True, "payment_success": 1, "quality_score": 0.88, "response_time": 1.2, "uptime": 0.94}
        ]
        
        # Calculate trust score
        trust_score = self.did_manager.calculate_trust_score(agent_id, interactions)
        
        assert trust_score.agent_id == agent_id
        assert trust_score.total_interactions == 5
        assert trust_score.positive_interactions == 4
        assert trust_score.overall_score > 0.5  # Should be reasonably high
        
        # Update interaction
        self.did_manager.update_agent_interaction(agent_id, {"success": True, "quality_score": 0.9})
        
        # Verify trust score is updated
        updated_score = self.did_manager.get_agent_reputation(agent_id)
        assert updated_score is not None

class TestSecurityIntegration:
    """Test security feature integration."""
    
    def setup_method(self):
        self.auth_manager = AuthenticationManager()
        self.encryption_manager = EncryptionManager()
        self.audit_logger = AuditLogger()
    
    def test_authentication_with_encryption(self):
        """Test authentication combined with encryption."""
        agent_id = "test_agent"
        
        # Generate API key
        api_key = self.auth_manager.generate_api_key(agent_id)
        
        # Create encrypted message
        message_data = {"sensitive": "data", "timestamp": time.time()}
        password = "encryption_password"
        
        encrypted_data = self.encryption_manager.encrypt_with_password(
            json.dumps(message_data).encode(), password
        )
        
        # Create signed message with encrypted payload
        signed_message = self.auth_manager.create_signed_message(
            {"encrypted_payload": encrypted_data, "agent_id": agent_id}, agent_id
        )
        
        # Verify signed message
        verified_data = self.auth_manager.verify_signed_message(signed_message)
        assert verified_data is not None
        
        # Decrypt payload
        decrypted_data = self.encryption_manager.decrypt_with_password(
            verified_data["message"]["encrypted_payload"], password
        )
        
        decrypted_message = json.loads(decrypted_data.decode())
        assert decrypted_message == message_data
    
    def test_audit_logging_with_security_events(self):
        """Test audit logging with security events."""
        agent_id = "test_agent"
        
        # Log authentication
        self.audit_logger.log_authentication(agent_id, "login", True, "192.168.1.1")
        
        # Log payment
        self.audit_logger.log_payment(agent_id, "payment_123", 1000, True)
        
        # Log security event
        self.audit_logger.log_security_event(
            agent_id, "suspicious_activity", {"reason": "unusual_pattern"}
        )
        
        # Generate security report
        report = self.audit_logger.generate_security_report()
        
        assert report["failed_authentications"] == 0
        assert "security_events" in report
        assert report["total_events"] >= 3

class TestPerformanceIntegration:
    """Test performance monitoring integration."""
    
    def setup_method(self):
        self.audit_logger = AuditLogger()
    
    def test_performance_monitoring_workflow(self):
        """Test performance monitoring workflow."""
        agent_id = "test_agent"
        
        # Simulate service requests with timing
        start_time = time.time()
        
        # Log successful request
        self.audit_logger.log_event(
            EventType.AGENT_ACTION,
            agent_id,
            "service_request",
            {"service": "translation", "duration_ms": 1500},
            result="success",
            duration_ms=1500
        )
        
        # Log failed request
        self.audit_logger.log_event(
            EventType.AGENT_ACTION,
            agent_id,
            "service_request",
            {"service": "translation", "error": "timeout"},
            severity="ERROR",
            result="failure",
            duration_ms=5000
        )
        
        # Get events
        events = self.audit_logger.get_events(EventType.AGENT_ACTION)
        assert len(events) == 2
        
        # Check performance metrics
        successful_requests = [e for e in events if e.result == "success"]
        failed_requests = [e for e in events if e.result == "failure"]
        
        assert len(successful_requests) == 1
        assert len(failed_requests) == 1
        assert successful_requests[0].duration_ms == 1500
        assert failed_requests[0].duration_ms == 5000

class TestErrorHandling:
    """Test error handling and recovery."""
    
    def setup_method(self):
        self.auth_manager = AuthenticationManager()
        self.payment_security = PaymentSecurityManager()
    
    def test_invalid_api_key_handling(self):
        """Test handling of invalid API keys."""
        # Test with invalid API key
        payload = self.auth_manager.verify_api_key("invalid_key")
        assert payload is None
        
        # Test with expired API key
        with patch('time.time', return_value=0):
            expired_key = self.auth_manager.generate_api_key("test_agent")
        
        payload = self.auth_manager.verify_api_key(expired_key)
        assert payload is None
    
    def test_payment_error_handling(self):
        """Test payment error handling."""
        # Test with non-existent escrow
        success = self.payment_security.fund_escrow("nonexistent_escrow", "payment_hash")
        assert success is False
        
        # Test with invalid dispute
        success = self.payment_security.resolve_dispute(
            "nonexistent_dispute", "arbitrator", "resolution"
        )
        assert success is False
    
    def test_encryption_error_handling(self):
        """Test encryption error handling."""
        encryption_manager = EncryptionManager()
        
        # Test decryption with wrong password
        data = b"test data"
        encrypted = encryption_manager.encrypt_with_password(data, "correct_password")
        
        try:
            decrypted = encryption_manager.decrypt_with_password(encrypted, "wrong_password")
            assert False, "Should have raised an exception"
        except Exception:
            # Expected to fail
            pass

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
