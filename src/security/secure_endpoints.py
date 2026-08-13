"""Request models and input sanitization for the HTTP layer.

This module used to also export ``require_authentication`` and
``require_payment`` decorators. Both were broken in every configuration — the
first called a FastAPI dependency outside dependency injection, the second
imported a module that is not on the import path and passed an invalid kwarg to
``HTTPException`` — and both have been replaced by ``src.payments.gate``.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, UploadFile
from pydantic import BaseModel, field_validator

logger = logging.getLogger(__name__)

MAX_TEXT_LENGTH = 10_000
MAX_TASKS = 10
ALLOWED_AUDIO_TYPES = ("audio/wav", "audio/x-wav", "audio/mp3", "audio/mpeg", "audio/ogg")


class TranslationRequest(BaseModel):
    text: str
    source_lang: str = "auto"
    target_lang: str = "en"
    payment_hash: Optional[str] = None
    ecash_notes: Optional[str] = None

    @field_validator("text")
    @classmethod
    def validate_text(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Text cannot be empty")
        if len(v) > MAX_TEXT_LENGTH:
            raise ValueError(f"Text too long (max {MAX_TEXT_LENGTH} characters)")
        return v.strip()

    @field_validator("source_lang", "target_lang")
    @classmethod
    def validate_language_codes(cls, v: str) -> str:
        if v and len(v) > 10:
            raise ValueError("Language code too long")
        return v.lower()


class TranscriptionRequest(BaseModel):
    payment_hash: Optional[str] = None

    @field_validator("payment_hash")
    @classmethod
    def validate_payment_hash(cls, v: Optional[str]) -> Optional[str]:
        if v and len(v) != 64:
            raise ValueError("Invalid payment hash format")
        return v


class TaskChainRequest(BaseModel):
    tasks: List[Dict[str, Any]]
    payment_hash: Optional[str] = None

    @field_validator("tasks")
    @classmethod
    def validate_tasks(cls, v: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not v:
            raise ValueError("Tasks list cannot be empty")
        if len(v) > MAX_TASKS:
            raise ValueError(f"Too many tasks (max {MAX_TASKS})")
        for task in v:
            if not task.get("service"):
                raise ValueError("Each task must have a service")
            if not task.get("parameters"):
                raise ValueError("Each task must have parameters")
        return v


def validate_file_upload(file: UploadFile, max_size: int = 10 * 1024 * 1024) -> UploadFile:
    """Validate an upload's declared size and content type.

    ``UploadFile.size`` is ``None`` on some Starlette paths, which previously
    raised a TypeError here. An unknown size is not treated as valid — callers
    must still enforce a byte cap after reading.
    """
    if file.size is not None and file.size > max_size:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size: {max_size // (1024 * 1024)}MB",
        )

    if file.content_type not in ALLOWED_AUDIO_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed: {', '.join(ALLOWED_AUDIO_TYPES)}",
        )

    return file


def log_security_event(event_type: str, agent_id: str, details: Dict[str, Any]) -> None:
    """Record a security-relevant event for monitoring."""
    logger.warning("SECURITY_EVENT: %s from agent %s: %s", event_type, agent_id, details)


def sanitize_input(text: str, max_length: int = 1000) -> str:
    """Strip control characters and bound the length of caller-supplied text."""
    if not text:
        return ""
    sanitized = "".join(char for char in text if ord(char) >= 32 or char in "\t\n\r")
    return sanitized[:max_length]
