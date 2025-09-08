# src/agents/coordinator_agent/__init__.py

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from core.payment import require_payment, log_request
from core.agent_server import agent_route, create_agent_router
from fastapi import APIRouter, File, UploadFile, HTTPException, Request
from src.agents.coordinator_agent.coordinator_agent import CoordinatorAgent

# Create agent instance
agent = CoordinatorAgent()

# Create router with security
router = create_agent_router(agent, prefix="/coordinator")

@agent_route(router, "/translate_audio", agent=agent)
@require_payment(min_sats=350, service_name="translate_audio")  # Combined cost of transcribe + translate
@log_request
async def translate_audio(request: Request, audio: UploadFile = File(...)):
    """
    Accepts an audio file, transcribes it via PolyglotAgent, then translates it.
    Returns both the transcription and translated text.
    """
    if not audio:
        raise HTTPException(status_code=400, detail="Missing 'audio' file")

    try:
        # Save the uploaded audio temporarily
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_audio:
            temp_audio.write(await audio.read())
            audio_path = temp_audio.name

        # Use agent's service processing
        result = await agent.process_service_request(
            "translate_audio",
            {
                "audio_file_path": audio_path,
                "target_language": "en"  # Default to English
            }
        )
        
        # Clean up temp file
        os.unlink(audio_path)
        
        if result["status"] == "error":
            raise HTTPException(status_code=500, detail=result["error"])
        
        return result["result"]

    except Exception as e:
        # Clean up temp file if it exists
        if 'audio_path' in locals():
            try:
                os.unlink(audio_path)
            except:
                pass
        raise HTTPException(status_code=500, detail=str(e))


@agent_route(router, "/chain_tasks", agent=agent)
@require_payment(min_sats=100, service_name="chain_tasks")
@log_request
async def chain_tasks(request: Request):
    """
    Chain multiple tasks together.
    Expects JSON with 'tasks' array containing service calls.
    """
    data = await request.json()
    
    if "tasks" not in data:
        raise HTTPException(status_code=400, detail="Missing 'tasks' parameter")
    
    # Use agent's service processing
    result = await agent.process_service_request(
        "chain_tasks",
        {"tasks": data["tasks"]}
    )
    
    if result["status"] == "error":
        raise HTTPException(status_code=500, detail=result["error"])
    
    return result["result"]
