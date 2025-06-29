# src/agents/coordinator_agent/coordinator_agent.py

from bitagent.core.agent import Agent
from bitagent.core.message import Message

class CoordinatorAgent(Agent):
    """
    Orchestrates multi-step AI tasks by calling other agents (e.g. translation, transcription).
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = "coordinator-agent"
        self.description = "Routes complex tasks across multiple AI agents."
        self.services = {
            "translate_audio": "Transcribes then translates audio",
            "chain_tasks": "Chain any services from other BitAgent agents"
        }

    def list_services(self):
        return list(self.services.keys())

    def get_info(self):
        return {
            "name": self.name,
            "description": self.description,
            "services": self.services
        }

    async def handle_request(self, message: Message):
        return {
            "note": "Use the orchestrator endpoint in __init__.py"
        }
