# src/agents/polyglot_agent/polyglot_agent.py

import sys
import os
import uuid
import logging

# Add the project root to the path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from src.agents.base_agent import BaseAgent

class PolyglotAgent(BaseAgent):
    """
    An AI-to-AI translation and transcription agent.
    Provides language services for a small Bitcoin Lightning payment.
    """

    def __init__(self, **kwargs):
        super().__init__(name="PolyglotAgent", role="translation_service")
        self.description = "Translate or transcribe input text/audio between languages."
        self.supported_languages = ["en", "es", "fr", "de", "zh", "ar", "hi", "ru", "pt", "ja"]
        self.services = {
            "translate": "Translate text from one language to another",
            "transcribe": "Transcribe speech to text (audio)"
        }
        self.price_sats = {
            "translate": 100,
            "transcribe": 250
        }
        logging.info(f"PolyglotAgent initialized with DID: {self.id}")

    def get_info(self):
        return {
            "name": self.name,
            "description": self.description,
            "did": self.id,
            "supported_languages": self.supported_languages,
            "services": self.services,
            "pricing": self.price_sats
        }

    def list_services(self):
        return list(self.services.keys())

    def get_price(self, service: str = None):
        """Get price for a specific service or all services."""
        if service:
            return self.price_sats.get(service, 0)
        return self.price_sats

    async def handle_translation(self, text: str, source_lang: str = "auto", target_lang: str = "en"):
        """Handle translation requests."""
        try:
            if not text:
                return {"error": "Missing 'text' parameter"}
            
            # Try to import deep_translator, fallback to mock if not available
            try:
                from deep_translator import GoogleTranslator
                translator = GoogleTranslator(source=source_lang, target=target_lang)
                translated = translator.translate(text)
            except ImportError:
                # Fallback to mock translation if deep_translator not installed
                translated = f"[MOCK TRANSLATION] {text} (from {source_lang} to {target_lang})"
                logging.warning("deep_translator not installed, using mock translation")
            
            return {
                "input": text,
                "from": source_lang,
                "to": target_lang,
                "translated": translated
            }
            
        except Exception as e:
            logging.error(f"Translation failed: {e}")
            return {"error": f"Translation failed: {str(e)}"}

    async def handle_transcription(self, audio_file_path: str = None, audio_data: bytes = None):
        """Handle transcription requests."""
        try:
            if not audio_data and not audio_file_path:
                return {"error": "Missing 'audio_data' or 'audio_file_path' parameter"}
            
            # Try to import whisper, fallback to mock if not available
            try:
                import whisper
                model = whisper.load_model("base")
                
                if audio_file_path:
                    result = model.transcribe(audio_file_path)
                else:
                    # Handle audio data (save to temp file)
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
            except ImportError:
                # Fallback to mock transcription if whisper not installed
                logging.warning("whisper not installed, using mock transcription")
                return {
                    "language": "en",
                    "transcription": "[MOCK TRANSCRIPTION] This is a mock transcription of the audio file.",
                    "confidence": 0.95
                }
            
        except Exception as e:
            logging.error(f"Transcription failed: {e}")
            return {"error": f"Transcription failed: {str(e)}"}

    def advertise_service(self):
        """Advertise services via Nostr (compatible with existing system)."""
        nostr_event = {
            "kind": 30078,
            "pubkey": self.generate_mock_pubkey(),
            "tags": [
                ["t", "service:translation"],
                ["t", "service:transcription"],
                ["price_translate", str(self.price_sats["translate"])],
                ["price_transcribe", str(self.price_sats["transcribe"])],
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
