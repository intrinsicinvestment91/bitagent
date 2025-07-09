# run.py

import uvicorn
import logging
from fastapi import FastAPI, Request
from src.agents.streamfinder import agent_logic


app = FastAPI()
logging.basicConfig(level=logging.INFO)

@app.post("/a2a")
async def handle_a2a(request: Request):
    """Initial request handler: returns LN invoice."""
    return await agent_logic.handle_a2a_request(request)

@app.post("/confirm")
async def confirm_payment(req: Request):
    """
    Triggered after payment. Client must POST:
    {
        "payment_hash": "...",
        "query": "Movie title"
    }
    """
    data = await req.json()
    payment_hash = data.get("payment_hash")
    query = data.get("query")

    if not payment_hash or not query:
        return {"error": "Missing 'payment_hash' or 'query'"}

    return await agent_logic.handle_payment_confirmation(payment_hash, query)

if __name__ == "__main__":
    uvicorn.run("src.agents.streamfinder.run:app", host="0.0.0.0", port=8000, reload=True)
