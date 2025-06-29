# src/agents/coordinator_agent/__init__.py

import aiohttp
import tempfile
from fastapi import APIRouter, File, UploadFile, HTTPException, Request
from src.agents.coordinator_agent.coordinator_agent import CoordinatorAgent
from bitagent.core.agent_server import agent_route

router = APIRouter()
agent = CoordinatorAgent()

# Replace with actual URLs in production
POLYGLOT_BASE_URL = "http://localhost:8000"

@agent_route(router, "/translate_audio", agent=agent)
async def translate_audio(request: Request, audio: UploadFile = File(...)):
    """
    Accepts an audio file, transcribes it via PolyglotAgent, then translates it.
    Returns both the transcription and translated text.
    """

    # Step 1: Save the uploaded audio temporarily
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_audio:
            temp_audio.write(await audio.read())
            audio_path = temp_audio.name
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save audio: {str(e)}")

    # Step 2: Transcribe audio via PolyglotAgent
    async with aiohttp.ClientSession() as session:
        with open(audio_path, "rb") as f:
            transcribe_data = aiohttp.FormData()
            transcribe_data.add_field("audio", f, filename="audio.wav")

            try:
                async with session.post(f"{POLYGLOT_BASE_URL}/transcribe", data=transcribe_data) as resp:
                    if resp.status != 200:
                        raise HTTPException(status_code=resp.status, detail="Transcription failed")
                    transcription_result = await resp.json()
                    transcript_text = transcription_result["transcription"]
                    language = transcription_result["language"]
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Transcribe error: {str(e)}")

    # Step 3: Translate transcription via PolyglotAgent
    translate_payload = {
        "text": transcript_text,
        "source_lang": language,
        "target_lang": "en"
    }

    try:
        async with session.post(f"{POLYGLOT_BASE_URL}/translate", json=translate_payload) as resp:
            if resp.status != 200:
                raise HTTPException(status_code=resp.status, detail="Translation failed")
            translation_result = await resp.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Translate error: {str(e)}")

    # Step 4: Return both steps
    return {
        "transcription": transcript_text,
        "language": language,
        "translation": translation_result.get("translated")
    }
