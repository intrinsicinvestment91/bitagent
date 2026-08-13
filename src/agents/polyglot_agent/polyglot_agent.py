# src/agents/polyglot_agent/polyglot_agent.py

import asyncio
import logging
import os

from src.agents.base_agent import BaseAgent
from src.payments import pricing_for


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
            "transcribe": "Transcribe speech to text (audio)",
        }
        logging.info(f"PolyglotAgent initialized with DID: {self.id}")

    @property
    def price_sats(self) -> dict:
        """Prices read from the shared catalog — the single source of truth."""
        return {key.split(".", 1)[1]: value for key, value in pricing_for("polyglot").items()}

    def get_info(self):
        return {
            "name": self.name,
            "description": self.description,
            "did": self.id,
            "supported_languages": self.supported_languages,
            "services": self.services,
            "pricing": self.price_sats,
        }

    def list_services(self):
        return list(self.services.keys())

    def get_price(self, service: str = None):
        """Get price for a specific service or all services."""
        if service:
            return self.price_sats.get(service, 0)
        return self.price_sats

    async def handle_translation(
        self, text: str, source_lang: str = "auto", target_lang: str = "en"
    ):
        """Handle translation requests."""
        try:
            if not text:
                return {"error": "Missing 'text' parameter"}

            # Translation is a paid service, so a missing backend must be a hard
            # failure. This previously fell back to returning "[MOCK TRANSLATION]
            # <text>", which billed the caller 100 sats for their own input.
            try:
                from deep_translator import GoogleTranslator
            except ImportError as exc:
                logging.error("deep_translator is not installed; translation unavailable")
                raise RuntimeError("Translation backend is not installed") from exc

            translator = GoogleTranslator(source=source_lang, target=target_lang)
            translated = await asyncio.to_thread(translator.translate, text)
            if not translated:
                raise RuntimeError("Translation backend returned an empty result")

            return {"input": text, "from": source_lang, "to": target_lang, "translated": translated}

        except Exception as e:
            logging.error(f"Translation failed: {e}")
            return {"error": f"Translation failed: {str(e)}"}

    async def handle_transcription(self, audio_file_path: str = None, audio_data: bytes = None):
        """Handle transcription requests."""
        try:
            if not audio_data and not audio_file_path:
                return {"error": "Missing 'audio_data' or 'audio_file_path' parameter"}

            # Whisper is excluded from the cloud image (it pulls ~2GB of PyTorch).
            # When it is absent the catalog marks polyglot.transcribe unavailable
            # and the gate refuses the request before reaching here, so this is a
            # backstop. It must never fabricate a transcript: this previously
            # returned "[MOCK TRANSCRIPTION] …" for a 250-sat service.
            try:
                import whisper
            except ImportError as exc:
                logging.error("whisper is not installed; transcription unavailable")
                raise RuntimeError("Transcription backend is not installed") from exc

            model = await asyncio.to_thread(whisper.load_model, "base")

            if audio_file_path:
                result = await asyncio.to_thread(model.transcribe, audio_file_path)
            else:
                import tempfile

                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
                    temp_file.write(audio_data)
                    temp_file_path = temp_file.name
                try:
                    result = await asyncio.to_thread(model.transcribe, temp_file_path)
                finally:
                    os.unlink(temp_file_path)

            return {
                "language": result.get("language"),
                "transcription": result.get("text"),
                "confidence": result.get("confidence", 0.0),
            }

        except Exception as e:
            logging.error(f"Transcription failed: {e}")
            return {"error": f"Transcription failed: {str(e)}"}

    def advertise_service(self, pubkey: str | None = None):
        """Build the Nostr announcement for this agent's services.

        ``pubkey`` should be the node's real discovery key. It used to be filled
        in by ``generate_mock_pubkey()``, which published a fabricated npub that
        nobody could verify or reach.
        """
        nostr_event = {
            "kind": 30078,
            "pubkey": pubkey or "",
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
                "note": f"offered by {self.name}",
            },
        }
        return nostr_event
