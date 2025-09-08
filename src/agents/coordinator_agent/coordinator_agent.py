# src/agents/coordinator_agent/coordinator_agent.py

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from core.agent import Agent, Message

class CoordinatorAgent(Agent):
    """
    Orchestrates multi-step AI tasks by calling other agents (e.g. translation, transcription).
    """

    def __init__(self, **kwargs):
        super().__init__(
            agent_id="coordinator-agent-001",
            name="Task Coordinator Agent",
            description="Routes complex tasks across multiple AI agents.",
            services=["translate_audio", "chain_tasks"],
            **kwargs
        )
        self.service_descriptions = {
            "translate_audio": "Transcribes then translates audio",
            "chain_tasks": "Chain any services from other BitAgent agents"
        }

    def get_info(self):
        base_info = super().get_info()
        base_info.update({
            "service_descriptions": self.service_descriptions
        })
        return base_info

    async def handle_request(self, message: Message):
        """
        Handle coordination requests.
        """
        try:
            payload = message.payload
            service = payload.get("service")
            parameters = payload.get("parameters", {})
            
            if service == "translate_audio":
                return await self._handle_translate_audio(parameters)
            elif service == "chain_tasks":
                return await self._handle_chain_tasks(parameters)
            else:
                return {
                    "error": f"Unknown service: {service}",
                    "available_services": self.services
                }
                
        except Exception as e:
            return {
                "error": f"Coordination failed: {str(e)}"
            }
    
    async def _handle_translate_audio(self, parameters: dict):
        """Handle translate_audio requests."""
        try:
            audio_data = parameters.get("audio_data")
            audio_file_path = parameters.get("audio_file_path")
            target_language = parameters.get("target_language", "en")
            
            if not audio_data and not audio_file_path:
                return {"error": "Missing 'audio_data' or 'audio_file_path' parameter"}
            
            # Step 1: Transcribe audio
            transcription_result = await self._call_polyglot_service(
                "transcribe", 
                {"audio_file_path": audio_file_path} if audio_file_path else {"audio_data": audio_data}
            )
            
            if transcription_result.get("status") == "error":
                return {"error": f"Transcription failed: {transcription_result['error']}"}
            
            transcript_text = transcription_result["result"]["transcription"]
            detected_language = transcription_result["result"]["language"]
            
            # Step 2: Translate transcription
            translation_result = await self._call_polyglot_service(
                "translate",
                {
                    "text": transcript_text,
                    "source_lang": detected_language,
                    "target_lang": target_language
                }
            )
            
            if translation_result.get("status") == "error":
                return {"error": f"Translation failed: {translation_result['error']}"}
            
            translated_text = translation_result["result"]["translated"]
            
            return {
                "transcription": transcript_text,
                "language": detected_language,
                "translation": translated_text,
                "target_language": target_language
            }
            
        except Exception as e:
            return {"error": f"Translate audio failed: {str(e)}"}
    
    async def _handle_chain_tasks(self, parameters: dict):
        """Handle task chaining requests."""
        try:
            tasks = parameters.get("tasks", [])
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
            return {"error": f"Task chaining failed: {str(e)}"}
    
    async def _call_polyglot_service(self, service: str, parameters: dict):
        """Call PolyglotAgent service."""
        # This would integrate with the actual PolyglotAgent
        # For now, return a mock response
        return {
            "status": "success",
            "result": {
                "transcription": "Mock transcription",
                "language": "en",
                "translated": "Mock translation"
            }
        }
    
    async def _call_service(self, service: str, parameters: dict):
        """Call any service (placeholder for service discovery integration)."""
        # This would integrate with the service discovery system
        # For now, return a mock response
        return {
            "service": service,
            "status": "completed",
            "result": f"Mock result for {service}"
        }
