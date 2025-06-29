# src/agents/polyglot_agent/__init__.py

import json
from bitagent.core.payment import require_payment
from bitagent.core.agent_server import agent_route
from fastapi import APIRouter, HTTPException, Request
from src.agents.polyglot_agent.polyglot_agent import PolyglotAgent

# External dependencies (ensure these are installed in your venv)
from deep_translator import GoogleTranslator
import whisper

router = APIRouter()
agent = PolyglotAgent()

# Load Whisper model once
model = whisper.load_model("base")


@agent_route(router, "/translate", agent=agent)
@require_payment(min_sats=100)
async def translate(request: Request):
    """
    Translates text from one language to another.
    Requires 'text', 'source_lang', and 'target_lang' in the request body.
    """
    data = await request.json()

    try:
        text = data["text"]
        source = data["source_lang"]
        target = data["target_lang"]
    except KeyError:
        raise HTTPException(status_code=400, detail="Missing one of: text, source_lang, target_lang")

    try:
        translated = GoogleTranslator(source=source, target=target).translate(text)
        return {
            "input": text,
            "from": source,
            "to": target,
            "translated": translated
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@agent_route(router, "/transcribe", agent=agent)
@require_payment(min_sats=250)
async def transcribe(request: Request):
    """
    Transcribes an uploaded audio file to text using OpenAI's Whisper.
    """
    form = await request.form()
    file = form.get("audio")

    if not file:
        raise HTTPException(status_code=400, detail="Missing 'audio' file in form data")

    audio_bytes = await file.read()

    try:
        with open("temp_audio.wav", "wb") as f:
            f.write(audio_bytes)

        result = model.transcribe("temp_audio.wav")
        return {
            "language": result.get("language"),
            "transcription": result.get("text")
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
