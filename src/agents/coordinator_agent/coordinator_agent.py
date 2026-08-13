# src/agents/coordinator_agent/coordinator_agent.py

import logging

from src.agents.base_agent import BaseAgent
from src.payments import pricing_for

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
        logging.info(f"CoordinatorAgent initialized with DID: {self.id}")

    @property
    def price_sats(self) -> dict:
        """Prices from the shared catalog — the single source of truth."""
        return {
            key.split(".", 1)[1]: value for key, value in pricing_for("coordinator").items()
        }

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
        """Run a PolyglotAgent step as part of an already-paid chain."""
        from src.agents.polyglot_agent.polyglot_agent import PolyglotAgent

        polyglot = PolyglotAgent()
        try:
            if service == "transcribe":
                return await polyglot.handle_transcription(
                    audio_file_path=parameters.get("audio_file_path"),
                    audio_data=parameters.get("audio_data"),
                )
            if service == "translate":
                return await polyglot.handle_translation(
                    parameters.get("text", ""),
                    parameters.get("source_lang", "auto"),
                    parameters.get("target_lang", "en"),
                )
            return {"error": f"Unknown service: {service}"}
        except Exception as e:
            logging.error("PolyglotAgent step '%s' failed: %s", service, e)
            return {"error": f"Service call failed: {e}"}

    async def _call_service(self, service: str, parameters: dict):
        """Run one chain step.

        Steps execute in-process against the same agents this node already
        serves, because the caller has paid the coordinator for the whole chain.
        This previously returned the literal string "Mock result for {service}"
        for every step, so chain_tasks produced no real work at all.
        """
        from agent_logic import METHOD_SERVICES, dispatch_service

        if service not in METHOD_SERVICES:
            return {
                "error": (
                    f"Unknown service '{service}'. Available: "
                    f"{', '.join(sorted(METHOD_SERVICES))}"
                )
            }
        try:
            result = await dispatch_service(service, parameters)
        except Exception as e:
            logging.error("Chain step '%s' failed: %s", service, e)
            return {"error": f"Service call failed: {e}"}
        return {"service": service, "status": "completed", "result": result}

    def advertise_service(self, pubkey: str | None = None):
        """Build the Nostr announcement for this agent's services.

        ``pubkey`` should be the node's real discovery key; it used to be a
        fabricated npub from ``generate_mock_pubkey()``.
        """
        nostr_event = {
            "kind": 30078,
            "pubkey": pubkey or "",
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
