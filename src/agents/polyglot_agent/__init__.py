import logging
import os
import tempfile

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from src.agents.polyglot_agent.polyglot_agent import PolyglotAgent
from src.payments import Quote, get_service, paid_work, pricing_for, require_payment
from src.security.secure_endpoints import TranslationRequest, sanitize_input

logger = logging.getLogger(__name__)

agent = PolyglotAgent()
router = APIRouter()

#: Audio uploads are read into memory before transcription, so cap them.
MAX_AUDIO_BYTES = 25 * 1024 * 1024


@router.get("/info")
async def get_agent_info():
    return agent.get_info()


@router.get("/services")
async def get_services():
    return {
        "services": agent.list_services(),
        "pricing": pricing_for("polyglot"),
        "details": [
            get_service("polyglot.translate").info(),
            get_service("polyglot.transcribe").info(),
        ],
    }


@router.post("/translate")
async def translate(body: TranslationRequest):
    text = sanitize_input(body.text)
    source = sanitize_input(body.source_lang)
    target = sanitize_input(body.target_lang)

    outcome = await require_payment(
        "polyglot.translate",
        body.payment_hash,
        body.ecash_notes,
        memo=f"Translate: {text[:40]}",
    )
    if isinstance(outcome, Quote):
        return JSONResponse(status_code=outcome.status_code, content=outcome.body)

    async with paid_work(outcome):
        result = await agent.handle_translation(text, source, target)
        if "error" in result:
            raise HTTPException(502, result["error"])
        return result


@router.post("/transcribe")
async def transcribe(
    audio: UploadFile = File(...),
    payment_hash: str | None = Form(default=None),
    ecash_notes: str | None = Form(default=None),
):
    outcome = await require_payment(
        "polyglot.transcribe", payment_hash, ecash_notes, memo="Audio transcription"
    )
    if isinstance(outcome, Quote):
        return JSONResponse(status_code=outcome.status_code, content=outcome.body)

    async with paid_work(outcome):
        audio_bytes = await audio.read()
        if len(audio_bytes) > MAX_AUDIO_BYTES:
            raise HTTPException(413, f"Audio exceeds {MAX_AUDIO_BYTES // (1024 * 1024)} MB limit")

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        try:
            result = await agent.handle_transcription(audio_file_path=tmp_path)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                logger.warning("Could not remove temporary audio file %s", tmp_path)

        if "error" in result:
            raise HTTPException(502, result["error"])
        return result


@router.post("/a2a")
async def a2a(body: dict):
    """A2A twins of /translate and /transcribe — same service ids, same prices."""
    method = body.get("method")
    params = body.get("params") or {}

    if method not in {"polyglot.translate", "polyglot.transcribe"}:
        return {"error": f"Unsupported method '{method}'"}

    if method == "polyglot.translate":
        text = params.get("text")
        if not text:
            return {"error": "Missing 'text'"}
        outcome = await require_payment(
            method,
            params.get("payment_hash"),
            params.get("ecash_notes"),
            memo=f"Translate: {str(text)[:40]}",
        )
        if isinstance(outcome, Quote):
            return JSONResponse(status_code=outcome.status_code, content=outcome.body)
        async with paid_work(outcome):
            return await agent.handle_translation(
                sanitize_input(text),
                params.get("source_lang", "auto"),
                params.get("target_lang", "en"),
            )

    audio_data = params.get("audio_data")
    if not audio_data:
        return {"error": "Missing 'audio_data'"}
    outcome = await require_payment(
        method, params.get("payment_hash"), params.get("ecash_notes"), memo="Audio transcription"
    )
    if isinstance(outcome, Quote):
        return JSONResponse(status_code=outcome.status_code, content=outcome.body)
    async with paid_work(outcome):
        return await agent.handle_transcription(audio_data=audio_data)
