# src/agents/polyglot_agent/__init__.py

import json
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from core.payment import require_payment, log_request
from core.agent_server import agent_route, create_agent_router
from fastapi import APIRouter, HTTPException, Request, File, UploadFile
from src.agents.polyglot_agent.polyglot_agent import PolyglotAgent

# Create agent instance
agent = PolyglotAgent()

# Create router with security
router = create_agent_router(agent, prefix="/polyglot")

@agent_route(router, "/translate", agent=agent)
@require_payment(min_sats=100, service_name="translation")
@log_request
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

    # Use agent's service processing
    result = await agent.process_service_request(
        "translate",
        {
            "text": text,
            "source_lang": source,
            "target_lang": target
        }
    )
    
    if result["status"] == "error":
        raise HTTPException(status_code=500, detail=result["error"])
    
    return result["result"]


@agent_route(router, "/transcribe", agent=agent)
@require_payment(min_sats=250, service_name="transcription")
@log_request
async def transcribe(request: Request, audio: UploadFile = File(...)):
    """
    Transcribes an uploaded audio file to text using OpenAI's Whisper.
    """
    if not audio:
        raise HTTPException(status_code=400, detail="Missing 'audio' file in form data")

    audio_bytes = await audio.read()

    try:
        # Save to temporary file
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
            temp_file.write(audio_bytes)
            temp_file_path = temp_file.name

        # Use agent's service processing
        result = await agent.process_service_request(
            "transcribe",
            {
                "audio_file_path": temp_file_path
            }
        )
        
        # Clean up temp file
        os.unlink(temp_file_path)
        
        if result["status"] == "error":
            raise HTTPException(status_code=500, detail=result["error"])
        
        return result["result"]

    except Exception as e:
        # Clean up temp file if it exists
        if 'temp_file_path' in locals():
            try:
                os.unlink(temp_file_path)
            except:
                pass
        raise HTTPException(status_code=500, detail=str(e))
