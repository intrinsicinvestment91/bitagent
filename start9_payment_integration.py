#!/usr/bin/env python3
"""
Start9 Payment Integration for BitAgent
Handles payment collection and verification for agent services
"""

import os
import logging
from typing import Optional, Dict, Any
from fastapi import HTTPException, Request
from agent_wallet import AgentWallet

logger = logging.getLogger(__name__)

class Start9PaymentManager:
    """Manages payments for BitAgent services on Start9"""
    
    def __init__(self):
        self.wallet = AgentWallet()
        self.node_id = os.getenv("START9_NODE_ID", "unknown")
        
    def create_service_invoice(self, service_name: str, amount_sats: int, memo: str = "") -> Dict[str, Any]:
        """Create invoice for agent service payment"""
        try:
            full_memo = f"{service_name}: {memo}" if memo else f"{service_name} service"
            
            invoice = self.wallet.create_invoice(amount_sats, full_memo)
            
            if not invoice:
                raise Exception("Failed to create invoice")
            
            logger.info(f"💰 Created invoice for {service_name}: {amount_sats} sats")
            
            return {
                "payment_required": True,
                "amount_sats": amount_sats,
                "payment_request": invoice.get("bolt11") or invoice.get("payment_request"),
                "payment_hash": invoice.get("payment_hash"),
                "memo": full_memo,
                "service": service_name,
                "node_id": self.node_id
            }
            
        except Exception as e:
            logger.error(f"Failed to create invoice for {service_name}: {e}")
            raise HTTPException(status_code=500, detail=f"Payment system error: {str(e)}")
    
    def verify_payment(self, payment_hash: str) -> bool:
        """Verify if payment is completed"""
        try:
            return self.wallet.check_invoice(payment_hash)
        except Exception as e:
            logger.error(f"Failed to verify payment {payment_hash}: {e}")
            return False
    
    def get_balance(self) -> int:
        """Get current wallet balance"""
        try:
            return self.wallet.get_balance()
        except Exception as e:
            logger.error(f"Failed to get balance: {e}")
            return 0
    
    def get_wallet_info(self) -> Dict[str, Any]:
        """Get wallet information"""
        try:
            balance = self.get_balance()
            wallet_id = self.wallet.get_wallet_id()
            
            return {
                "balance_sats": balance,
                "wallet_id": wallet_id,
                "node_id": self.node_id,
                "lnbits_url": os.getenv("LNBITS_URL", "not configured")
            }
        except Exception as e:
            logger.error(f"Failed to get wallet info: {e}")
            return {
                "balance_sats": 0,
                "wallet_id": "unknown",
                "node_id": self.node_id,
                "error": str(e)
            }

def require_payment_for_service(service_name: str, amount_sats: int):
    """Decorator to require payment for agent services"""
    def decorator(func):
        async def wrapper(request: Request, *args, **kwargs):
            payment_manager = Start9PaymentManager()
            
            # Check if payment_hash is provided
            try:
                body = await request.json()
                payment_hash = body.get("payment_hash")
            except:
                payment_hash = None
            
            if payment_hash:
                # Verify payment
                if payment_manager.verify_payment(payment_hash):
                    logger.info(f"✅ Payment verified for {service_name}: {payment_hash}")
                    return await func(request, *args, **kwargs)
                else:
                    logger.warning(f"❌ Payment not verified for {service_name}: {payment_hash}")
                    raise HTTPException(
                        status_code=402, 
                        detail="Payment not yet received or invalid"
                    )
            else:
                # Create invoice for payment
                invoice_data = payment_manager.create_service_invoice(
                    service_name, amount_sats, "Service payment"
                )
                
                logger.info(f"💳 Payment required for {service_name}: {amount_sats} sats")
                raise HTTPException(
                    status_code=402,
                    detail="Payment required",
                    headers={"X-Payment-Required": "true"},
                    extra=invoice_data
                )
        
        return wrapper
    return decorator

# Payment amounts for different services
SERVICE_PRICING = {
    "polyglot.translate": 100,
    "polyglot.transcribe": 250,
    "coordinator.translate_audio": 350,
    "coordinator.chain_tasks": 100,
    "streamfinder.search": 100
}

def get_service_price(service_name: str) -> int:
    """Get price for a specific service"""
    return SERVICE_PRICING.get(service_name, 100)  # Default 100 sats

def create_payment_required_response(service_name: str, amount_sats: int = None) -> Dict[str, Any]:
    """Create a standardized payment required response"""
    if amount_sats is None:
        amount_sats = get_service_price(service_name)
    
    payment_manager = Start9PaymentManager()
    return payment_manager.create_service_invoice(service_name, amount_sats)
