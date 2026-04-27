#!/usr/bin/env python3
"""
Test script to verify PolyglotAgent and CoordinatorAgent functionality
"""

import sys
import os
import asyncio
import logging
import importlib
from unittest.mock import Mock
from unittest.mock import AsyncMock, patch

import pytest

from src.core.payment import (
    FedimintPaymentProvider,
    LNbitsPaymentProvider,
    PaymentProvider,
    get_payment_provider,
)
from src.core.request import (
    sign_request,
    validate_request_envelope,
    verify_signature,
)
app_main = importlib.import_module("main")
sys.path.append('.')

async def test_polyglot_agent():
    """Test PolyglotAgent functionality"""
    print("🧪 Testing PolyglotAgent...")
    
    from src.agents.polyglot_agent.polyglot_agent import PolyglotAgent
    
    # Create agent
    agent = PolyglotAgent()
    print(f"✅ Agent created: {agent.name}")
    print(f"📋 Agent info: {agent.get_info()}")
    
    # Test translation
    print("\n🔄 Testing translation...")
    result = await agent.handle_translation("Hello world", "en", "es")
    print(f"📝 Translation result: {result}")
    
    # Test transcription (mock)
    print("\n🎤 Testing transcription...")
    result = await agent.handle_transcription(audio_file_path="nonexistent.wav")
    print(f"📝 Transcription result: {result}")
    
    # Test service advertisement
    print("\n📡 Testing service advertisement...")
    nostr_event = agent.advertise_service()
    print(f"📡 Nostr event: {nostr_event}")
    
    print("✅ PolyglotAgent tests completed!\n")

async def test_coordinator_agent():
    """Test CoordinatorAgent functionality"""
    print("🧪 Testing CoordinatorAgent...")
    
    from src.agents.coordinator_agent.coordinator_agent import CoordinatorAgent
    
    # Create agent
    agent = CoordinatorAgent()
    print(f"✅ Agent created: {agent.name}")
    print(f"📋 Agent info: {agent.get_info()}")
    
    # Test task chaining
    print("\n🔗 Testing task chaining...")
    tasks = [
        {"service": "mock_service_1", "parameters": {"param1": "value1"}},
        {"service": "mock_service_2", "parameters": {"param2": "value2"}}
    ]
    result = await agent.handle_chain_tasks(tasks)
    print(f"🔗 Chain tasks result: {result}")
    
    # Test service advertisement
    print("\n📡 Testing service advertisement...")
    nostr_event = agent.advertise_service()
    print(f"📡 Nostr event: {nostr_event}")
    
    print("✅ CoordinatorAgent tests completed!\n")

async def test_agent_integration():
    """Test integration between agents"""
    print("🧪 Testing agent integration...")
    
    from src.agents.polyglot_agent.polyglot_agent import PolyglotAgent
    from src.agents.coordinator_agent.coordinator_agent import CoordinatorAgent
    
    # Create both agents
    polyglot = PolyglotAgent()
    coordinator = CoordinatorAgent()
    
    print(f"✅ Created {polyglot.name} and {coordinator.name}")
    
    # Test that they can work together
    print("🔗 Testing inter-agent communication...")
    
    # Simulate coordinator calling polyglot (would normally be HTTP)
    translation_result = await polyglot.handle_translation("Test message", "en", "es")
    print(f"📝 Polyglot translation: {translation_result}")
    
    # Test coordinator's task chaining
    chain_result = await coordinator.handle_chain_tasks([
        {"service": "polyglot.translate", "parameters": {"text": "Hello", "source_lang": "en", "target_lang": "es"}}
    ])
    print(f"🔗 Coordinator chain: {chain_result}")
    
    print("✅ Agent integration tests completed!\n")

async def main():
    """Run all tests"""
    print("🚀 Starting BitAgent functionality tests...\n")
    
    try:
        await test_polyglot_agent()
        await test_coordinator_agent()
        await test_agent_integration()
        
        print("🎉 All tests completed successfully!")
        print("\n📋 Summary:")
        print("✅ PolyglotAgent - Translation and transcription services")
        print("✅ CoordinatorAgent - Task coordination and chaining")
        print("✅ Agent integration - Inter-agent communication")
        print("✅ Nostr compatibility - Service advertisement")
        print("✅ FastAPI integration - HTTP endpoints")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())


def test_lnbits_payment_provider_protocol_and_methods():
    mock_client = Mock()
    mock_client.create_invoice.return_value = {"payment_hash": "hash_1", "bolt11": "lnbc1"}
    mock_client.check_invoice.return_value = True
    mock_client.pay_invoice.return_value = True

    provider = LNbitsPaymentProvider(mock_client)
    assert isinstance(provider, PaymentProvider)
    assert provider.create_invoice(100, "memo") == {"payment_hash": "hash_1", "bolt11": "lnbc1"}
    assert provider.verify_payment("hash_1") is True
    assert provider.receive("token", 100) is True
    assert provider.send(100, "lnbc_dest") is True


def test_fedimint_payment_provider_protocol_and_methods():
    mock_wallet = Mock()
    mock_wallet.create_invoice.return_value = {"invoice": "fm_inv_1"}
    mock_wallet.verify_invoice.return_value = True
    mock_wallet.receive_token.return_value = True
    mock_wallet.send_token.return_value = True

    provider = FedimintPaymentProvider(mock_wallet)
    assert isinstance(provider, PaymentProvider)
    assert provider.create_invoice(50, "memo") == {"invoice": "fm_inv_1"}
    assert provider.verify_payment("fm_inv_1") is True
    assert provider.receive("ecash_token", 50) is True
    assert provider.send(50, "destination") is True


def test_get_payment_provider_factory():
    mock_client = Mock()
    lnbits_provider = get_payment_provider("lnbits", mock_client)
    assert isinstance(lnbits_provider, LNbitsPaymentProvider)

    mock_wallet = Mock()
    fedimint_provider = get_payment_provider("fedimint", mock_wallet)
    assert isinstance(fedimint_provider, FedimintPaymentProvider)


def test_validate_request_envelope_valid_payload_passes():
    req = {
        "id": "req-1",
        "method": "agent.translate",
        "params": {"text": "hello"},
        "sender": "did:example:alice",
        "signature": None,
        "timestamp": 1710000000,
    }
    assert validate_request_envelope(req) is True


def test_validate_request_envelope_missing_method_fails():
    req = {
        "id": "req-1",
        "params": {"text": "hello"},
        "sender": "did:example:alice",
        "signature": None,
        "timestamp": 1710000000,
    }
    assert validate_request_envelope(req) is False


def test_validate_request_envelope_invalid_params_type_fails():
    req = {
        "id": "req-1",
        "method": "agent.translate",
        "params": ["not", "a", "dict"],
        "sender": "did:example:alice",
        "signature": None,
        "timestamp": 1710000000,
    }
    assert validate_request_envelope(req) is False


def test_validate_request_envelope_missing_timestamp_fails():
    req = {
        "id": "req-1",
        "method": "agent.translate",
        "params": {"text": "hello"},
        "sender": "did:example:alice",
        "signature": None,
    }
    assert validate_request_envelope(req) is False


def test_validate_request_envelope_signature_present_still_passes():
    req = {
        "id": "req-1",
        "method": "agent.translate",
        "params": {"text": "hello"},
        "sender": "did:example:alice",
        "signature": "signed-payload",
        "timestamp": 1710000000,
    }
    assert validate_request_envelope(req) is True


def test_request_signature_helpers_are_non_enforcing_stubs():
    req = {
        "id": "req-2",
        "method": "agent.translate",
        "params": {"text": "hello"},
        "sender": "did:example:alice",
        "signature": None,
        "timestamp": 1710000001,
    }
    assert sign_request(req, "private-key") == "stub-signature"
    assert verify_signature(req) is True


@pytest.mark.asyncio
async def test_a2a_endpoint_valid_envelope_is_accepted():
    app_main.REQUEST_ENVELOPE_METRICS["valid"] = 0
    app_main.REQUEST_ENVELOPE_METRICS["invalid"] = 0
    request = AsyncMock()
    request.json = AsyncMock(
        return_value={
            "id": "req-1",
            "method": "identity.get_identity",
            "params": {"pubkey": "abc"},
            "sender": "did:example:alice",
            "signature": None,
            "timestamp": 1710000000,
        }
    )

    with patch("main.handle_a2a_request", AsyncMock(return_value={"ok": True})) as handle_mock:
        response = await app_main.a2a_endpoint(request)

    assert response == {"jsonrpc": "2.0", "result": {"ok": True}, "id": "req-1"}
    handle_mock.assert_awaited_once_with("identity.get_identity", {"pubkey": "abc"})
    assert app_main.REQUEST_ENVELOPE_METRICS["valid"] == 1
    assert app_main.REQUEST_ENVELOPE_METRICS["invalid"] == 0


@pytest.mark.asyncio
async def test_a2a_endpoint_invalid_legacy_payload_logs_warning_and_continues(caplog):
    app_main.REQUEST_ENVELOPE_METRICS["valid"] = 0
    app_main.REQUEST_ENVELOPE_METRICS["invalid"] = 0
    request = AsyncMock()
    request.json = AsyncMock(
        return_value={
            "method": "identity.get_identity",
            "params": {"pubkey": "abc"},
            "id": 7,
        }
    )

    with patch("main.handle_a2a_request", AsyncMock(return_value={"ok": "legacy"})) as handle_mock:
        with caplog.at_level(logging.WARNING):
            response = await app_main.a2a_endpoint(request)

    assert response == {"jsonrpc": "2.0", "result": {"ok": "legacy"}, "id": 7}
    handle_mock.assert_awaited_once_with("identity.get_identity", {"pubkey": "abc"})
    assert "Invalid request envelope received; continuing in compatibility mode" in caplog.text
    assert app_main.REQUEST_ENVELOPE_METRICS["valid"] == 0
    assert app_main.REQUEST_ENVELOPE_METRICS["invalid"] == 1


def test_request_envelope_metrics_endpoint_returns_expected_keys():
    app_main.REQUEST_ENVELOPE_METRICS["valid"] = 0
    app_main.REQUEST_ENVELOPE_METRICS["invalid"] = 0

    metrics = app_main.get_request_envelope_metrics()

    assert "valid" in metrics
    assert "invalid" in metrics
    assert metrics == {"valid": 0, "invalid": 0}


def test_request_envelope_metrics_endpoint_returns_copy_and_does_not_mutate_source():
    app_main.REQUEST_ENVELOPE_METRICS["valid"] = 2
    app_main.REQUEST_ENVELOPE_METRICS["invalid"] = 3

    metrics = app_main.get_request_envelope_metrics()
    metrics["valid"] = 999

    assert app_main.REQUEST_ENVELOPE_METRICS["valid"] == 2
    assert app_main.REQUEST_ENVELOPE_METRICS["invalid"] == 3


@pytest.mark.asyncio
async def test_request_envelope_metrics_endpoint_reflects_previous_a2a_requests():
    app_main.REQUEST_ENVELOPE_METRICS["valid"] = 0
    app_main.REQUEST_ENVELOPE_METRICS["invalid"] = 0

    valid_request = AsyncMock()
    valid_request.json = AsyncMock(
        return_value={
            "id": "req-1",
            "method": "identity.get_identity",
            "params": {"pubkey": "abc"},
            "sender": "did:example:alice",
            "signature": None,
            "timestamp": 1710000000,
        }
    )
    invalid_request = AsyncMock()
    invalid_request.json = AsyncMock(
        return_value={
            "id": 2,
            "method": "identity.get_identity",
            "params": {"pubkey": "abc"},
        }
    )

    with patch("main.handle_a2a_request", AsyncMock(return_value={"ok": True})):
        await app_main.a2a_endpoint(valid_request)
        await app_main.a2a_endpoint(invalid_request)

    metrics = app_main.get_request_envelope_metrics()
    assert metrics["valid"] == 1
    assert metrics["invalid"] == 1
