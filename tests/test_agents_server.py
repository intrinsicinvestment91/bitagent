#!/usr/bin/env python3
"""
Test server to demonstrate the fixed PolyglotAgent and CoordinatorAgent
"""

import sys
import os
sys.path.append('.')

from fastapi import FastAPI
from src.agents.polyglot_agent import router as polyglot_router
from src.agents.coordinator_agent import router as coordinator_router

# Create FastAPI app
app = FastAPI(title="BitAgent Test Server", version="1.0.0")

# Include routers
app.include_router(polyglot_router, prefix="/polyglot", tags=["PolyglotAgent"])
app.include_router(coordinator_router, prefix="/coordinator", tags=["CoordinatorAgent"])

@app.get("/")
async def root():
    return {
        "message": "BitAgent Test Server",
        "agents": {
            "polyglot": "/polyglot",
            "coordinator": "/coordinator"
        },
        "endpoints": {
            "polyglot": {
                "info": "/polyglot/info",
                "services": "/polyglot/services", 
                "translate": "/polyglot/translate",
                "transcribe": "/polyglot/transcribe",
                "a2a": "/polyglot/a2a"
            },
            "coordinator": {
                "info": "/coordinator/info",
                "services": "/coordinator/services",
                "translate_audio": "/coordinator/translate_audio", 
                "chain_tasks": "/coordinator/chain_tasks",
                "a2a": "/coordinator/a2a"
            }
        }
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy", "agents": ["polyglot", "coordinator"]}

if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting BitAgent Test Server...")
    print("📡 PolyglotAgent: http://localhost:8000/polyglot")
    print("🔗 CoordinatorAgent: http://localhost:8000/coordinator")
    print("📋 API Docs: http://localhost:8000/docs")
    uvicorn.run(app, host="0.0.0.0", port=8000)
