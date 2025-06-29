# src/agents/polyglot_agent/polyglot_agent.py

from bitagent.core.agent import Agent
from bitagent.core.message import Message

class PolyglotAgent(Agent):
    """
    An AI-to-AI translation and transcription agent.
    Provides language services for a small Bitcoin Lightning payment.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = "polyglot-agent"
        self.description = "Translate or transcribe input text/audio between languages."
        self.supported_languages = ["en", "es", "fr", "de", "zh", "ar", "hi", "ru", "pt", "ja"]
        self.services = {
            "translate": "Translate text from one language to another",
            "transcribe": "Transcribe speech to text (audio)"
        }

    def list_services(self):
        return list(self.services.keys())

    def get_info(self):
        return {
            "name": self.name,
            "description": self.description,
            "supported_languages": self.supported_languages,
            "services": self.services
        }

    async def handle_request(self, message: Message):
        return {
            "error": "Direct handling not supported here. Use logic in __init__.py"
        }
