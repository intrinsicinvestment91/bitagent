# src/agents/coordinator_agent/__init__.py

import sys
import os
import tempfile
import logging

# Add the project root to the path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from fastapi import APIRouter, File, UploadFile, HTTPException, Request, Depends
from src.agents.coordinator_agent.coordinator_agent import CoordinatorAgent
from src.security.secure_endpoints import (
    require_authentication, 
    require_payment, 
    TaskChainRequest,
    validate_file_upload,
    sanitize_input
)

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
@require_authentication(["read", "write"])
@require_payment(min_sats=350, service_name="translate_audio")
async def translate_audio(
    request: Request,
    audio: UploadFile = File(...), 
    target_language: str = "en"
):
    """
    Accepts an audio file, transcribes it via PolyglotAgent, then translates it.
    Returns both the transcription and translated text.
    Requires authentication and payment.
    """
    try:
        # Validate file upload
        audio = validate_file_upload(audio, max_size=100 * 1024 * 1024)  # 100MB limit
        
        # Sanitize target language
        target_language = sanitize_input(target_language, max_length=10)
        
        # Log the request
        agent_id = getattr(request.state, 'agent_id', 'unknown')
        logging.info(f"Audio translation request from agent {agent_id}: {audio.filename} -> {target_language}")
        
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
                logging.error(f"Audio translation error: {result['error']}")
                raise HTTPException(status_code=500, detail=result["error"])
            
            return result
        finally:
            # Clean up temp file
            try:
                os.unlink(audio_path)
            except:
                pass

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Translate audio error: {e}")
        raise HTTPException(status_code=500, detail="Audio translation service error")

@router.post("/chain_tasks")
@require_authentication(["read", "write"])
@require_payment(min_sats=100, service_name="chain_tasks")
async def chain_tasks(request: Request, task_request: TaskChainRequest):
    """
    Chain multiple tasks together.
    Requires authentication and payment.
    """
    try:
        # Log the request
        agent_id = getattr(request.state, 'agent_id', 'unknown')
        logging.info(f"Task chaining request from agent {agent_id}: {len(task_request.tasks)} tasks")
        
        # Use agent's service processing
        result = await agent.handle_chain_tasks(task_request.tasks)
        
        if "error" in result:
            logging.error(f"Task chaining error: {result['error']}")
            raise HTTPException(status_code=500, detail=result["error"])
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Chain tasks error: {e}")
        raise HTTPException(status_code=500, detail="Task chaining service error")

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
