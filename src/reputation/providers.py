import os
from abc import ABC, abstractmethod
from typing import Any


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class BaseReputationProvider(ABC):
    provider_name = "base"

    @abstractmethod
    def get_score(self, subject_pubkey: str, namespace: str) -> dict[str, Any]:
        """Return provider-specific reputation payload for a subject."""


class Kind30085ReputationProvider(BaseReputationProvider):
    provider_name = "kind_30085"

    def get_score(self, subject_pubkey: str, namespace: str) -> dict[str, Any]:
        # First-PR scaffold: wiring and fallback behavior only.
        # Relay fetch/scoring will be added in follow-up work.
        return {
            "provider": self.provider_name,
            "namespace": namespace,
            "subject_pubkey": subject_pubkey,
            "available": False,
            "reason": "kind_30085_provider_not_implemented",
        }


class MockReputationProvider(BaseReputationProvider):
    provider_name = "mock"

    def get_score(self, subject_pubkey: str, namespace: str) -> dict[str, Any]:
        raw_score = os.getenv("BITAGENT_MOCK_REPUTATION_SCORE", "0.75")
        raw_confidence = os.getenv("BITAGENT_MOCK_REPUTATION_CONFIDENCE", "0.8")
        try:
            score = float(raw_score)
        except ValueError:
            score = 0.75
        try:
            confidence = float(raw_confidence)
        except ValueError:
            confidence = 0.8

        return {
            "provider": self.provider_name,
            "namespace": namespace,
            "subject_pubkey": subject_pubkey,
            "available": True,
            "score": max(0.0, min(score, 1.0)),
            "confidence": max(0.0, min(confidence, 1.0)),
        }


def load_reputation_provider_from_env() -> tuple[BaseReputationProvider | None, str]:
    enabled = _as_bool(os.getenv("BITAGENT_REPUTATION_ENABLED"), default=False)
    if not enabled:
        return None, "payment.reliability"

    namespace = os.getenv("BITAGENT_REPUTATION_NAMESPACE", "payment.reliability")
    provider_name = os.getenv("BITAGENT_REPUTATION_PROVIDER", "kind_30085").strip().lower()

    if provider_name == "kind_30085":
        return Kind30085ReputationProvider(), namespace
    if provider_name == "mock":
        return MockReputationProvider(), namespace

    return None, namespace
