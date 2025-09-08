"""
Core Agent base class for BitAgent framework.
Provides the foundation for all agents with security and monitoring integration.
"""

import time
import logging
from typing import Dict, Any, List, Optional
from abc import ABC, abstractmethod
from dataclasses import dataclass

# Import enhanced security components
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from security.authentication import AuthenticationManager
from security.encryption import EncryptionManager
from security.secure_communication import SecureCommunicationManager
from security.payment_security import PaymentSecurityManager
from identity.enhanced_did import EnhancedDIDManager
from monitoring.audit_logger import AuditLogger, EventType
from monitoring.performance_monitor import PerformanceMonitor, AgentPerformanceTracker

@dataclass
class Message:
    """Standard message format for agent communication."""
    message_id: str
    sender_id: str
    recipient_id: str
    message_type: str
    payload: Dict[str, Any]
    timestamp: float
    correlation_id: Optional[str] = None

class Agent(ABC):
    """
    Base Agent class with integrated security, monitoring, and payment capabilities.
    All BitAgent agents should inherit from this class.
    """
    
    def __init__(self, agent_id: str, name: str, description: str, services: List[str], **kwargs):
        self.agent_id = agent_id
        self.name = name
        self.description = description
        self.services = services
        
        # Initialize security components
        self.auth_manager = AuthenticationManager()
        self.encryption_manager = EncryptionManager()
        self.comm_manager = SecureCommunicationManager(agent_id, self.auth_manager)
        self.payment_security = PaymentSecurityManager()
        
        # Initialize identity and trust
        self.did_manager = EnhancedDIDManager()
        self.did = self.did_manager.create_did(agent_id)
        
        # Initialize monitoring
        self.audit_logger = AuditLogger(f"audit_{agent_id}.log")
        self.performance_monitor = PerformanceMonitor()
        self.performance_tracker = AgentPerformanceTracker(agent_id, self.performance_monitor)
        
        # Generate API key
        self.api_key = self.auth_manager.generate_api_key(agent_id, ["read", "write", "admin"])
        
        # Agent metadata
        self.created_at = time.time()
        self.last_activity = time.time()
        self.status = "initialized"
        
        # Log agent creation
        self.audit_logger.log_event(
            EventType.SYSTEM,
            agent_id,
            "agent_created",
            {"name": name, "services": services, "did": self.did}
        )
        
        logging.info(f"Agent {name} ({agent_id}) initialized with DID: {self.did}")
    
    @abstractmethod
    async def handle_request(self, message: Message) -> Dict[str, Any]:
        """
        Handle incoming requests. Must be implemented by subclasses.
        """
        pass
    
    def get_info(self) -> Dict[str, Any]:
        """Get agent information."""
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "description": self.description,
            "services": self.services,
            "did": self.did,
            "status": self.status,
            "created_at": self.created_at,
            "last_activity": self.last_activity
        }
    
    def list_services(self) -> List[str]:
        """List available services."""
        return self.services
    
    async def process_service_request(self, service: str, parameters: Dict[str, Any], 
                                    request_id: str = None) -> Dict[str, Any]:
        """Process a service request with monitoring and security."""
        start_time = time.time()
        request_id = request_id or f"req_{int(time.time() * 1000)}"
        
        try:
            # Log request
            self.audit_logger.log_event(
                EventType.AGENT_ACTION,
                self.agent_id,
                "service_request_received",
                {"service": service, "parameters": parameters, "request_id": request_id}
            )
            
            # Validate service
            if service not in self.services:
                raise ValueError(f"Service '{service}' not available")
            
            # Process the request
            result = await self._process_service_impl(service, parameters)
            
            # Log success
            duration_ms = (time.time() - start_time) * 1000
            self.performance_tracker.record_request(duration_ms, True, service)
            
            self.audit_logger.log_event(
                EventType.AGENT_ACTION,
                self.agent_id,
                "service_request_completed",
                {"service": service, "request_id": request_id, "duration_ms": duration_ms},
                result="success",
                duration_ms=duration_ms
            )
            
            return {
                "status": "success",
                "result": result,
                "request_id": request_id,
                "processing_time_ms": duration_ms
            }
            
        except Exception as e:
            # Log error
            duration_ms = (time.time() - start_time) * 1000
            self.performance_tracker.record_request(duration_ms, False, service)
            
            self.audit_logger.log_event(
                EventType.AGENT_ACTION,
                self.agent_id,
                "service_request_failed",
                {"service": service, "error": str(e), "request_id": request_id},
                severity="ERROR",
                result="failure",
                duration_ms=duration_ms
            )
            
            return {
                "status": "error",
                "error": str(e),
                "request_id": request_id,
                "processing_time_ms": duration_ms
            }
    
    async def _process_service_impl(self, service: str, parameters: Dict[str, Any]) -> Any:
        """
        Internal service processing. Override this method in subclasses.
        """
        # Default implementation - delegate to handle_request for backward compatibility
        message = Message(
            message_id=f"msg_{int(time.time() * 1000)}",
            sender_id="system",
            recipient_id=self.agent_id,
            message_type="service_request",
            payload={"service": service, "parameters": parameters},
            timestamp=time.time()
        )
        
        return await self.handle_request(message)
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics."""
        return self.performance_tracker.get_performance_stats()
    
    def get_security_report(self) -> Dict[str, Any]:
        """Get security report."""
        return self.audit_logger.generate_security_report()
    
    def get_trust_score(self) -> float:
        """Get current trust score."""
        trust_score = self.did_manager.get_agent_reputation(self.agent_id)
        return trust_score.overall_score if trust_score else 0.0
    
    def update_status(self, status: str):
        """Update agent status."""
        self.status = status
        self.last_activity = time.time()
        
        self.audit_logger.log_event(
            EventType.SYSTEM,
            self.agent_id,
            "status_updated",
            {"new_status": status}
        )
    
    def __repr__(self):
        return f"<Agent {self.name} ({self.agent_id})>"
