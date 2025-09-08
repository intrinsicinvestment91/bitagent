"""
Payment decorators and utilities for BitAgent framework.
Provides secure payment integration with escrow and fraud detection.
"""

import functools
import time
import logging
from typing import Callable, Any, Dict, Optional
from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# Import enhanced security components
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from security.authentication import AuthenticationManager
from security.payment_security import PaymentSecurityManager, EscrowStatus
from monitoring.audit_logger import AuditLogger, EventType

# Global instances (in production, these would be dependency injected)
auth_manager = AuthenticationManager()
payment_security = PaymentSecurityManager()
audit_logger = AuditLogger()

security_scheme = HTTPBearer()

def get_current_agent(credentials: HTTPAuthorizationCredentials = Depends(security_scheme)) -> Dict[str, Any]:
    """Extract and validate agent from API key."""
    api_key = credentials.credentials
    payload = auth_manager.verify_api_key(api_key)
    
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    return payload

def require_payment(min_sats: int = 100, service_name: str = None):
    """
    Decorator to require payment before processing a request.
    Integrates with the enhanced payment security system.
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(request: Request, *args, **kwargs):
            start_time = time.time()
            
            try:
                # Extract agent information
                agent_payload = get_current_agent()
                agent_id = agent_payload["agent_id"]
                
                # Get request data
                if hasattr(request, 'json'):
                    request_data = await request.json()
                else:
                    request_data = {}
                
                # Create escrow payment
                service_desc = service_name or func.__name__
                escrow = payment_security.create_escrow_payment(
                    buyer_id=agent_id,
                    seller_id="service_provider",  # Would be determined by service
                    amount_sats=min_sats,
                    service_description=service_desc
                )
                
                # Log payment requirement
                audit_logger.log_event(
                    EventType.PAYMENT,
                    agent_id,
                    "payment_required",
                    {
                        "service": service_desc,
                        "amount_sats": min_sats,
                        "escrow_id": escrow.escrow_id
                    }
                )
                
                # Check if payment is already provided in request
                payment_hash = request_data.get("payment_hash")
                if payment_hash:
                    # Verify payment
                    if payment_security.fund_escrow(escrow.escrow_id, payment_hash):
                        # Payment verified, proceed with service
                        result = await func(request, *args, **kwargs)
                        
                        # Release escrow
                        payment_security.release_escrow(escrow.escrow_id, "Service completed")
                        
                        # Log successful payment
                        audit_logger.log_payment(
                            agent_id, escrow.escrow_id, min_sats, True
                        )
                        
                        return result
                    else:
                        raise HTTPException(status_code=402, detail="Payment verification failed")
                else:
                    # Return payment request
                    return {
                        "payment_required": True,
                        "amount_sats": min_sats,
                        "escrow_id": escrow.escrow_id,
                        "service": service_desc,
                        "message": f"Payment of {min_sats} sats required for {service_desc}"
                    }
                    
            except HTTPException:
                raise
            except Exception as e:
                # Log error
                duration_ms = (time.time() - start_time) * 1000
                audit_logger.log_event(
                    EventType.PAYMENT,
                    "unknown",
                    "payment_error",
                    {"error": str(e)},
                    severity="ERROR",
                    duration_ms=duration_ms
                )
                
                raise HTTPException(status_code=500, detail=f"Payment processing error: {str(e)}")
        
        return wrapper
    return decorator

def require_authentication(permissions: list = None):
    """
    Decorator to require authentication for a request.
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(request: Request, *args, **kwargs):
            try:
                # Extract and validate agent
                agent_payload = get_current_agent()
                agent_id = agent_payload["agent_id"]
                
                # Check permissions
                if permissions:
                    agent_permissions = agent_payload.get("permissions", [])
                    if not any(perm in agent_permissions for perm in permissions):
                        raise HTTPException(
                            status_code=403, 
                            detail=f"Insufficient permissions. Required: {permissions}"
                        )
                
                # Log authentication
                audit_logger.log_authentication(
                    agent_id, "api_key_auth", True
                )
                
                # Add agent info to request state
                request.state.agent_id = agent_id
                request.state.agent_permissions = agent_payload.get("permissions", [])
                
                return await func(request, *args, **kwargs)
                
            except HTTPException:
                raise
            except Exception as e:
                audit_logger.log_authentication(
                    "unknown", "api_key_auth", False
                )
                raise HTTPException(status_code=401, detail="Authentication failed")
        
        return wrapper
    return decorator

def log_request(func: Callable) -> Callable:
    """
    Decorator to log all requests for monitoring and audit purposes.
    """
    @functools.wraps(func)
    async def wrapper(request: Request, *args, **kwargs):
        start_time = time.time()
        
        try:
            # Extract agent info if available
            agent_id = getattr(request.state, 'agent_id', 'anonymous')
            
            # Log request
            audit_logger.log_event(
                EventType.AGENT_ACTION,
                agent_id,
                "request_received",
                {
                    "endpoint": str(request.url),
                    "method": request.method,
                    "headers": dict(request.headers)
                }
            )
            
            # Execute function
            result = await func(request, *args, **kwargs)
            
            # Log success
            duration_ms = (time.time() - start_time) * 1000
            audit_logger.log_event(
                EventType.AGENT_ACTION,
                agent_id,
                "request_completed",
                {"endpoint": str(request.url), "duration_ms": duration_ms},
                result="success",
                duration_ms=duration_ms
            )
            
            return result
            
        except Exception as e:
            # Log error
            duration_ms = (time.time() - start_time) * 1000
            audit_logger.log_event(
                EventType.AGENT_ACTION,
                agent_id,
                "request_failed",
                {"endpoint": str(request.url), "error": str(e)},
                severity="ERROR",
                result="failure",
                duration_ms=duration_ms
            )
            raise
    
    return wrapper

class PaymentRequiredException(HTTPException):
    """Exception raised when payment is required."""
    def __init__(self, amount_sats: int, service: str, escrow_id: str):
        super().__init__(
            status_code=402,
            detail={
                "payment_required": True,
                "amount_sats": amount_sats,
                "service": service,
                "escrow_id": escrow_id
            }
        )
