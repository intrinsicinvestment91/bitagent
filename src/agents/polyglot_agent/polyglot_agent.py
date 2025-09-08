# src/agents/polyglot_agent/polyglot_agent.py

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from core.agent import Agent, Message

class PolyglotAgent(Agent):
    """
    An AI-to-AI translation and transcription agent.
    Provides language services for a small Bitcoin Lightning payment.
    """

    def __init__(self, **kwargs):
        super().__init__(
            agent_id="polyglot-agent-001",
            name="Polyglot Translation Agent",
            description="Translate or transcribe input text/audio between languages.",
            services=["translate", "transcribe"],
            **kwargs
        )
        self.supported_languages = ["en", "es", "fr", "de", "zh", "ar", "hi", "ru", "pt", "ja"]
        self.service_descriptions = {
            "translate": "Translate text from one language to another",
            "transcribe": "Transcribe speech to text (audio)"
        }

    def get_info(self):
        base_info = super().get_info()
        base_info.update({
            "supported_languages": self.supported_languages,
            "service_descriptions": self.service_descriptions
        })
        return base_info

    async def handle_request(self, message: Message):
        """
        Handle incoming requests for translation or transcription services.
        """
        try:
            payload = message.payload
            service = payload.get("service")
            parameters = payload.get("parameters", {})
            
            if service == "translate":
                return await self._handle_translation(parameters)
            elif service == "transcribe":
                return await self._handle_transcription(parameters)
            else:
                return {
                    "error": f"Unknown service: {service}",
                    "available_services": self.services
                }
                
        except Exception as e:
            return {
                "error": f"Request handling failed: {str(e)}"
            }
    
    async def _handle_translation(self, parameters: dict):
        """Handle translation requests."""
        try:
            text = parameters.get("text", "")
            source_lang = parameters.get("source_lang", "auto")
            target_lang = parameters.get("target_lang", "en")
            
            if not text:
                return {"error": "Missing 'text' parameter"}
            
            # Import here to avoid issues if not installed
            from deep_translator import GoogleTranslator
            
            translator = GoogleTranslator(source=source_lang, target=target_lang)
            translated = translator.translate(text)
            
            return {
                "input": text,
                "from": source_lang,
                "to": target_lang,
                "translated": translated
            }
            
        except Exception as e:
            return {"error": f"Translation failed: {str(e)}"}
    
    async def _handle_transcription(self, parameters: dict):
        """Handle transcription requests."""
        try:
            audio_data = parameters.get("audio_data")
            audio_file_path = parameters.get("audio_file_path")
            
            if not audio_data and not audio_file_path:
                return {"error": "Missing 'audio_data' or 'audio_file_path' parameter"}
            
            # Import here to avoid issues if not installed
            import whisper
            
            # Load model (in production, this would be cached)
            model = whisper.load_model("base")
            
            if audio_file_path:
                result = model.transcribe(audio_file_path)
            else:
                # Handle audio data (would need to save to temp file)
                import tempfile
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
                    temp_file.write(audio_data)
                    temp_file_path = temp_file.name
                
                try:
                    result = model.transcribe(temp_file_path)
                finally:
                    os.unlink(temp_file_path)
            
            return {
                "language": result.get("language"),
                "transcription": result.get("text"),
                "confidence": result.get("confidence", 0.0)
            }
            
        except Exception as e:
            return {"error": f"Transcription failed: {str(e)}"}
