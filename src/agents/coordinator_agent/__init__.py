# src/agents/coordinator_agent/__init__.py

import sys
import os
import tempfile
import logging

# Add the project root to the path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from fastapi import APIRouter, File, UploadFile, HTTPException, Request
from src.agents.coordinator_agent.coordinator_agent import CoordinatorAgent

# Create agent instance
agent = CoordinatorAgent()

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

@router.post("/translate_audio")
async def translate_audio(audio: UploadFile = File(...), target_language: str = "en"):
    """
    Accepts an audio file, transcribes it via PolyglotAgent, then translates it.
    Returns both the transcription and translated text.
    """
    if not audio:
        raise HTTPException(status_code=400, detail="Missing 'audio' file")

    try:
        # Save the uploaded audio temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_audio:
            temp_audio.write(await audio.read())
            audio_path = temp_audio.name

        try:
            # Use agent's service processing
            result = await agent.handle_translate_audio(
                audio_file_path=audio_path,
                target_language=target_language
            )
            
            if "error" in result:
                raise HTTPException(status_code=500, detail=result["error"])
            
            return result
        finally:
            # Clean up temp file
            try:
                os.unlink(audio_path)
            except:
                pass

    except Exception as e:
        logging.error(f"Translate audio error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/chain_tasks")
async def chain_tasks(request: Request):
    """
    Chain multiple tasks together.
    Expects JSON with 'tasks' array containing service calls.
    """
    try:
        data = await request.json()
        
        if "tasks" not in data:
            raise HTTPException(status_code=400, detail="Missing 'tasks' parameter")
        
        # Use agent's service processing
        result = await agent.handle_chain_tasks(data["tasks"])
        
        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])
        
        return result
    except Exception as e:
        logging.error(f"Chain tasks error: {e}")
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

        if method == "coordinator.translate_audio":
            audio_data = params.get("audio_data")
            target_language = params.get("target_language", "en")
            
            if not audio_data:
                return {"error": "Missing 'audio_data' parameter"}
            
            result = await agent.handle_translate_audio(
                audio_data=audio_data,
                target_language=target_language
            )
            return result
            
        elif method == "coordinator.chain_tasks":
            tasks = params.get("tasks", [])
            
            if not tasks:
                return {"error": "Missing 'tasks' parameter"}
            
            result = await agent.handle_chain_tasks(tasks)
            return result
            
        else:
            return {
                "error": f"Unsupported method '{method}'. Use 'coordinator.translate_audio' or 'coordinator.chain_tasks'."
            }

    except Exception as e:
        logging.error(f"Error in handle_a2a_request: {e}")
        return {"error": str(e)}
