# BitAgent Start9 Server Deployment Guide

## Private free mode (current milestone)

The StartOS package in this repository (`manifest.yaml`, `scripts/procedures/`) installs into
**private LAN-only free mode**. This is the first private milestone: the node is not published to
the internet and has nothing at stake. "LAN-only" means reachable from your local network — any
device or person with access to that network can reach it, so it is not the same as private to you.

What the defaults mean:

| Setting | Default | Effect |
|---|---|---|
| Enable Lightning payments | off | Every service is free and labelled free in `/health` and `/services`. No LNbits wallet is needed |
| Enable public Nostr discovery | off | No relay connection, no announcement, no DHT traffic, and no Nostr identity is created at all |
| LNbits URL / Admin API Key | empty | Required **only** if you turn payments on |
| Nostr Private Key | empty | Used **only** if you turn discovery on, where it is required |
| Public URL | empty | Required **only** if you turn discovery on |

Access and exposure:

- **LAN only.** The package deliberately declares no Tor interface for this milestone.
- `ALLOWED_ORIGINS` is empty, so no cross-origin browser request is allowed. The API and `/docs`
  are same-origin and unaffected.

Turning something on is an explicit, complete act:

- Payments on with LNbits fields empty → the node **refuses to start**. It never comes up serving
  paid services for free.
- Discovery on without a persistent 64-hex Nostr key, or without a public URL that is not
  localhost → the node **refuses to start**, before it opens any connection. It does not fall back
  to a throwaway identity.

**Do not enter real credentials during this milestone.** No LNbits key, no funded wallet, no Nostr
key you use elsewhere. Leave both switches off and treat the node as a private test surface.

### Required install smoke-test gate (not yet done)

The application side of private free mode is implemented and tested, but **nothing here has been
validated on a real StartOS install** — no `.s9pk` has been built and nothing has been installed.
The two switches are declared as `boolean` config fields and reach the container through
`manifest.yaml` as environment strings, and the exact literal StartOS renders is what decides
behaviour. Confirm all of this on the first install, before trusting the defaults:

1. With both switches off, `PAYMENTS_ENABLED` and `NOSTR_DISCOVERY_ENABLED` inside the service are
   the literal string `false`. Read them from the service's own logs in the StartOS UI, or from a
   shell attached to the service through StartOS (`start-cli package attach`/service shell) — this
   package is operated through StartOS, not through Docker directly.
2. With a switch on, the value is the literal `true`.
3. The startup log contains `Public discovery is disabled` exactly once, and no
   `Nostr broadcast scheduled` line.
4. `/health` reports `"payments": "disabled"`.

How the code behaves if a rendering surprises us:

- `NOSTR_DISCOVERY_ENABLED` set to anything unrecognised → discovery stays **disabled** and a
  warning is logged. Safe.
- `PAYMENTS_ENABLED` empty or absent while no LNbits credentials are set → the node **refuses to
  start**. Safe, but the node will not come up, so check 1 above rather than discovering it here.
- `PAYMENTS_ENABLED` unrecognised → treated as off, i.e. free service. This is the one case that
  fails quietly in the wrong direction for a paid node, which is why check 2 matters before
  payments are ever enabled.

The rest of this document is older material about building and running on Start9; it describes
`start9_server.py`, which still uses the legacy wallet and does not enforce single-use payments.

## 🚀 **Deploying to Start9 Server**

### **1. Prepare Your Start9 Server**

First, ensure your Start9 server has the necessary services:

```bash
# Install required services on Start9
# - LNbits (for Lightning payments)
# - Fedimint (for ecash)
# - Any other Bitcoin/Lightning services you need
```

### **2. Create Start9 Service Package**

Create a proper Start9 service package structure:

```
bitagent-service/
├── manifest.yaml
├── docker-compose.yaml
├── Dockerfile
├── scripts/
│   ├── install.sh
│   └── start.sh
└── data/
    └── .env.template
```

### **3. Docker Configuration**

Create `Dockerfile`:
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create data directory
RUN mkdir -p /data

# Expose port
EXPOSE 8000

# Start command
CMD ["python", "start9_server.py"]
```

### **4. Start9 Manifest**

Create `manifest.yaml`:
```yaml
version: "0.0.1"
name: bitagent
title: BitAgent AI Services
description: Decentralized AI agents with Lightning payments
category: Developer Tools
icon: https://raw.githubusercontent.com/your-repo/bitagent/main/icon.png
developer: Your Name
license: MIT
homepage: https://github.com/your-repo/bitagent
support: https://github.com/your-repo/bitagent/issues

services:
  - name: bitagent
    title: BitAgent Server
    description: Main BitAgent service
    image: your-registry/bitagent:latest
    ports:
      - 8000:8000
    volumes:
      - bitagent-data:/data
    environment:
      - LNBITS_URL=${LNBITS_URL}
      - LNBITS_API_KEY=${LNBITS_API_KEY}
      - FEDIMINT_URL=${FEDIMINT_URL}
      - NOSTR_PRIVATE_KEY=${NOSTR_PRIVATE_KEY}
    depends_on:
      - lnbits
      - fedimint

volumes:
  bitagent-data:
```

## 💰 **Payment Collection Setup**

### **1. LNbits Integration**

Create a dedicated LNbits wallet for your agents:

```python
# start9_payment_manager.py
import os
from lnbits_client import LNbitsClient
from agent_wallet import AgentWallet

class Start9PaymentManager:
    def __init__(self):
        # Get LNbits credentials from Start9 environment
        self.lnbits_url = os.getenv("LNBITS_URL")
        self.lnbits_api_key = os.getenv("LNBITS_API_KEY")
        
        if not self.lnbits_url or not self.lnbits_api_key:
            raise ValueError("LNBITS_URL and LNBITS_API_KEY must be set")
        
        self.client = LNbitsClient(self.lnbits_api_key, self.lnbits_url)
        self.wallet = AgentWallet()
        
    def get_agent_balance(self):
        """Get total balance across all agents"""
        return self.wallet.get_balance()
    
    def create_agent_invoice(self, amount_sats, memo, agent_name):
        """Create invoice for specific agent service"""
        return self.wallet.create_invoice(
            amount=amount_sats,
            memo=f"{agent_name}: {memo}"
        )
    
    def check_payment_status(self, payment_hash):
        """Check if payment is completed"""
        return self.wallet.check_invoice(payment_hash)
    
    def get_payment_history(self):
        """Get payment history (if LNbits API supports it)"""
        # This would depend on LNbits API capabilities
        pass
```

### **2. Enhanced Agent with Payment Collection**

Update your agents to use the Start9 payment manager:

```python
# src/agents/start9_agent.py
import os
import logging
from src.agents.base_agent import BaseAgent
from start9_payment_manager import Start9PaymentManager

class Start9Agent(BaseAgent):
    def __init__(self, name, role, **kwargs):
        super().__init__(name, role, **kwargs)
        self.payment_manager = Start9PaymentManager()
        self.start9_node_id = os.getenv("START9_NODE_ID", "unknown")
        
    def create_service_invoice(self, service_name, amount_sats, memo=""):
        """Create invoice for service payment"""
        try:
            invoice = self.payment_manager.create_agent_invoice(
                amount_sats=amount_sats,
                memo=f"{service_name}: {memo}",
                agent_name=self.name
            )
            logging.info(f"Created invoice for {service_name}: {amount_sats} sats")
            return invoice
        except Exception as e:
            logging.error(f"Failed to create invoice: {e}")
            return None
    
    def verify_payment(self, payment_hash):
        """Verify payment completion"""
        return self.payment_manager.check_payment_status(payment_hash)
    
    def get_earnings(self):
        """Get total earnings for this agent"""
        return self.payment_manager.get_agent_balance()
```

### **3. Start9 Server Main File**

Create `start9_server.py`:

```python
#!/usr/bin/env python3
"""
BitAgent Start9 Server
Main server file for Start9 deployment
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

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("🚀 Starting BitAgent on Start9...")
    logger.info(f"📡 Node ID: {os.getenv('START9_NODE_ID', 'unknown')}")
    logger.info(f"💰 LNbits URL: {os.getenv('LNBITS_URL', 'not set')}")
    
    # Initialize agents
    global streamfinder_agent
    streamfinder_agent = StreamfinderAgent()
    
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
        }
    }

@app.get("/wallet/balance")
async def get_wallet_balance():
    """Get total wallet balance across all agents"""
    try:
        from start9_payment_manager import Start9PaymentManager
        payment_manager = Start9PaymentManager()
        balance = payment_manager.get_agent_balance()
        return {
            "balance_sats": balance,
            "node_id": os.getenv("START9_NODE_ID", "unknown")
        }
    except Exception as e:
        logger.error(f"Failed to get balance: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "BitAgent",
        "node_id": os.getenv("START9_NODE_ID", "unknown")
    }

if __name__ == "__main__":
    import uvicorn
    
    # Get configuration from environment
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    
    logger.info(f"🚀 Starting BitAgent server on {host}:{port}")
    uvicorn.run(app, host=host, port=port)
```

## 🔧 **Environment Configuration**

Create `.env` file for Start9:

```bash
# LNbits Configuration
LNBITS_URL=https://your-lnbits-instance.com
LNBITS_API_KEY=your-lnbits-api-key

# Fedimint Configuration (if using)
FEDIMINT_URL=https://your-fedimint-instance.com
FEDIMINT_API_KEY=your-fedimint-api-key

# Nostr Configuration
NOSTR_PRIVATE_KEY=your-nostr-private-key

# Start9 Configuration
START9_NODE_ID=your-start9-node-id
HOST=0.0.0.0
PORT=8000

# Optional: Database
DATABASE_URL=sqlite:///data/bitagent.db
```

## 📊 **Payment Monitoring**

Create a payment monitoring dashboard:

```python
# payment_dashboard.py
from fastapi import FastAPI
from start9_payment_manager import Start9PaymentManager
import asyncio

app = FastAPI(title="BitAgent Payment Dashboard")

@app.get("/payments/summary")
async def payment_summary():
    """Get payment summary for all agents"""
    payment_manager = Start9PaymentManager()
    
    return {
        "total_balance": payment_manager.get_agent_balance(),
        "node_id": os.getenv("START9_NODE_ID"),
        "timestamp": asyncio.get_event_loop().time()
    }

@app.get("/payments/agents")
async def agent_earnings():
    """Get earnings breakdown by agent"""
    # This would track individual agent earnings
    # You'd need to implement agent-specific tracking
    pass
```

## 🚀 **Deployment Steps**

1. **Build and push Docker image:**
   ```bash
   docker build -t your-registry/bitagent:latest .
   docker push your-registry/bitagent:latest
   ```

2. **Install on Start9:**
   - Upload your service package to Start9
   - Configure environment variables
   - Start the service

3. **Configure LNbits:**
   - Set up LNbits on your Start9 server
   - Create dedicated wallet for BitAgent
   - Configure API keys

4. **Test payment flow:**
   ```bash
   # Test creating an invoice
   curl -X POST "http://your-start9-server:8000/polyglot/translate" \
     -H "Content-Type: application/json" \
     -d '{"text": "Hello", "source_lang": "en", "target_lang": "es"}'
   ```

## 💡 **Payment Collection Tips**

1. **Monitor balances regularly** - Set up alerts for low balances
2. **Backup wallet keys** - Ensure you have secure backups
3. **Track agent performance** - Monitor which agents earn the most
4. **Set up automatic withdrawals** - Configure regular sats withdrawal to your main wallet
5. **Implement rate limiting** - Prevent abuse of your services

This setup will allow you to collect sats from users who pay for your AI agent services while running everything on your Start9 server!
