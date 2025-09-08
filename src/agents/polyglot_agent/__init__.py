# src/agents/polyglot_agent/__init__.py

import json
import sys
import os
import tempfile
import logging

# Add the project root to the path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from fastapi import APIRouter, HTTPException, Request, File, UploadFile
from src.agents.polyglot_agent.polyglot_agent import PolyglotAgent

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
async def translate(request: Request):
    """
    Translates text from one language to another.
    Requires 'text', 'source_lang', and 'target_lang' in the request body.
    """
    try:
        data = await request.json()
        text = data["text"]
        source = data.get("source_lang", "auto")
        target = data.get("target_lang", "en")
    except KeyError:
        raise HTTPException(status_code=400, detail="Missing 'text' parameter")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {str(e)}")

    try:
        result = await agent.handle_translation(text, source, target)
        
        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])
        
        return result
    except Exception as e:
        logging.error(f"Translation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/transcribe")
async def transcribe(audio: UploadFile = File(...)):
    """
    Transcribes an uploaded audio file to text.
    """
    if not audio:
        raise HTTPException(status_code=400, detail="Missing 'audio' file")

    try:
        audio_bytes = await audio.read()
        
        # Save to temporary file
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
            temp_file.write(audio_bytes)
            temp_file_path = temp_file.name

        try:
            result = await agent.handle_transcription(audio_file_path=temp_file_path)
            
            if "error" in result:
                raise HTTPException(status_code=500, detail=result["error"])
            
            return result
        finally:
            # Clean up temp file
            try:
                os.unlink(temp_file_path)
            except:
                pass

    except Exception as e:
        logging.error(f"Transcription error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

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
