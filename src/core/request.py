"""
Request envelope helpers for agent-to-agent communication.

This module is intentionally non-enforcing scaffolding. It defines a
standardized request envelope shape and placeholder signature helpers that
future packets can integrate into runtime paths.
"""


def validate_request_envelope(req: dict) -> bool:
    """
    Validate a standardized request envelope.

    Expected structure:
    {
        "id": str,
        "method": str,
        "params": dict,
        "sender": str,
        "signature": str | None,
        "timestamp": int
    }
    """
    required_keys = {"id", "method", "params", "sender", "signature", "timestamp"}
    if not isinstance(req, dict):
        return False
    if not required_keys.issubset(req.keys()):
        return False
    if not isinstance(req.get("id"), str) or not req["id"].strip():
        return False
    if not isinstance(req.get("method"), str) or not req["method"].strip():
        return False
    if not isinstance(req.get("params"), dict):
        return False
    if not isinstance(req.get("sender"), str) or not req["sender"].strip():
        return False
    if not isinstance(req.get("timestamp"), int):
        return False
    signature = req.get("signature")
    if signature is not None and not isinstance(signature, str):
        return False
    return True


def sign_request(req: dict, private_key: str) -> str:
    """Placeholder signing helper for future crypto integration."""
    return "stub-signature"


def verify_signature(req: dict) -> bool:
    """Placeholder signature verification helper for future crypto integration."""
    return True
