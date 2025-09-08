#!/usr/bin/env python3
"""
BitAgent Start9 Server
Main server file for Start9 deployment with payment collection
"""

import os
import logging
import asyncio
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

# Import your agents
from src.agents.polyglot_agent import router as polyglot_router
from src.agents.coordinator_agent import router as coordinator_router
from src.agents.streamfinder.streamfinder import StreamfinderAgent
from agent_logic import handle_a2a_request, handle_payment_confirmation
from agent_wallet import AgentWallet

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global agent instances
streamfinder_agent = None
payment_wallet = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("🚀 Starting BitAgent on Start9...")
    logger.info(f"📡 Node ID: {os.getenv('START9_NODE_ID', 'unknown')}")
    logger.info(f"💰 LNbits URL: {os.getenv('LNBITS_URL', 'not set')}")
    
    # Initialize agents and payment system
    global streamfinder_agent, payment_wallet
    streamfinder_agent = StreamfinderAgent()
    
    try:
        payment_wallet = AgentWallet()
        balance = payment_wallet.get_balance()
        logger.info(f"💰 Initial wallet balance: {balance} sats")
    except Exception as e:
        logger.error(f"Failed to initialize payment wallet: {e}")
        payment_wallet = None
    
    yield
    
    # Shutdown
    logger.info("🛑 Shutting down BitAgent...")

# Create FastAPI app
app = FastAPI(
    title="BitAgent Start9 Server",
    description="Decentralized AI agents with Lightning payments",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include agent routers
app.include_router(polyglot_router, prefix="/polyglot", tags=["PolyglotAgent"])
app.include_router(coordinator_router, prefix="/coordinator", tags=["CoordinatorAgent"])

# StreamfinderAgent endpoints (existing)
@app.post("/a2a")
async def streamfinder_a2a(request: Request):
    return await handle_a2a_request(request)

@app.post("/confirm/{payment_hash}")
async def streamfinder_confirm(payment_hash: str, query: str):
    return await handle_payment_confirmation(payment_hash, query)

# Start9 specific endpoints
@app.get("/")
async def root():
    return {
        "service": "BitAgent",
        "version": "1.0.0",
        "node_id": os.getenv("START9_NODE_ID", "unknown"),
        "agents": {
            "polyglot": "/polyglot",
            "coordinator": "/coordinator", 
            "streamfinder": "/a2a"
        },
        "payment_info": {
            "lnbits_url": os.getenv("LNBITS_URL", "not configured"),
            "wallet_balance": "check /wallet/balance"
        },
        "endpoints": {
            "api_docs": "/docs",
            "health": "/health",
            "wallet_balance": "/wallet/balance",
            "payment_history": "/wallet/history"
        }
    }

@app.get("/wallet/balance")
async def get_wallet_balance():
    """Get total wallet balance across all agents"""
    try:
        if not payment_wallet:
            raise HTTPException(status_code=503, detail="Payment wallet not initialized")
        
        balance = payment_wallet.get_balance()
        wallet_id = payment_wallet.get_wallet_id()
        
        return {
            "balance_sats": balance,
            "wallet_id": wallet_id,
            "node_id": os.getenv("START9_NODE_ID", "unknown"),
            "lnbits_url": os.getenv("LNBITS_URL", "not configured")
        }
    except Exception as e:
        logger.error(f"Failed to get balance: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/wallet/history")
async def get_payment_history():
    """Get payment history (placeholder - would need LNbits API support)"""
    return {
        "message": "Payment history not yet implemented",
        "note": "This would require LNbits API support for payment history",
        "current_balance": payment_wallet.get_balance() if payment_wallet else 0
    }

@app.post("/wallet/create-invoice")
async def create_payment_invoice(request: Request):
    """Create a payment invoice for any service"""
    try:
        data = await request.json()
        amount = data.get("amount_sats")
        memo = data.get("memo", "BitAgent Service")
        
        if not amount:
            raise HTTPException(status_code=400, detail="amount_sats is required")
        
        if not payment_wallet:
            raise HTTPException(status_code=503, detail="Payment wallet not initialized")
        
        invoice = payment_wallet.create_invoice(amount, memo)
        
        return {
            "invoice": invoice,
            "amount_sats": amount,
            "memo": memo,
            "node_id": os.getenv("START9_NODE_ID", "unknown")
        }
    except Exception as e:
        logger.error(f"Failed to create invoice: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/agents/status")
async def get_agents_status():
    """Get status of all agents"""
    return {
        "agents": {
            "polyglot": {
                "status": "running",
                "endpoint": "/polyglot",
                "services": ["translate", "transcribe"]
            },
            "coordinator": {
                "status": "running", 
                "endpoint": "/coordinator",
                "services": ["translate_audio", "chain_tasks"]
            },
            "streamfinder": {
                "status": "running",
                "endpoint": "/a2a",
                "services": ["streamfinder.search"]
            }
        },
        "payment_system": {
            "status": "running" if payment_wallet else "error",
            "wallet_balance": payment_wallet.get_balance() if payment_wallet else 0
        }
    }

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "BitAgent",
        "node_id": os.getenv("START9_NODE_ID", "unknown"),
        "payment_system": "healthy" if payment_wallet else "error",
        "agents": ["polyglot", "coordinator", "streamfinder"]
    }

if __name__ == "__main__":
    import uvicorn
    
    # Get configuration from environment
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    
    logger.info(f"🚀 Starting BitAgent server on {host}:{port}")
    logger.info("💰 Payment collection enabled for all agent services")
    logger.info("📡 Agents will collect sats for their services")
    
    uvicorn.run(app, host=host, port=port)
