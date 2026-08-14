# src/agents/coordinator_agent/__init__.py
"""CoordinatorAgent HTTP router.

Both paid endpoints here used to be unreachable in every configuration: they
were wrapped in ``@require_authentication`` and ``@require_payment`` from
``src.security.secure_endpoints``, which called a FastAPI dependency outside
dependency injection (TypeError → 401) and imported a module that is not on the
import path (ModuleNotFoundError → 500). They now use the shared payment gate
like every other agent.
"""

import base64
import binascii
import logging
import os
import tempfile

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from src.agents.coordinator_agent.coordinator_agent import CoordinatorAgent
from src.payments import Quote, get_service, paid_work, pricing_for, require_payment
from src.security.secure_endpoints import TaskChainRequest, sanitize_input

logger = logging.getLogger(__name__)

agent = CoordinatorAgent()
router = APIRouter()

MAX_AUDIO_BYTES = 25 * 1024 * 1024


@router.get("/info")
async def get_agent_info():
    """Get agent information."""
    return agent.get_info()


@router.get("/services")
async def get_services():
    return {
        "services": agent.list_services(),
        "pricing": pricing_for("coordinator"),
        "details": [
            get_service("coordinator.translate_audio").info(),
            get_service("coordinator.chain_tasks").info(),
        ],
    }


@router.post("/translate_audio")
async def translate_audio(
    audio: UploadFile = File(...),
    target_language: str = Form(default="en"),
    payment_hash: str | None = Form(default=None),
    ecash_notes: str | None = Form(default=None),
):
    """Transcribe an audio file via PolyglotAgent, then translate the result."""
    outcome = await require_payment(
        "coordinator.translate_audio", payment_hash, ecash_notes, memo="Transcribe and translate"
    )
    if isinstance(outcome, Quote):
        return JSONResponse(status_code=outcome.status_code, content=outcome.body)

    async with paid_work(outcome):
        target_language = sanitize_input(target_language, max_length=10)
        audio_bytes = await audio.read()
        if len(audio_bytes) > MAX_AUDIO_BYTES:
            raise HTTPException(413, f"Audio exceeds {MAX_AUDIO_BYTES // (1024 * 1024)} MB limit")

        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_audio:
            temp_audio.write(audio_bytes)
            audio_path = temp_audio.name

        try:
            result = await agent.handle_translate_audio(
                audio_file_path=audio_path, target_language=target_language
            )
        finally:
            try:
                os.unlink(audio_path)
            except OSError:
                logger.warning("Could not remove temporary audio file %s", audio_path)

        if "error" in result:
            raise HTTPException(502, result["error"])
        return result


@router.post("/chain_tasks")
async def chain_tasks(task_request: TaskChainRequest):
    """Run a chain of services in one paid request."""
    outcome = await require_payment(
        "coordinator.chain_tasks",
        task_request.payment_hash,
        memo=f"Chain of {len(task_request.tasks)} tasks",
    )
    if isinstance(outcome, Quote):
        return JSONResponse(status_code=outcome.status_code, content=outcome.body)

    async with paid_work(outcome):
        result = await agent.handle_chain_tasks(task_request.tasks)
        if "error" in result:
            raise HTTPException(400, result["error"])
        return result


@router.post("/a2a")
async def a2a(body: dict):
    """A2A twins of the two paid routes above — same service ids, same prices."""
    method = body.get("method")
    params = body.get("params") or {}

    if method not in {"coordinator.translate_audio", "coordinator.chain_tasks"}:
        return {
            "error": (
                f"Unsupported method '{method}'. Use 'coordinator.translate_audio' "
                "or 'coordinator.chain_tasks'."
            )
        }

    if method == "coordinator.translate_audio":
        audio_data = params.get("audio_data")
        if not audio_data:
            return {"error": "Missing 'audio_data' parameter"}
        try:
            # A2A carries binary as base64; this path previously handed the raw
            # string to whisper and always failed with "not implemented yet".
            decoded = base64.b64decode(audio_data, validate=True)
        except (binascii.Error, ValueError):
            return {"error": "'audio_data' must be base64-encoded audio"}
        if len(decoded) > MAX_AUDIO_BYTES:
            return {"error": f"Audio exceeds {MAX_AUDIO_BYTES // (1024 * 1024)} MB limit"}

        outcome = await require_payment(
            method,
            params.get("payment_hash"),
            params.get("ecash_notes"),
            memo="Transcribe and translate",
        )
        if isinstance(outcome, Quote):
            return JSONResponse(status_code=outcome.status_code, content=outcome.body)
        async with paid_work(outcome):
            return await agent.handle_translate_audio(
                audio_data=decoded,
                target_language=sanitize_input(params.get("target_language", "en"), max_length=10),
            )

    tasks = params.get("tasks") or []
    if not tasks:
        return {"error": "Missing 'tasks' parameter"}

    outcome = await require_payment(
        method,
        params.get("payment_hash"),
        params.get("ecash_notes"),
        memo=f"Chain of {len(tasks)} tasks",
    )
    if isinstance(outcome, Quote):
        return JSONResponse(status_code=outcome.status_code, content=outcome.body)
    async with paid_work(outcome):
        return await agent.handle_chain_tasks(tasks)
