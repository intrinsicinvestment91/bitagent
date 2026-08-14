"""Security tests for authentication, DID identity, and audit logging.

The escrow, secure-channel and homemade-crypto modules these also used to cover
were deleted: their payment verification was a `return True` placeholder with no
wallet behind it, the channel manager returned "Mock result from ...", and the
encryption module's `_hkdf_expand` was a truncated SHA-256 rather than HKDF.
None of them were reachable from a request.
"""

import os
import tempfile
import time
from unittest.mock import patch

from src.identity.enhanced_did import CredentialType, EnhancedDIDManager
from src.monitoring.audit_logger import AuditLogger, EventType, LogLevel, SecurityEvent
from src.security.authentication import AuthenticationManager, RateLimiter


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
        with patch("time.time", return_value=0):
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
        for _ in range(5):
            assert rate_limiter.is_allowed(agent_id) is True

        # Exceed limit
        assert rate_limiter.is_allowed(agent_id) is False


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
            {
                "success": True,
                "payment_success": 1,
                "quality_score": 0.9,
                "response_time": 1.0,
                "uptime": 0.95,
            },
            {
                "success": True,
                "payment_success": 1,
                "quality_score": 0.8,
                "response_time": 2.0,
                "uptime": 0.90,
            },
            {
                "success": False,
                "payment_success": 0,
                "quality_score": 0.3,
                "response_time": 10.0,
                "uptime": 0.50,
            },
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
            SecurityEvent.LOGIN_SUCCESS,
        )

        events = self.audit_logger.get_events(EventType.AUTHENTICATION)
        assert len(events) == 1
        assert events[0].agent_id == "test_agent"
        assert events[0].action == "login"

    def test_authentication_logging(self):
        """Test authentication event logging."""
        self.audit_logger.log_authentication("test_agent", "login", True, "192.168.1.1")

        events = self.audit_logger.get_events(EventType.AUTHENTICATION)
        assert len(events) == 1
        assert events[0].result == "success"
        assert events[0].ip_address == "192.168.1.1"

    def test_payment_logging(self):
        """Test payment event logging."""
        self.audit_logger.log_payment("test_agent", "payment_123", 1000, True)

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
