# src/agents/polyglot_agent/__init__.py

import json
import sys
import os
import tempfile
import logging

# Add the project root to the path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from fastapi import APIRouter, HTTPException, Request, File, UploadFile, Depends
from src.agents.polyglot_agent.polyglot_agent import PolyglotAgent
from src.security.secure_endpoints import (
    require_authentication, 
    require_payment, 
    TranslationRequest, 
    TranscriptionRequest,
    validate_file_upload,
    sanitize_input
)

# Create agent instance
agent = PolyglotAgent()

# Create router
router = APIRouter()

@router.get("/info")
async def get_agent_info():
    """Get agent information."""
    return agent.get_info()

@router.get("/services")
async def get_services():
    """Get available services."""
    return {
        "services": agent.list_services(),
        "pricing": agent.get_price()
    }

@router.post("/translate")
@require_authentication(["read", "write"])
@require_payment(min_sats=100, service_name="translation")
async def translate(request: Request, translation_request: TranslationRequest):
    """
    Translates text from one language to another.
    Requires authentication and payment.
    """
    try:
        # Sanitize input
        text = sanitize_input(translation_request.text)
        source = sanitize_input(translation_request.source_lang)
        target = sanitize_input(translation_request.target_lang)
        
        # Log the request
        agent_id = getattr(request.state, 'agent_id', 'unknown')
        logging.info(f"Translation request from agent {agent_id}: {source} -> {target}")
        
        result = await agent.handle_translation(text, source, target)
        
        if "error" in result:
            logging.error(f"Translation error: {result['error']}")
            raise HTTPException(status_code=500, detail=result["error"])
        
        return result
    except Exception as e:
        logging.error(f"Translation error: {e}")
        raise HTTPException(status_code=500, detail="Translation service error")

@router.post("/transcribe")
@require_authentication(["read", "write"])
@require_payment(min_sats=250, service_name="transcription")
async def transcribe(
    request: Request,
    audio: UploadFile = File(...),
    transcription_request: TranscriptionRequest = Depends()
):
    """
    Transcribes an uploaded audio file to text.
    Requires authentication and payment.
    """
    try:
        # Validate file upload
        audio = validate_file_upload(audio, max_size=50 * 1024 * 1024)  # 50MB limit
        
        # Log the request
        agent_id = getattr(request.state, 'agent_id', 'unknown')
        logging.info(f"Transcription request from agent {agent_id}: {audio.filename}")
        
        audio_bytes = await audio.read()
        
        # Save to temporary file
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
            temp_file.write(audio_bytes)
            temp_file_path = temp_file.name

        try:
            result = await agent.handle_transcription(audio_file_path=temp_file_path)
            
            if "error" in result:
                logging.error(f"Transcription error: {result['error']}")
                raise HTTPException(status_code=500, detail=result["error"])
            
            return result
        finally:
            # Clean up temp file
            try:
                os.unlink(temp_file_path)
            except:
                pass

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Transcription error: {e}")
        raise HTTPException(status_code=500, detail="Transcription service error")

# A2A compatible endpoints (like StreamfinderAgent)
@router.post("/a2a")
async def handle_a2a_request(request: Request):
    """
    A2A compatible endpoint for agent-to-agent communication.
    """
    try:
        body = await request.json()
        logging.info(f"Received A2A request: {body}")

        method = body.get("method")
        params = body.get("params", {})

        if method == "polyglot.translate":
            text = params.get("text")
            source_lang = params.get("source_lang", "auto")
            target_lang = params.get("target_lang", "en")
            
            if not text:
                return {"error": "Missing 'text' parameter"}
            
            result = await agent.handle_translation(text, source_lang, target_lang)
            return result
            
        elif method == "polyglot.transcribe":
            audio_data = params.get("audio_data")
            if not audio_data:
                return {"error": "Missing 'audio_data' parameter"}
            
            result = await agent.handle_transcription(audio_data=audio_data)
            return result
            
        else:
            return {
                "error": f"Unsupported method '{method}'. Use 'polyglot.translate' or 'polyglot.transcribe'."
            }

    except Exception as e:
        logging.error(f"Error in handle_a2a_request: {e}")
        return {"error": str(e)}
