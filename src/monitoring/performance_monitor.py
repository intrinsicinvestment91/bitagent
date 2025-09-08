"""
Performance monitoring and metrics collection for BitAgent.
Implements real-time performance tracking, health checks, and system metrics.
"""

import time
import psutil
import asyncio
import threading
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, asdict
from collections import defaultdict, deque
import json
import logging
from datetime import datetime, timedelta

@dataclass
class PerformanceMetric:
    """Performance metric data point."""
    name: str
    value: float
    timestamp: float
    tags: Dict[str, str]
    unit: str

@dataclass
class HealthCheck:
    """Health check result."""
    check_name: str
    status: str  # healthy, unhealthy, degraded
    message: str
    timestamp: float
    response_time_ms: float
    details: Dict[str, Any]

@dataclass
class SystemStats:
    """System resource statistics."""
    cpu_percent: float
    memory_percent: float
    disk_percent: float
    network_io: Dict[str, int]
    timestamp: float

class PerformanceMonitor:
    """Real-time performance monitoring system."""
    
    def __init__(self, collection_interval: float = 30.0):
        self.collection_interval = collection_interval
        self.metrics = defaultdict(lambda: deque(maxlen=1000))
        self.health_checks = {}
        self.system_stats = deque(maxlen=100)
        self.custom_metrics = {}
        self.alerts = []
        self.running = False
        self.monitor_thread = None
        
        # Performance thresholds
        self.thresholds = {
            "cpu_percent": 80.0,
            "memory_percent": 85.0,
            "disk_percent": 90.0,
            "response_time_ms": 5000.0,
            "error_rate": 0.05  # 5%
        }
    
    def start_monitoring(self):
        """Start the performance monitoring."""
        if self.running:
            return
        
        self.running = True
        self.monitor_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self.monitor_thread.start()
        logging.info("Performance monitoring started")
    
    def stop_monitoring(self):
        """Stop the performance monitoring."""
        self.running = False
        if self.monitor_thread:
            self.monitor_thread.join()
        logging.info("Performance monitoring stopped")
    
    def record_metric(self, name: str, value: float, tags: Dict[str, str] = None, unit: str = ""):
        """Record a custom metric."""
        metric = PerformanceMetric(
            name=name,
            value=value,
            timestamp=time.time(),
            tags=tags or {},
            unit=unit
        )
        
        self.metrics[name].append(metric)
        
        # Check thresholds
        self._check_metric_thresholds(name, value)
    
    def record_timing(self, operation: str, duration_ms: float, tags: Dict[str, str] = None):
        """Record timing metrics."""
        self.record_metric(f"{operation}_duration", duration_ms, tags, "ms")
        self.record_metric(f"{operation}_count", 1, tags, "count")
    
    def record_counter(self, name: str, increment: int = 1, tags: Dict[str, str] = None):
        """Record counter metrics."""
        self.record_metric(name, increment, tags, "count")
    
    def record_gauge(self, name: str, value: float, tags: Dict[str, str] = None):
        """Record gauge metrics."""
        self.record_metric(name, value, tags, "gauge")
    
    def add_health_check(self, name: str, check_func: Callable[[], HealthCheck]):
        """Add a health check function."""
        self.health_checks[name] = check_func
        logging.info(f"Added health check: {name}")
    
    def run_health_checks(self) -> Dict[str, HealthCheck]:
        """Run all health checks."""
        results = {}
        
        for name, check_func in self.health_checks.items():
            try:
                start_time = time.time()
                result = check_func()
                result.response_time_ms = (time.time() - start_time) * 1000
                results[name] = result
            except Exception as e:
                results[name] = HealthCheck(
                    check_name=name,
                    status="unhealthy",
                    message=f"Health check failed: {str(e)}",
                    timestamp=time.time(),
                    response_time_ms=0,
                    details={"error": str(e)}
                )
        
        return results
    
    def get_metrics(self, name: str, start_time: float = None, end_time: float = None) -> List[PerformanceMetric]:
        """Get metrics for a specific name."""
        if name not in self.metrics:
            return []
        
        metrics = list(self.metrics[name])
        
        if start_time:
            metrics = [m for m in metrics if m.timestamp >= start_time]
        if end_time:
            metrics = [m for m in metrics if m.timestamp <= end_time]
        
        return metrics
    
    def get_metric_summary(self, name: str, start_time: float = None, end_time: float = None) -> Dict[str, Any]:
        """Get summary statistics for a metric."""
        metrics = self.get_metrics(name, start_time, end_time)
        
        if not metrics:
            return {}
        
        values = [m.value for m in metrics]
        
        return {
            "count": len(values),
            "min": min(values),
            "max": max(values),
            "avg": sum(values) / len(values),
            "latest": values[-1] if values else None,
            "unit": metrics[0].unit if metrics else ""
        }
    
    def get_system_stats(self) -> SystemStats:
        """Get current system statistics."""
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        network = psutil.net_io_counters()
        
        stats = SystemStats(
            cpu_percent=cpu_percent,
            memory_percent=memory.percent,
            disk_percent=disk.percent,
            network_io={
                "bytes_sent": network.bytes_sent,
                "bytes_recv": network.bytes_recv,
                "packets_sent": network.packets_sent,
                "packets_recv": network.packets_recv
            },
            timestamp=time.time()
        )
        
        self.system_stats.append(stats)
        return stats
    
    def get_performance_report(self, start_time: float = None, end_time: float = None) -> Dict[str, Any]:
        """Generate a comprehensive performance report."""
        if not start_time:
            start_time = time.time() - 3600  # Last hour
        if not end_time:
            end_time = time.time()
        
        # Get system stats
        system_stats = [s for s in self.system_stats if start_time <= s.timestamp <= end_time]
        
        # Get health check results
        health_results = self.run_health_checks()
        
        # Get key metrics
        key_metrics = {}
        for metric_name in ["response_time", "error_rate", "throughput"]:
            if metric_name in self.metrics:
                key_metrics[metric_name] = self.get_metric_summary(metric_name, start_time, end_time)
        
        # Calculate system averages
        system_avg = {}
        if system_stats:
            system_avg = {
                "cpu_avg": sum(s.cpu_percent for s in system_stats) / len(system_stats),
                "memory_avg": sum(s.memory_percent for s in system_stats) / len(system_stats),
                "disk_avg": sum(s.disk_percent for s in system_stats) / len(system_stats)
            }
        
        return {
            "report_period": {
                "start": start_time,
                "end": end_time,
                "duration_hours": (end_time - start_time) / 3600
            },
            "system_stats": system_avg,
            "health_checks": {name: asdict(result) for name, result in health_results.items()},
            "key_metrics": key_metrics,
            "alerts": len(self.alerts),
            "overall_health": self._calculate_overall_health(health_results, system_avg)
        }
    
    def _monitoring_loop(self):
        """Main monitoring loop."""
        while self.running:
            try:
                # Collect system stats
                system_stats = self.get_system_stats()
                
                # Record system metrics
                self.record_gauge("system.cpu_percent", system_stats.cpu_percent)
                self.record_gauge("system.memory_percent", system_stats.memory_percent)
                self.record_gauge("system.disk_percent", system_stats.disk_percent)
                
                # Run health checks
                health_results = self.run_health_checks()
                for name, result in health_results.items():
                    self.record_gauge(f"health.{name}", 1 if result.status == "healthy" else 0)
                
                # Check for alerts
                self._check_system_alerts(system_stats, health_results)
                
                time.sleep(self.collection_interval)
                
            except Exception as e:
                logging.error(f"Error in monitoring loop: {e}")
                time.sleep(self.collection_interval)
    
    def _check_metric_thresholds(self, name: str, value: float):
        """Check if metric exceeds thresholds."""
        threshold_key = None
        
        if "cpu" in name.lower():
            threshold_key = "cpu_percent"
        elif "memory" in name.lower():
            threshold_key = "memory_percent"
        elif "disk" in name.lower():
            threshold_key = "disk_percent"
        elif "response_time" in name.lower() or "duration" in name.lower():
            threshold_key = "response_time_ms"
        elif "error" in name.lower():
            threshold_key = "error_rate"
        
        if threshold_key and threshold_key in self.thresholds:
            threshold = self.thresholds[threshold_key]
            if value > threshold:
                self._create_alert(f"metric_threshold_exceeded", 
                                 f"Metric {name} exceeded threshold: {value} > {threshold}",
                                 "warning")
    
    def _check_system_alerts(self, system_stats: SystemStats, health_results: Dict[str, HealthCheck]):
        """Check for system-level alerts."""
        # CPU alert
        if system_stats.cpu_percent > self.thresholds["cpu_percent"]:
            self._create_alert("high_cpu", 
                             f"High CPU usage: {system_stats.cpu_percent}%",
                             "warning")
        
        # Memory alert
        if system_stats.memory_percent > self.thresholds["memory_percent"]:
            self._create_alert("high_memory", 
                             f"High memory usage: {system_stats.memory_percent}%",
                             "warning")
        
        # Disk alert
        if system_stats.disk_percent > self.thresholds["disk_percent"]:
            self._create_alert("high_disk", 
                             f"High disk usage: {system_stats.disk_percent}%",
                             "critical")
        
        # Health check alerts
        for name, result in health_results.items():
            if result.status == "unhealthy":
                self._create_alert(f"health_check_failed", 
                                 f"Health check {name} failed: {result.message}",
                                 "critical")
    
    def _create_alert(self, alert_type: str, message: str, severity: str):
        """Create a performance alert."""
        alert = {
            "type": alert_type,
            "message": message,
            "severity": severity,
            "timestamp": time.time()
        }
        
        self.alerts.append(alert)
        logging.warning(f"Performance alert: {message}")
    
    def _calculate_overall_health(self, health_results: Dict[str, HealthCheck], 
                                system_avg: Dict[str, float]) -> str:
        """Calculate overall system health."""
        # Check health checks
        unhealthy_checks = sum(1 for result in health_results.values() if result.status == "unhealthy")
        total_checks = len(health_results)
        
        if unhealthy_checks > 0:
            return "unhealthy"
        
        # Check system resources
        if (system_avg.get("cpu_avg", 0) > 90 or 
            system_avg.get("memory_avg", 0) > 95 or 
            system_avg.get("disk_avg", 0) > 95):
            return "degraded"
        
        return "healthy"

class AgentPerformanceTracker:
    """Track performance metrics for individual agents."""
    
    def __init__(self, agent_id: str, performance_monitor: PerformanceMonitor):
        self.agent_id = agent_id
        self.monitor = performance_monitor
        self.request_times = deque(maxlen=1000)
        self.error_count = 0
        self.success_count = 0
    
    def record_request(self, duration_ms: float, success: bool, endpoint: str = None):
        """Record a request performance."""
        self.request_times.append(duration_ms)
        
        if success:
            self.success_count += 1
        else:
            self.error_count += 1
        
        # Record metrics
        tags = {"agent_id": self.agent_id}
        if endpoint:
            tags["endpoint"] = endpoint
        
        self.monitor.record_timing(f"agent_request", duration_ms, tags)
        self.monitor.record_counter(f"agent_requests", 1, tags)
        
        if not success:
            self.monitor.record_counter(f"agent_errors", 1, tags)
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics for this agent."""
        if not self.request_times:
            return {"error_rate": 0, "avg_response_time": 0, "total_requests": 0}
        
        total_requests = self.success_count + self.error_count
        error_rate = self.error_count / total_requests if total_requests > 0 else 0
        avg_response_time = sum(self.request_times) / len(self.request_times)
        
        return {
            "agent_id": self.agent_id,
            "total_requests": total_requests,
            "success_count": self.success_count,
            "error_count": self.error_count,
            "error_rate": error_rate,
            "avg_response_time_ms": avg_response_time,
            "min_response_time_ms": min(self.request_times),
            "max_response_time_ms": max(self.request_times)
        }

# Built-in health checks
def create_database_health_check(db_connection_func):
    """Create a database health check."""
    def check():
        try:
            start_time = time.time()
            # This would test the database connection
            # For now, return a mock result
            return HealthCheck(
                check_name="database",
                status="healthy",
                message="Database connection successful",
                timestamp=time.time(),
                response_time_ms=(time.time() - start_time) * 1000,
                details={"connection_pool_size": 10}
            )
        except Exception as e:
            return HealthCheck(
                check_name="database",
                status="unhealthy",
                message=f"Database connection failed: {str(e)}",
                timestamp=time.time(),
                response_time_ms=0,
                details={"error": str(e)}
            )
    return check

def create_payment_system_health_check(payment_client):
    """Create a payment system health check."""
    def check():
        try:
            start_time = time.time()
            # This would test the payment system
            # For now, return a mock result
            return HealthCheck(
                check_name="payment_system",
                status="healthy",
                message="Payment system operational",
                timestamp=time.time(),
                response_time_ms=(time.time() - start_time) * 1000,
                details={"balance": 1000000}
            )
        except Exception as e:
            return HealthCheck(
                check_name="payment_system",
                status="unhealthy",
                message=f"Payment system error: {str(e)}",
                timestamp=time.time(),
                response_time_ms=0,
                details={"error": str(e)}
            )
    return check
