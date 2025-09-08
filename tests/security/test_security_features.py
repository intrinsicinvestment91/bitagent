"""
Comprehensive security testing framework for BitAgent.
Tests authentication, encryption, input validation, and security protocols.
"""

import pytest
import asyncio
import json
import time
from unittest.mock import Mock, patch
import tempfile
import os

# Import security modules
import sys
sys.path.append('/home/charlie/bitagent/src')

from security.authentication import AuthenticationManager, RateLimiter
from security.encryption import EncryptionManager, KeyExchange, SecureMessage, InputValidator
from security.secure_communication import SecureCommunicationManager, MessageType, SecurityLevel
from security.payment_security import PaymentSecurityManager, EscrowStatus, DisputeStatus
from identity.enhanced_did import EnhancedDIDManager, DIDMethod, CredentialType, TrustLevel
from monitoring.audit_logger import AuditLogger, EventType, SecurityEvent, LogLevel

class TestAuthentication:
    """Test authentication and authorization features."""
    
    def setup_method(self):
        self.auth_manager = AuthenticationManager()
    
    def test_api_key_generation(self):
        """Test API key generation and verification."""
        agent_id = "test_agent"
        permissions = ["read", "write"]
        
        api_key = self.auth_manager.generate_api_key(agent_id, permissions)
        assert api_key is not None
        
        # Verify the API key
        payload = self.auth_manager.verify_api_key(api_key)
        assert payload is not None
        assert payload["agent_id"] == agent_id
        assert payload["permissions"] == permissions
    
    def test_api_key_expiration(self):
        """Test API key expiration."""
        agent_id = "test_agent"
        
        # Create expired API key
        with patch('time.time', return_value=0):
            api_key = self.auth_manager.generate_api_key(agent_id)
        
        # Verify it's expired
        payload = self.auth_manager.verify_api_key(api_key)
        assert payload is None
    
    def test_signed_message_creation(self):
        """Test signed message creation and verification."""
        message = {"test": "data", "timestamp": time.time()}
        agent_id = "test_agent"
        
        signed_message = self.auth_manager.create_signed_message(message, agent_id)
        assert "data" in signed_message
        assert "signature" in signed_message
        assert "public_key" in signed_message
        
        # Verify the signed message
        verified_data = self.auth_manager.verify_signed_message(signed_message)
        assert verified_data is not None
        assert verified_data["message"] == message
        assert verified_data["agent_id"] == agent_id
    
    def test_jwt_token_management(self):
        """Test JWT token creation and verification."""
        agent_id = "test_agent"
        permissions = ["read", "write"]
        
        token = self.auth_manager.create_jwt_token(agent_id, permissions)
        assert token is not None
        
        # Verify the token
        payload = self.auth_manager.verify_jwt_token(token)
        assert payload is not None
        assert payload["agent_id"] == agent_id
        assert payload["permissions"] == permissions
        
        # Test token revocation
        self.auth_manager.revoke_token(token)
        payload = self.auth_manager.verify_jwt_token(token)
        assert payload is None
    
    def test_rate_limiting(self):
        """Test rate limiting functionality."""
        rate_limiter = RateLimiter(max_requests=5, window_seconds=60)
        agent_id = "test_agent"
        
        # Make requests within limit
        for i in range(5):
            assert rate_limiter.is_allowed(agent_id) is True
        
        # Exceed limit
        assert rate_limiter.is_allowed(agent_id) is False

class TestEncryption:
    """Test encryption and decryption features."""
    
    def setup_method(self):
        self.encryption_manager = EncryptionManager()
    
    def test_symmetric_key_generation(self):
        """Test symmetric key generation."""
        key = self.encryption_manager.generate_symmetric_key()
        assert len(key) == 32
        assert isinstance(key, bytes)
    
    def test_password_based_encryption(self):
        """Test password-based encryption and decryption."""
        data = b"Test data for encryption"
        password = "test_password"
        
        encrypted = self.encryption_manager.encrypt_with_password(data, password)
        assert encrypted is not None
        assert isinstance(encrypted, str)
        
        decrypted = self.encryption_manager.decrypt_with_password(encrypted, password)
        assert decrypted == data
    
    def test_aes_gcm_encryption(self):
        """Test AES-GCM encryption."""
        data = b"Test data for AES-GCM encryption"
        key = self.encryption_manager.generate_symmetric_key()
        
        ciphertext, iv, _ = self.encryption_manager.encrypt_aes_gcm(data, key)
        assert ciphertext is not None
        assert iv is not None
        
        decrypted = self.encryption_manager.decrypt_aes_gcm(ciphertext, key, iv)
        assert decrypted == data
    
    def test_chacha20_poly1305_encryption(self):
        """Test ChaCha20-Poly1305 encryption."""
        data = b"Test data for ChaCha20-Poly1305 encryption"
        key = self.encryption_manager.generate_symmetric_key()
        
        ciphertext, nonce = self.encryption_manager.encrypt_chacha20_poly1305(data, key)
        assert ciphertext is not None
        assert nonce is not None
        
        decrypted = self.encryption_manager.decrypt_chacha20_poly1305(ciphertext, key, nonce)
        assert decrypted == data
    
    def test_key_exchange(self):
        """Test key exchange protocol."""
        key_exchange1 = KeyExchange()
        key_exchange2 = KeyExchange()
        
        # Exchange public keys
        pub_key1 = key_exchange1.get_public_key_bytes()
        pub_key2 = key_exchange2.get_public_key_bytes()
        
        # Derive shared secrets
        shared_secret1 = key_exchange1.derive_shared_secret(pub_key2)
        shared_secret2 = key_exchange2.derive_shared_secret(pub_key1)
        
        assert shared_secret1 == shared_secret2
        assert len(shared_secret1) == 32
    
    def test_secure_message(self):
        """Test secure message creation and decryption."""
        secure_message = SecureMessage(self.encryption_manager)
        data = {"test": "data", "number": 42}
        key = self.encryption_manager.generate_symmetric_key()
        
        encrypted_message = secure_message.create_secure_message(data, key)
        assert "ciphertext" in encrypted_message
        assert "nonce" in encrypted_message
        assert "algorithm" in encrypted_message
        
        decrypted_data = secure_message.decrypt_secure_message(encrypted_message, key)
        assert decrypted_data == data
    
    def test_input_validation(self):
        """Test input validation and sanitization."""
        # Test JSON schema validation
        schema = {
            "name": {"type": "string", "max_length": 50, "required": True},
            "age": {"type": "integer", "minimum": 0, "maximum": 150},
            "tags": {"type": "array", "max_items": 10}
        }
        
        valid_data = {"name": "test", "age": 25, "tags": ["tag1", "tag2"]}
        assert InputValidator.validate_json_schema(valid_data, schema) is True
        
        invalid_data = {"name": "x" * 100, "age": -5}  # Invalid name length and age
        assert InputValidator.validate_json_schema(invalid_data, schema) is False
        
        # Test string sanitization
        dirty_string = "Test\x00string\nwith\ttabs"
        clean_string = InputValidator.sanitize_string(dirty_string)
        assert "\x00" not in clean_string
        
        # Test agent ID validation
        assert InputValidator.validate_agent_id("valid_agent_123") is True
        assert InputValidator.validate_agent_id("invalid@agent") is False

class TestSecureCommunication:
    """Test secure agent-to-agent communication."""
    
    def setup_method(self):
        self.comm_manager1 = SecureCommunicationManager("agent1")
        self.comm_manager2 = SecureCommunicationManager("agent2")
    
    @pytest.mark.asyncio
    async def test_secure_channel_establishment(self):
        """Test secure channel establishment."""
        peer_public_key = self.comm_manager2.key_exchange.get_public_key_bytes()
        
        channel_id = await self.comm_manager1.establish_secure_channel(
            "agent2", peer_public_key, SecurityLevel.SECURE
        )
        
        assert channel_id is not None
        assert channel_id in self.comm_manager1.active_channels
    
    @pytest.mark.asyncio
    async def test_secure_message_sending(self):
        """Test secure message sending."""
        # Establish channel
        peer_public_key = self.comm_manager2.key_exchange.get_public_key_bytes()
        channel_id = await self.comm_manager1.establish_secure_channel(
            "agent2", peer_public_key, SecurityLevel.SECURE
        )
        
        # Send message
        payload = {"test": "data", "timestamp": time.time()}
        success = await self.comm_manager1.send_secure_message(
            channel_id, MessageType.REQUEST, payload
        )
        
        assert success is True
    
    def test_channel_info(self):
        """Test channel information retrieval."""
        # This would require a properly established channel
        # For now, test with a mock channel
        channel_info = self.comm_manager1.get_channel_info("nonexistent_channel")
        assert channel_info is None

class TestPaymentSecurity:
    """Test payment security features."""
    
    def setup_method(self):
        self.payment_security = PaymentSecurityManager()
    
    def test_escrow_creation(self):
        """Test escrow payment creation."""
        buyer_id = "buyer_agent"
        seller_id = "seller_agent"
        amount = 1000
        description = "Test service"
        
        escrow = self.payment_security.create_escrow_payment(
            buyer_id, seller_id, amount, description
        )
        
        assert escrow.escrow_id is not None
        assert escrow.buyer_id == buyer_id
        assert escrow.seller_id == seller_id
        assert escrow.amount_sats == amount
        assert escrow.status == EscrowStatus.CREATED
    
    def test_escrow_funding(self):
        """Test escrow funding."""
        # Create escrow
        escrow = self.payment_security.create_escrow_payment(
            "buyer", "seller", 1000, "Test service"
        )
        
        # Mock payment verification
        with patch.object(self.payment_security, '_verify_payment', return_value=True):
            success = self.payment_security.fund_escrow(escrow.escrow_id, "payment_hash")
            assert success is True
            assert escrow.status == EscrowStatus.FUNDED
    
    def test_dispute_creation(self):
        """Test payment dispute creation."""
        # Create and fund escrow
        escrow = self.payment_security.create_escrow_payment(
            "buyer", "seller", 1000, "Test service"
        )
        
        with patch.object(self.payment_security, '_verify_payment', return_value=True):
            self.payment_security.fund_escrow(escrow.escrow_id, "payment_hash")
        
        # Create dispute
        dispute = self.payment_security.create_dispute(
            escrow.escrow_id, "buyer", "Service not delivered"
        )
        
        assert dispute.dispute_id is not None
        assert dispute.escrow_id == escrow.escrow_id
        assert dispute.complainant_id == "buyer"
        assert dispute.status == DisputeStatus.OPEN
    
    def test_fraud_detection(self):
        """Test fraud detection."""
        # Test with normal payment
        normal_payment = {
            "buyer_id": "buyer1",
            "seller_id": "seller1",
            "amount": 1000,
            "timestamp": time.time()
        }
        
        triggered_rules = self.payment_security.detect_payment_fraud(normal_payment)
        assert len(triggered_rules) == 0
        
        # Test with suspicious payment
        suspicious_payment = {
            "buyer_id": "buyer2",
            "seller_id": "seller2",
            "amount": 2000000,  # Very large amount
            "timestamp": time.time()
        }
        
        triggered_rules = self.payment_security.detect_payment_fraud(suspicious_payment)
        # Should trigger high amount rule
        assert len(triggered_rules) > 0

class TestDIDIdentity:
    """Test enhanced DID identity system."""
    
    def setup_method(self):
        self.did_manager = EnhancedDIDManager()
    
    def test_did_creation(self):
        """Test DID document creation."""
        agent_id = "test_agent"
        services = [{"type": "payment", "endpoint": "https://example.com/pay"}]
        
        did = self.did_manager.create_did(agent_id, services)
        assert did.startswith("did:key:")
        assert did in self.did_manager.did_documents
        
        did_document = self.did_manager.did_documents[did]
        assert did_document.id == did
        assert len(did_document.service) == 1
    
    def test_verifiable_credential(self):
        """Test verifiable credential creation and verification."""
        subject_did = "did:key:test_subject"
        credential_data = {"capability": "translation", "level": "expert"}
        
        credential = self.did_manager.issue_verifiable_credential(
            subject_did, CredentialType.AGENT_CAPABILITY, credential_data
        )
        
        assert credential.id is not None
        assert credential.issuer is not None
        assert credential.credential_subject["id"] == subject_did
        
        # Verify credential
        is_valid = self.did_manager.verify_credential(credential)
        assert is_valid is True
    
    def test_trust_score_calculation(self):
        """Test trust score calculation."""
        agent_id = "test_agent"
        interactions = [
            {"success": True, "payment_success": 1, "quality_score": 0.9, "response_time": 1.0, "uptime": 0.95},
            {"success": True, "payment_success": 1, "quality_score": 0.8, "response_time": 2.0, "uptime": 0.90},
            {"success": False, "payment_success": 0, "quality_score": 0.3, "response_time": 10.0, "uptime": 0.50}
        ]
        
        trust_score = self.did_manager.calculate_trust_score(agent_id, interactions)
        
        assert trust_score.agent_id == agent_id
        assert trust_score.total_interactions == 3
        assert trust_score.positive_interactions == 2
        assert 0.0 <= trust_score.overall_score <= 1.0
    
    def test_identity_claim(self):
        """Test identity claim creation and verification."""
        subject_did = "did:key:test_subject"
        claim_data = {"service_type": "translation", "languages": ["en", "es"]}
        
        claim = self.did_manager.create_identity_claim(
            subject_did, "service_capability", claim_data
        )
        
        assert claim.claim_id is not None
        assert claim.subject == subject_did
        assert claim.claim_data == claim_data
        
        # Verify claim
        is_valid = self.did_manager.verify_identity_claim(claim)
        assert is_valid is True

class TestAuditLogging:
    """Test audit logging and monitoring."""
    
    def setup_method(self):
        self.temp_file = tempfile.NamedTemporaryFile(delete=False)
        self.temp_file.close()
        self.audit_logger = AuditLogger(self.temp_file.name)
    
    def teardown_method(self):
        os.unlink(self.temp_file.name)
    
    def test_event_logging(self):
        """Test audit event logging."""
        self.audit_logger.log_event(
            EventType.AUTHENTICATION,
            "test_agent",
            "login",
            {"method": "api_key"},
            SecurityEvent.LOGIN_SUCCESS
        )
        
        events = self.audit_logger.get_events(EventType.AUTHENTICATION)
        assert len(events) == 1
        assert events[0].agent_id == "test_agent"
        assert events[0].action == "login"
    
    def test_authentication_logging(self):
        """Test authentication event logging."""
        self.audit_logger.log_authentication(
            "test_agent", "login", True, "192.168.1.1"
        )
        
        events = self.audit_logger.get_events(EventType.AUTHENTICATION)
        assert len(events) == 1
        assert events[0].result == "success"
        assert events[0].ip_address == "192.168.1.1"
    
    def test_payment_logging(self):
        """Test payment event logging."""
        self.audit_logger.log_payment(
            "test_agent", "payment_123", 1000, True
        )
        
        events = self.audit_logger.get_events(EventType.PAYMENT)
        assert len(events) == 1
        assert events[0].details["payment_id"] == "payment_123"
        assert events[0].details["amount_sats"] == 1000
    
    def test_alert_creation(self):
        """Test alert creation and resolution."""
        alert_id = self.audit_logger.create_alert(
            "test_alert", "Test alert message", LogLevel.WARNING
        )
        
        assert alert_id is not None
        
        active_alerts = self.audit_logger.get_active_alerts()
        assert len(active_alerts) == 1
        assert active_alerts[0].alert_id == alert_id
        
        # Resolve alert
        self.audit_logger.resolve_alert(alert_id, "Test resolution")
        
        active_alerts = self.audit_logger.get_active_alerts()
        assert len(active_alerts) == 0
    
    def test_security_report(self):
        """Test security report generation."""
        # Log some events
        self.audit_logger.log_authentication("agent1", "login", True)
        self.audit_logger.log_authentication("agent2", "login", False)
        self.audit_logger.log_payment("agent1", "payment1", 1000, True)
        
        report = self.audit_logger.generate_security_report()
        
        assert "security_events" in report
        assert "failed_authentications" in report
        assert report["failed_authentications"] == 1

# Integration tests
class TestSecurityIntegration:
    """Integration tests for security features."""
    
    @pytest.mark.asyncio
    async def test_end_to_end_secure_communication(self):
        """Test end-to-end secure communication flow."""
        # Setup
        auth_manager = AuthenticationManager()
        comm_manager1 = SecureCommunicationManager("agent1", auth_manager)
        comm_manager2 = SecureCommunicationManager("agent2", auth_manager)
        
        # Generate API keys
        api_key1 = auth_manager.generate_api_key("agent1", ["read", "write"])
        api_key2 = auth_manager.generate_api_key("agent2", ["read", "write"])
        
        # Verify API keys
        payload1 = auth_manager.verify_api_key(api_key1)
        payload2 = auth_manager.verify_api_key(api_key2)
        
        assert payload1 is not None
        assert payload2 is not None
        
        # Establish secure channel
        peer_public_key = comm_manager2.key_exchange.get_public_key_bytes()
        channel_id = await comm_manager1.establish_secure_channel(
            "agent2", peer_public_key, SecurityLevel.SECURE
        )
        
        assert channel_id is not None
        
        # Send secure message
        message_data = {"service": "translation", "text": "Hello world"}
        success = await comm_manager1.send_secure_message(
            channel_id, MessageType.REQUEST, message_data
        )
        
        assert success is True

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
