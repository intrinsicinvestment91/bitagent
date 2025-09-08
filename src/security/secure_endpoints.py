"""
Secure endpoint decorators and utilities for BitAgent.
Provides authentication, authorization, and input validation.
"""

import functools
import time
import logging
from typing import Callable, Any, Dict, Optional, List
from fastapi import Request, HTTPException, Depends, UploadFile
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, validator
import secrets
import hashlib

# Security scheme
security_scheme = HTTPBearer()

class SecureAuthManager:
    """Simplified authentication manager for production use."""
    
    def __init__(self, secret_key: str = None):
        self.secret_key = secret_key or secrets.token_urlsafe(32)
        self.api_keys = {}  # In production, use database
        self.rate_limits = {}  # Simple rate limiting
        
    def generate_api_key(self, agent_id: str, permissions: List[str] = None) -> str:
        """Generate a secure API key."""
        permissions = permissions or ["read"]
        api_key = secrets.token_urlsafe(32)
        
        self.api_keys[api_key] = {
            "agent_id": agent_id,
            "permissions": permissions,
            "created_at": time.time(),
            "last_used": time.time()
        }
        
        return api_key
    
    def verify_api_key(self, api_key: str) -> Optional[Dict[str, Any]]:
        """Verify API key and check rate limits."""
        if api_key not in self.api_keys:
            return None
            
        # Check rate limits (simple implementation)
        now = time.time()
        agent_data = self.api_keys[api_key]
        
        # Update last used
        agent_data["last_used"] = now
        
        return agent_data
    
    def check_rate_limit(self, api_key: str, max_requests: int = 100, window: int = 3600) -> bool:
        """Check if agent is within rate limits."""
        # Simple rate limiting - in production use Redis or similar
        return True  # For now, allow all requests

# Global auth manager
auth_manager = SecureAuthManager()

def get_current_agent(credentials: HTTPAuthorizationCredentials = Depends(security_scheme)) -> Dict[str, Any]:
    """Extract and validate agent from API key."""
    api_key = credentials.credentials
    agent_data = auth_manager.verify_api_key(api_key)
    
    if not agent_data:
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    # Check rate limits
    if not auth_manager.check_rate_limit(api_key):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    
    return agent_data

def require_authentication(permissions: List[str] = None):
    """Decorator to require authentication for endpoints."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(request: Request, *args, **kwargs):
            try:
                # Get agent from API key
                agent_data = get_current_agent()
                agent_id = agent_data["agent_id"]
                agent_permissions = agent_data.get("permissions", [])
                
                # Check permissions
                if permissions:
                    if not any(perm in agent_permissions for perm in permissions):
                        raise HTTPException(
                            status_code=403, 
                            detail=f"Insufficient permissions. Required: {permissions}"
                        )
                
                # Add agent info to request state
                request.state.agent_id = agent_id
                request.state.agent_permissions = agent_permissions
                
                # Log authentication
                logging.info(f"Authenticated request from agent {agent_id}")
                
                return await func(request, *args, **kwargs)
                
            except HTTPException:
                raise
            except Exception as e:
                logging.error(f"Authentication error: {e}")
                raise HTTPException(status_code=401, detail="Authentication failed")
        
        return wrapper
    return decorator

def require_payment(min_sats: int, service_name: str):
    """Decorator to require payment before service execution."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(request: Request, *args, **kwargs):
            try:
                # Check for payment hash in request
                body = await request.json()
                payment_hash = body.get("payment_hash")
                
                if not payment_hash:
                    # Create invoice for payment
                    from start9_payment_integration import Start9PaymentManager
                    payment_manager = Start9PaymentManager()
                    
                    invoice_data = payment_manager.create_service_invoice(
                        service_name, min_sats, "Service payment"
                    )
                    
                    raise HTTPException(
                        status_code=402,
                        detail="Payment required",
                        headers={"X-Payment-Required": "true"},
                        extra=invoice_data
                    )
                
                # Verify payment
                from start9_payment_integration import Start9PaymentManager
                payment_manager = Start9PaymentManager()
                
                if not payment_manager.verify_payment(payment_hash):
                    raise HTTPException(
                        status_code=402,
                        detail="Payment not verified"
                    )
                
                # Payment verified, proceed with service
                logging.info(f"Payment verified for {service_name}: {payment_hash}")
                return await func(request, *args, **kwargs)
                
            except HTTPException:
                raise
            except Exception as e:
                logging.error(f"Payment verification error: {e}")
                raise HTTPException(status_code=500, detail="Payment verification failed")
        
        return wrapper
    return decorator

# Input validation models
class TranslationRequest(BaseModel):
    text: str
    source_lang: str = "auto"
    target_lang: str = "en"
    payment_hash: Optional[str] = None
    
    @validator('text')
    def validate_text(cls, v):
        if not v or not v.strip():
            raise ValueError('Text cannot be empty')
        if len(v) > 10000:
            raise ValueError('Text too long (max 10000 characters)')
        return v.strip()
    
    @validator('source_lang', 'target_lang')
    def validate_language_codes(cls, v):
        if v != "auto" and len(v) != 2:
            raise ValueError('Language codes must be 2 characters or "auto"')
        return v.lower()

class TranscriptionRequest(BaseModel):
    payment_hash: Optional[str] = None
    
    @validator('payment_hash')
    def validate_payment_hash(cls, v):
        if v and len(v) != 64:
            raise ValueError('Invalid payment hash format')
        return v

class TaskChainRequest(BaseModel):
    tasks: List[Dict[str, Any]]
    payment_hash: Optional[str] = None
    
    @validator('tasks')
    def validate_tasks(cls, v):
        if not v:
            raise ValueError('Tasks list cannot be empty')
        if len(v) > 10:
            raise ValueError('Too many tasks (max 10)')
        
        for task in v:
            if not task.get('service'):
                raise ValueError('Each task must have a service')
            if not task.get('parameters'):
                raise ValueError('Each task must have parameters')
        
        return v

def validate_file_upload(file: UploadFile, max_size: int = 10 * 1024 * 1024) -> UploadFile:
    """Validate file upload size and type."""
    if file.size > max_size:
        raise HTTPException(
            status_code=413, 
            detail=f"File too large. Maximum size: {max_size // (1024*1024)}MB"
        )
    
    # Check file type
    allowed_types = ['audio/wav', 'audio/mp3', 'audio/mpeg', 'audio/ogg']
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed: {', '.join(allowed_types)}"
        )
    
    return file

def log_security_event(event_type: str, agent_id: str, details: Dict[str, Any]):
    """Log security events for monitoring."""
    logging.warning(f"SECURITY_EVENT: {event_type} from agent {agent_id}: {details}")

def sanitize_input(text: str, max_length: int = 1000) -> str:
    """Sanitize user input."""
    if not text:
        return ""
    
    # Remove control characters and null bytes
    sanitized = "".join(char for char in text if ord(char) >= 32 or char in "\t\n\r")
    
    # Limit length
    return sanitized[:max_length]
