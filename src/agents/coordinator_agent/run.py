# src/agents/coordinator_agent/run.py

import uvicorn
from fastapi import FastAPI
from src.agents.coordinator_agent import router as coordinator_router

app = FastAPI(
    title="CoordinatorAgent",
    description="An MCPS-style coordinator that routes audio tasks to PolyglotAgent.",
    version="0.1.0"
)

# Include the router that defines /translate_audio
app.include_router(coordinator_router)

if __name__ == "__main__":
    uvicorn.run("src.agents.coordinator_agent.run:app", host="0.0.0.0", port=8001, reload=True)
