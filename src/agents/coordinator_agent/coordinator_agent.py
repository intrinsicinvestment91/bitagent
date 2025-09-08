# src/agents/coordinator_agent/coordinator_agent.py

import sys
import os
import uuid
import logging
import aiohttp

# Add the project root to the path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from src.agents.base_agent import BaseAgent

class CoordinatorAgent(BaseAgent):
    """
    Orchestrates multi-step AI tasks by calling other agents (e.g. translation, transcription).
    """

    def __init__(self, **kwargs):
        super().__init__(name="CoordinatorAgent", role="task_coordinator")
        self.description = "Routes complex tasks across multiple AI agents."
        self.services = {
            "translate_audio": "Transcribes then translates audio",
            "chain_tasks": "Chain any services from other BitAgent agents"
        }
        self.price_sats = {
            "translate_audio": 350,  # Combined cost of transcribe + translate
            "chain_tasks": 100
        }
        
        # Agent endpoints (would be discovered via Nostr in production)
        self.agent_endpoints = {
            "polyglot": "http://localhost:8000",
            "streamfinder": "http://localhost:8000"  # Same port for demo
        }
        
        logging.info(f"CoordinatorAgent initialized with DID: {self.id}")

    def get_info(self):
        return {
            "name": self.name,
            "description": self.description,
            "did": self.id,
            "services": self.services,
            "pricing": self.price_sats,
            "agent_endpoints": self.agent_endpoints
        }

    def list_services(self):
        return list(self.services.keys())

    def get_price(self, service: str = None):
        """Get price for a specific service or all services."""
        if service:
            return self.price_sats.get(service, 0)
        return self.price_sats

    async def handle_translate_audio(self, audio_file_path: str = None, audio_data: bytes = None, target_language: str = "en"):
        """Handle translate_audio requests."""
        try:
            if not audio_data and not audio_file_path:
                return {"error": "Missing 'audio_data' or 'audio_file_path' parameter"}
            
            # Step 1: Transcribe audio via PolyglotAgent
            transcription_result = await self._call_polyglot_service(
                "transcribe", 
                {"audio_file_path": audio_file_path} if audio_file_path else {"audio_data": audio_data}
            )
            
            if "error" in transcription_result:
                return {"error": f"Transcription failed: {transcription_result['error']}"}
            
            transcript_text = transcription_result["transcription"]
            detected_language = transcription_result["language"]
            
            # Step 2: Translate transcription via PolyglotAgent
            translation_result = await self._call_polyglot_service(
                "translate",
                {
                    "text": transcript_text,
                    "source_lang": detected_language,
                    "target_lang": target_language
                }
            )
            
            if "error" in translation_result:
                return {"error": f"Translation failed: {translation_result['error']}"}
            
            translated_text = translation_result["translated"]
            
            return {
                "transcription": transcript_text,
                "language": detected_language,
                "translation": translated_text,
                "target_language": target_language
            }
            
        except Exception as e:
            logging.error(f"Translate audio failed: {e}")
            return {"error": f"Translate audio failed: {str(e)}"}

    async def handle_chain_tasks(self, tasks: list):
        """Handle task chaining requests."""
        try:
            if not tasks:
                return {"error": "No tasks provided"}
            
            results = []
            for task in tasks:
                service = task.get("service")
                task_params = task.get("parameters", {})
                
                if not service:
                    return {"error": "Task missing 'service' field"}
                
                # Call the appropriate service
                result = await self._call_service(service, task_params)
                results.append({
                    "service": service,
                    "parameters": task_params,
                    "result": result
                })
            
            return {
                "task_chain_results": results,
                "total_tasks": len(tasks)
            }
            
        except Exception as e:
            logging.error(f"Task chaining failed: {e}")
            return {"error": f"Task chaining failed: {str(e)}"}

    async def _call_polyglot_service(self, service: str, parameters: dict):
        """Call PolyglotAgent service."""
        try:
            polyglot_url = self.agent_endpoints["polyglot"]
            
            if service == "transcribe":
                # Handle file upload for transcription
                if "audio_file_path" in parameters:
                    async with aiohttp.ClientSession() as session:
                        with open(parameters["audio_file_path"], "rb") as f:
                            data = aiohttp.FormData()
                            data.add_field("audio", f, filename="audio.wav")
                            
                            async with session.post(f"{polyglot_url}/transcribe", data=data) as resp:
                                if resp.status == 200:
                                    return await resp.json()
                                else:
                                    return {"error": f"Transcription failed: {resp.status}"}
                else:
                    # Handle audio data
                    return {"error": "Audio data handling not implemented yet"}
                    
            elif service == "translate":
                # Handle JSON request for translation
                async with aiohttp.ClientSession() as session:
                    async with session.post(f"{polyglot_url}/translate", json=parameters) as resp:
                        if resp.status == 200:
                            return await resp.json()
                        else:
                            return {"error": f"Translation failed: {resp.status}"}
            else:
                return {"error": f"Unknown service: {service}"}
                
        except Exception as e:
            logging.error(f"Error calling PolyglotAgent: {e}")
            return {"error": f"Service call failed: {str(e)}"}

    async def _call_service(self, service: str, parameters: dict):
        """Call any service (placeholder for service discovery integration)."""
        try:
            # This would integrate with the service discovery system
            # For now, return a mock response
            return {
                "service": service,
                "status": "completed",
                "result": f"Mock result for {service}",
                "parameters": parameters
            }
        except Exception as e:
            return {"error": f"Service call failed: {str(e)}"}

    def advertise_service(self):
        """Advertise services via Nostr (compatible with existing system)."""
        nostr_event = {
            "kind": 30078,
            "pubkey": self.generate_mock_pubkey(),
            "tags": [
                ["t", "service:coordination"],
                ["t", "service:translate_audio"],
                ["price_translate_audio", str(self.price_sats["translate_audio"])],
                ["price_chain_tasks", str(self.price_sats["chain_tasks"])],
            ],
            "content": {
                "service": self.description,
                "did": self.id,
                "services": self.services,
                "pricing": self.price_sats,
                "note": f"offered by {self.name}"
            }
        }
        return nostr_event

    def generate_mock_pubkey(self):
        """Generate a mock Nostr public key."""
        return f"npub1{uuid.uuid4().hex[:20]}"
