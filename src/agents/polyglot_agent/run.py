# src/agents/polyglot_agent/run.py

import uvicorn
from fastapi import FastAPI
from src.agents.polyglot_agent import router as polyglot_router

app = FastAPI(
    title="PolyglotAgent",
    description="Translation and transcription agent using LNbits payment gating.",
    version="0.1.0"
)

# Include routes from __init__.py
app.include_router(polyglot_router)

if __name__ == "__main__":
    uvicorn.run("src.agents.polyglot_agent.run:app", host="0.0.0.0", port=8000, reload=True)
