"""
Agent server utilities for BitAgent framework.
Provides FastAPI integration with security and monitoring.
"""

import functools
import time
import logging
from typing import Callable, Any, Dict, Optional, List
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# Import enhanced security components
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from security.authentication import AuthenticationManager
from monitoring.audit_logger import AuditLogger, EventType
from core.agent import Agent

# Global instances (in production, these would be dependency injected)
auth_manager = AuthenticationManager()
audit_logger = AuditLogger()

security_scheme = HTTPBearer()

def get_current_agent(credentials: HTTPAuthorizationCredentials = Depends(security_scheme)) -> Dict[str, Any]:
    """Extract and validate agent from API key."""
    api_key = credentials.credentials
    payload = auth_manager.verify_api_key(api_key)
    
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    return payload

def agent_route(router: APIRouter, path: str, agent: Agent, methods: List[str] = None, **kwargs):
    """
    Decorator to register an agent endpoint with security and monitoring.
    Replaces the missing agent_route from bitagent.core.
    """
    if methods is None:
        methods = ["POST"]
    
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(request: Request, *args, **kwargs):
            start_time = time.time()
            
            try:
                # Extract agent information
                agent_payload = get_current_agent()
                client_agent_id = agent_payload["agent_id"]
                
                # Log request
                audit_logger.log_event(
                    EventType.AGENT_ACTION,
                    client_agent_id,
                    "agent_request_received",
                    {
                        "endpoint": path,
                        "target_agent": agent.agent_id,
                        "method": request.method
                    }
                )
                
                # Add agent info to request state
                request.state.client_agent_id = client_agent_id
                request.state.target_agent = agent
                
                # Execute the function
                result = await func(request, *args, **kwargs)
                
                # Log success
                duration_ms = (time.time() - start_time) * 1000
                audit_logger.log_event(
                    EventType.AGENT_ACTION,
                    client_agent_id,
                    "agent_request_completed",
                    {
                        "endpoint": path,
                        "target_agent": agent.agent_id,
                        "duration_ms": duration_ms
                    },
                    result="success",
                    duration_ms=duration_ms
                )
                
                return result
                
            except HTTPException:
                raise
            except Exception as e:
                # Log error
                duration_ms = (time.time() - start_time) * 1000
                audit_logger.log_event(
                    EventType.AGENT_ACTION,
                    client_agent_id,
                    "agent_request_failed",
                    {
                        "endpoint": path,
                        "target_agent": agent.agent_id,
                        "error": str(e)
                    },
                    severity="ERROR",
                    result="failure",
                    duration_ms=duration_ms
                )
                
                raise HTTPException(status_code=500, detail=f"Agent request failed: {str(e)}")
        
        # Register the route with FastAPI
        router.add_api_route(
            path,
            wrapper,
            methods=methods,
            **kwargs
        )
        
        return wrapper
    
    return decorator

def create_agent_router(agent: Agent, prefix: str = "") -> APIRouter:
    """
    Create a FastAPI router for an agent with security middleware.
    """
    router = APIRouter(prefix=prefix)
    
    # Add agent info endpoint
    @router.get("/info")
    async def get_agent_info():
        """Get agent information."""
        return agent.get_info()
    
    # Add services endpoint
    @router.get("/services")
    async def get_services():
        """Get available services."""
        return {
            "services": agent.list_services(),
            "agent_id": agent.agent_id
        }
    
    # Add performance stats endpoint
    @router.get("/stats")
    async def get_performance_stats():
        """Get performance statistics."""
        return agent.get_performance_stats()
    
    # Add security report endpoint
    @router.get("/security")
    async def get_security_report():
        """Get security report."""
        return agent.get_security_report()
    
    return router

def secure_agent_endpoint(agent: Agent, endpoint_name: str):
    """
    Decorator to create a secure agent endpoint with proper authentication and monitoring.
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(request: Request, *args, **kwargs):
            start_time = time.time()
            
            try:
                # Extract agent information
                agent_payload = get_current_agent()
                client_agent_id = agent_payload["agent_id"]
                
                # Log request
                audit_logger.log_event(
                    EventType.AGENT_ACTION,
                    client_agent_id,
                    "secure_endpoint_accessed",
                    {
                        "endpoint": endpoint_name,
                        "target_agent": agent.agent_id,
                        "method": request.method
                    }
                )
                
                # Add agent info to request state
                request.state.client_agent_id = client_agent_id
                request.state.target_agent = agent
                
                # Execute the function
                result = await func(request, *args, **kwargs)
                
                # Log success
                duration_ms = (time.time() - start_time) * 1000
                audit_logger.log_event(
                    EventType.AGENT_ACTION,
                    client_agent_id,
                    "secure_endpoint_completed",
                    {
                        "endpoint": endpoint_name,
                        "target_agent": agent.agent_id,
                        "duration_ms": duration_ms
                    },
                    result="success",
                    duration_ms=duration_ms
                )
                
                return result
                
            except HTTPException:
                raise
            except Exception as e:
                # Log error
                duration_ms = (time.time() - start_time) * 1000
                audit_logger.log_event(
                    EventType.AGENT_ACTION,
                    client_agent_id,
                    "secure_endpoint_failed",
                    {
                        "endpoint": endpoint_name,
                        "target_agent": agent.agent_id,
                        "error": str(e)
                    },
                    severity="ERROR",
                    result="failure",
                    duration_ms=duration_ms
                )
                
                raise HTTPException(status_code=500, detail=f"Secure endpoint failed: {str(e)}")
        
        return wrapper
    
    return decorator

class AgentServer:
    """
    Agent server class that provides a complete FastAPI application for an agent.
    """
    
    def __init__(self, agent: Agent, title: str = None, description: str = None, version: str = "1.0.0"):
        self.agent = agent
        self.title = title or f"{agent.name} Server"
        self.description = description or agent.description
        self.version = version
        
        # Create FastAPI app
        from fastapi import FastAPI
        self.app = FastAPI(
            title=self.title,
            description=self.description,
            version=self.version
        )
        
        # Create router
        self.router = create_agent_router(agent)
        self.app.include_router(self.router)
        
        # Add middleware
        self._add_middleware()
        
        logging.info(f"Agent server created for {agent.name} ({agent.agent_id})")
    
    def _add_middleware(self):
        """Add security and monitoring middleware."""
        from fastapi.middleware.cors import CORSMiddleware
        from fastapi.middleware.trustedhost import TrustedHostMiddleware
        
        # CORS middleware
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],  # Configure appropriately for production
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        
        # Trusted host middleware
        self.app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=["*"]  # Configure appropriately for production
        )
    
    def add_endpoint(self, path: str, func: Callable, methods: List[str] = None, **kwargs):
        """Add an endpoint to the agent server."""
        if methods is None:
            methods = ["POST"]
        
        # Apply security decorator
        secure_func = secure_agent_endpoint(self.agent, path)(func)
        
        # Add to router
        self.router.add_api_route(
            path,
            secure_func,
            methods=methods,
            **kwargs
        )
    
    def get_app(self):
        """Get the FastAPI application."""
        return self.app
