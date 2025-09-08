"""
Comprehensive audit logging and monitoring system for BitAgent.
Implements structured logging, metrics collection, and security monitoring.
"""

import json
import time
import hashlib
import logging
import asyncio
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, asdict
from enum import Enum
import threading
from collections import defaultdict, deque
import os
from datetime import datetime, timedelta

class LogLevel(Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

class EventType(Enum):
    AUTHENTICATION = "authentication"
    PAYMENT = "payment"
    COMMUNICATION = "communication"
    DISCOVERY = "discovery"
    SECURITY = "security"
    SYSTEM = "system"
    AGENT_ACTION = "agent_action"

class SecurityEvent(Enum):
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILURE = "login_failure"
    PAYMENT_SUCCESS = "payment_success"
    PAYMENT_FAILURE = "payment_failure"
    FRAUD_DETECTED = "fraud_detected"
    UNAUTHORIZED_ACCESS = "unauthorized_access"
    DATA_BREACH = "data_breach"
    SUSPICIOUS_ACTIVITY = "suspicious_activity"

@dataclass
class AuditEvent:
    """Structured audit event."""
    event_id: str
    timestamp: float
    event_type: EventType
    security_event: Optional[SecurityEvent]
    agent_id: str
    action: str
    details: Dict[str, Any]
    ip_address: Optional[str]
    user_agent: Optional[str]
    severity: LogLevel
    correlation_id: Optional[str]
    session_id: Optional[str]
    result: str  # success, failure, error
    duration_ms: Optional[float]

@dataclass
class Metric:
    """Performance and system metric."""
    metric_name: str
    value: Union[int, float]
    timestamp: float
    tags: Dict[str, str]
    unit: Optional[str]

@dataclass
class Alert:
    """Security or system alert."""
    alert_id: str
    alert_type: str
    severity: LogLevel
    message: str
    timestamp: float
    agent_id: Optional[str]
    resolved: bool
    resolution_notes: Optional[str]

class AuditLogger:
    """Comprehensive audit logging system."""
    
    def __init__(self, log_file: str = "audit.log", max_file_size: int = 100 * 1024 * 1024):
        self.log_file = log_file
        self.max_file_size = max_file_size
        self.events = deque(maxlen=10000)  # Keep last 10k events in memory
        self.metrics = defaultdict(list)
        self.alerts = []
        self.correlation_ids = {}
        
        # Setup logging
        self._setup_logging()
        
        # Start background tasks
        self._start_background_tasks()
    
    def _setup_logging(self):
        """Setup structured logging."""
        # Create formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        # File handler
        file_handler = logging.FileHandler(self.log_file)
        file_handler.setFormatter(formatter)
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        
        # Setup logger
        self.logger = logging.getLogger('bitagent_audit')
        self.logger.setLevel(logging.INFO)
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)
    
    def log_event(self, event_type: EventType, agent_id: str, action: str,
                  details: Dict[str, Any], security_event: SecurityEvent = None,
                  severity: LogLevel = LogLevel.INFO, ip_address: str = None,
                  user_agent: str = None, correlation_id: str = None,
                  session_id: str = None, result: str = "success",
                  duration_ms: float = None):
        """Log an audit event."""
        event_id = self._generate_event_id()
        
        event = AuditEvent(
            event_id=event_id,
            timestamp=time.time(),
            event_type=event_type,
            security_event=security_event,
            agent_id=agent_id,
            action=action,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent,
            severity=severity,
            correlation_id=correlation_id,
            session_id=session_id,
            result=result,
            duration_ms=duration_ms
        )
        
        # Store in memory
        self.events.append(event)
        
        # Log to file
        self._write_event_to_log(event)
        
        # Check for security alerts
        self._check_security_alerts(event)
        
        # Update correlation tracking
        if correlation_id:
            self._update_correlation_tracking(correlation_id, event)
    
    def log_authentication(self, agent_id: str, action: str, success: bool,
                          ip_address: str = None, user_agent: str = None,
                          details: Dict[str, Any] = None):
        """Log authentication events."""
        security_event = SecurityEvent.LOGIN_SUCCESS if success else SecurityEvent.LOGIN_FAILURE
        severity = LogLevel.INFO if success else LogLevel.WARNING
        
        self.log_event(
            event_type=EventType.AUTHENTICATION,
            agent_id=agent_id,
            action=action,
            details=details or {},
            security_event=security_event,
            severity=severity,
            ip_address=ip_address,
            user_agent=user_agent,
            result="success" if success else "failure"
        )
    
    def log_payment(self, agent_id: str, payment_id: str, amount: int,
                   success: bool, details: Dict[str, Any] = None):
        """Log payment events."""
        security_event = SecurityEvent.PAYMENT_SUCCESS if success else SecurityEvent.PAYMENT_FAILURE
        severity = LogLevel.INFO if success else LogLevel.ERROR
        
        payment_details = {
            "payment_id": payment_id,
            "amount_sats": amount,
            **(details or {})
        }
        
        self.log_event(
            event_type=EventType.PAYMENT,
            agent_id=agent_id,
            action="payment_processing",
            details=payment_details,
            security_event=security_event,
            severity=severity,
            result="success" if success else "failure"
        )
    
    def log_communication(self, sender_id: str, recipient_id: str, message_type: str,
                         success: bool, details: Dict[str, Any] = None):
        """Log agent communication events."""
        comm_details = {
            "sender_id": sender_id,
            "recipient_id": recipient_id,
            "message_type": message_type,
            **(details or {})
        }
        
        self.log_event(
            event_type=EventType.COMMUNICATION,
            agent_id=sender_id,
            action="agent_communication",
            details=comm_details,
            severity=LogLevel.INFO,
            result="success" if success else "failure"
        )
    
    def log_security_event(self, agent_id: str, security_event: SecurityEvent,
                          details: Dict[str, Any], severity: LogLevel = LogLevel.WARNING):
        """Log security events."""
        self.log_event(
            event_type=EventType.SECURITY,
            agent_id=agent_id,
            action=security_event.value,
            details=details,
            security_event=security_event,
            severity=severity,
            result="detected"
        )
    
    def record_metric(self, metric_name: str, value: Union[int, float],
                     tags: Dict[str, str] = None, unit: str = None):
        """Record a performance metric."""
        metric = Metric(
            metric_name=metric_name,
            value=value,
            timestamp=time.time(),
            tags=tags or {},
            unit=unit
        )
        
        self.metrics[metric_name].append(metric)
        
        # Keep only recent metrics (last 24 hours)
        cutoff_time = time.time() - (24 * 3600)
        self.metrics[metric_name] = [
            m for m in self.metrics[metric_name] 
            if m.timestamp > cutoff_time
        ]
    
    def create_alert(self, alert_type: str, message: str, severity: LogLevel,
                    agent_id: str = None) -> str:
        """Create a security or system alert."""
        alert_id = self._generate_alert_id()
        
        alert = Alert(
            alert_id=alert_id,
            alert_type=alert_type,
            severity=severity,
            message=message,
            timestamp=time.time(),
            agent_id=agent_id,
            resolved=False,
            resolution_notes=None
        )
        
        self.alerts.append(alert)
        
        # Log the alert
        self.log_event(
            event_type=EventType.SECURITY,
            agent_id=agent_id or "system",
            action="alert_created",
            details={"alert_id": alert_id, "alert_type": alert_type, "message": message},
            severity=severity,
            result="created"
        )
        
        return alert_id
    
    def resolve_alert(self, alert_id: str, resolution_notes: str):
        """Resolve an alert."""
        for alert in self.alerts:
            if alert.alert_id == alert_id:
                alert.resolved = True
                alert.resolution_notes = resolution_notes
                
                self.log_event(
                    event_type=EventType.SECURITY,
                    agent_id=alert.agent_id or "system",
                    action="alert_resolved",
                    details={"alert_id": alert_id, "resolution_notes": resolution_notes},
                    severity=LogLevel.INFO,
                    result="resolved"
                )
                break
    
    def get_events(self, event_type: EventType = None, agent_id: str = None,
                  start_time: float = None, end_time: float = None,
                  limit: int = 100) -> List[AuditEvent]:
        """Retrieve audit events with filtering."""
        filtered_events = []
        
        for event in self.events:
            if event_type and event.event_type != event_type:
                continue
            if agent_id and event.agent_id != agent_id:
                continue
            if start_time and event.timestamp < start_time:
                continue
            if end_time and event.timestamp > end_time:
                continue
            
            filtered_events.append(event)
            
            if len(filtered_events) >= limit:
                break
        
        return filtered_events
    
    def get_metrics(self, metric_name: str, start_time: float = None,
                   end_time: float = None) -> List[Metric]:
        """Retrieve metrics for a specific metric name."""
        if metric_name not in self.metrics:
            return []
        
        metrics = self.metrics[metric_name]
        
        if start_time:
            metrics = [m for m in metrics if m.timestamp >= start_time]
        if end_time:
            metrics = [m for m in metrics if m.timestamp <= end_time]
        
        return metrics
    
    def get_active_alerts(self) -> List[Alert]:
        """Get all unresolved alerts."""
        return [alert for alert in self.alerts if not alert.resolved]
    
    def generate_security_report(self, start_time: float = None,
                               end_time: float = None) -> Dict[str, Any]:
        """Generate a security report."""
        if not start_time:
            start_time = time.time() - (24 * 3600)  # Last 24 hours
        if not end_time:
            end_time = time.time()
        
        # Get security events
        security_events = self.get_events(
            event_type=EventType.SECURITY,
            start_time=start_time,
            end_time=end_time
        )
        
        # Count by type
        event_counts = defaultdict(int)
        for event in security_events:
            if event.security_event:
                event_counts[event.security_event.value] += 1
        
        # Get active alerts
        active_alerts = self.get_active_alerts()
        
        # Get failed authentication attempts
        auth_events = self.get_events(
            event_type=EventType.AUTHENTICATION,
            start_time=start_time,
            end_time=end_time
        )
        failed_auth = sum(1 for event in auth_events if event.result == "failure")
        
        return {
            "report_period": {
                "start": start_time,
                "end": end_time
            },
            "security_events": dict(event_counts),
            "failed_authentications": failed_auth,
            "active_alerts": len(active_alerts),
            "total_events": len(security_events),
            "high_severity_events": len([e for e in security_events if e.severity == LogLevel.CRITICAL])
        }
    
    def _generate_event_id(self) -> str:
        """Generate unique event ID."""
        return f"evt_{int(time.time() * 1000)}_{hashlib.md5(str(time.time()).encode()).hexdigest()[:8]}"
    
    def _generate_alert_id(self) -> str:
        """Generate unique alert ID."""
        return f"alert_{int(time.time() * 1000)}_{hashlib.md5(str(time.time()).encode()).hexdigest()[:8]}"
    
    def _write_event_to_log(self, event: AuditEvent):
        """Write event to log file."""
        log_entry = {
            "event_id": event.event_id,
            "timestamp": event.timestamp,
            "event_type": event.event_type.value,
            "security_event": event.security_event.value if event.security_event else None,
            "agent_id": event.agent_id,
            "action": event.action,
            "details": event.details,
            "ip_address": event.ip_address,
            "user_agent": event.user_agent,
            "severity": event.severity.value,
            "correlation_id": event.correlation_id,
            "session_id": event.session_id,
            "result": event.result,
            "duration_ms": event.duration_ms
        }
        
        self.logger.info(json.dumps(log_entry))
    
    def _check_security_alerts(self, event: AuditEvent):
        """Check for security alert conditions."""
        # Check for multiple failed logins
        if (event.event_type == EventType.AUTHENTICATION and 
            event.result == "failure"):
            self._check_failed_login_pattern(event.agent_id)
        
        # Check for suspicious payment patterns
        if event.event_type == EventType.PAYMENT:
            self._check_payment_patterns(event)
        
        # Check for high-severity events
        if event.severity in [LogLevel.ERROR, LogLevel.CRITICAL]:
            self.create_alert(
                "high_severity_event",
                f"High severity event: {event.action}",
                event.severity,
                event.agent_id
            )
    
    def _check_failed_login_pattern(self, agent_id: str):
        """Check for patterns of failed login attempts."""
        recent_events = self.get_events(
            event_type=EventType.AUTHENTICATION,
            agent_id=agent_id,
            start_time=time.time() - 3600  # Last hour
        )
        
        failed_attempts = [e for e in recent_events if e.result == "failure"]
        
        if len(failed_attempts) >= 5:  # 5 failed attempts in an hour
            self.create_alert(
                "brute_force_attack",
                f"Multiple failed login attempts for agent {agent_id}",
                LogLevel.WARNING,
                agent_id
            )
    
    def _check_payment_patterns(self, event: AuditEvent):
        """Check for suspicious payment patterns."""
        # This would implement more sophisticated fraud detection
        # For now, just check for very large amounts
        amount = event.details.get("amount_sats", 0)
        if amount > 1000000:  # 1M sats
            self.create_alert(
                "large_payment",
                f"Large payment detected: {amount} sats",
                LogLevel.WARNING,
                event.agent_id
            )
    
    def _update_correlation_tracking(self, correlation_id: str, event: AuditEvent):
        """Update correlation tracking for request tracing."""
        if correlation_id not in self.correlation_ids:
            self.correlation_ids[correlation_id] = []
        
        self.correlation_ids[correlation_id].append(event)
    
    def _start_background_tasks(self):
        """Start background monitoring tasks."""
        # Start log rotation task
        threading.Thread(target=self._log_rotation_task, daemon=True).start()
        
        # Start metrics cleanup task
        threading.Thread(target=self._metrics_cleanup_task, daemon=True).start()
    
    def _log_rotation_task(self):
        """Background task for log rotation."""
        while True:
            try:
                if os.path.exists(self.log_file):
                    file_size = os.path.getsize(self.log_file)
                    if file_size > self.max_file_size:
                        # Rotate log file
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        rotated_file = f"{self.log_file}.{timestamp}"
                        os.rename(self.log_file, rotated_file)
                        
                        # Create new log file
                        self._setup_logging()
                        
                        self.logger.info("Log file rotated")
                
                time.sleep(3600)  # Check every hour
            except Exception as e:
                logging.error(f"Error in log rotation: {e}")
                time.sleep(3600)
    
    def _metrics_cleanup_task(self):
        """Background task for metrics cleanup."""
        while True:
            try:
                cutoff_time = time.time() - (7 * 24 * 3600)  # Keep 7 days
                
                for metric_name in list(self.metrics.keys()):
                    self.metrics[metric_name] = [
                        m for m in self.metrics[metric_name]
                        if m.timestamp > cutoff_time
                    ]
                    
                    # Remove empty metric lists
                    if not self.metrics[metric_name]:
                        del self.metrics[metric_name]
                
                time.sleep(3600)  # Cleanup every hour
            except Exception as e:
                logging.error(f"Error in metrics cleanup: {e}")
                time.sleep(3600)
