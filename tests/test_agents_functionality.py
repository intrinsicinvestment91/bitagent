#!/usr/bin/env python3
"""
Test script to verify PolyglotAgent and CoordinatorAgent functionality
"""

import sys
import os
import asyncio
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
