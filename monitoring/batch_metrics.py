import time
import psutil
import threading
import logging
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Callable
from collections import defaultdict, deque
import json

try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

try:
    import GPUtil
    GPUTIL_AVAILABLE = True
except ImportError:
    GPUTIL_AVAILABLE = False

from config.anpr_config import ANPRProcessingMetrics
from db.anpr_integration import ANPRDatabaseIntegration


@dataclass
class SystemMetrics:
    """System performance metrics at a point in time."""
    timestamp: datetime
    cpu_percent: float
    memory_percent: float
    memory_available_gb: float
    disk_usage_percent: float
    gpu_metrics: List[Dict[str, Any]] = field(default_factory=list)
    process_metrics: Dict[str, Any] = field(default_factory=dict)


@dataclass  
class ProcessingMetrics:
    """Processing performance metrics."""
    session_id: str
    start_time: datetime
    files_processed: int = 0
    total_files: int = 0
    processing_times: deque = field(default_factory=lambda: deque(maxlen=1000))
    error_count: int = 0
    gpu_utilization: deque = field(default_factory=lambda: deque(maxlen=1000))
    success_count: int = 0
    bytes_processed: int = 0
    
    def update(self, processing_time: float, success: bool = True, file_size: int = 0):
        """Update metrics with new processing result."""
        self.files_processed += 1
        self.processing_times.append(processing_time)
        
        if success:
            self.success_count += 1
        else:
            self.error_count += 1
            
        self.bytes_processed += file_size
        
        # Sample GPU utilization if available
        if TORCH_AVAILABLE and torch.cuda.is_available():
            try:
                gpu_util = torch.cuda.utilization()
                self.gpu_utilization.append(gpu_util)
            except Exception:
                pass
    
    def get_completion_rate(self) -> float:
        """Get processing completion rate."""
        if self.total_files == 0:
            return 0.0
        return self.files_processed / self.total_files
    
    def get_success_rate(self) -> float:
        """Get processing success rate."""
        if self.files_processed == 0:
            return 0.0
        return self.success_count / self.files_processed
    
    def get_average_processing_time(self) -> float:
        """Get average processing time per file."""
        if not self.processing_times:
            return 0.0
        return sum(self.processing_times) / len(self.processing_times)
    
    def get_files_per_minute(self) -> float:
        """Get processing rate in files per minute."""
        elapsed = (datetime.now() - self.start_time).total_seconds() / 60
        if elapsed == 0:
            return 0.0
        return self.files_processed / elapsed
    
    def get_throughput_mbps(self) -> float:
        """Get throughput in MB per second."""
        elapsed = (datetime.now() - self.start_time).total_seconds()
        if elapsed == 0:
            return 0.0
        return (self.bytes_processed / 1024 / 1024) / elapsed
    
    def get_average_gpu_utilization(self) -> float:
        """Get average GPU utilization."""
        if not self.gpu_utilization:
            return 0.0
        return sum(self.gpu_utilization) / len(self.gpu_utilization)
    
    def get_current_rate(self, window_minutes: int = 5) -> float:
        """Get current processing rate over a time window."""
        if not self.processing_times:
            return 0.0
        
        cutoff_time = datetime.now() - timedelta(minutes=window_minutes)
        recent_count = sum(1 for _ in self.processing_times)  # Simplified for now
        return recent_count / window_minutes


class PerformanceMonitor:
    """Comprehensive performance monitoring system."""
    
    def __init__(self, db_integration: ANPRDatabaseIntegration, 
                 sample_interval: float = 5.0):
        self.db_integration = db_integration
        self.sample_interval = sample_interval
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Monitoring state
        self.is_monitoring = False
        self.monitor_thread: Optional[threading.Thread] = None
        
        # Metrics storage
        self.system_metrics: deque = deque(maxlen=1000)
        self.processing_metrics: Dict[str, ProcessingMetrics] = {}
        
        # Callbacks for real-time updates
        self.callbacks: List[Callable[[Dict[str, Any]], None]] = []
        
        # Process tracking
        self.process_info = {}
        
    def start_monitoring(self, session_id: str):
        """Start performance monitoring for a session."""
        if self.is_monitoring:
            self.logger.warning("Monitoring already active")
            return
        
        self.is_monitoring = True
        self.processing_metrics[session_id] = ProcessingMetrics(
            session_id=session_id,
            start_time=datetime.now()
        )
        
        # Start monitoring thread
        self.monitor_thread = threading.Thread(
            target=self._monitoring_loop,
            args=(session_id,),
            daemon=True
        )
        self.monitor_thread.start()
        
        self.logger.info(f"Started performance monitoring for session {session_id}")
    
    def stop_monitoring(self, session_id: str):
        """Stop performance monitoring."""
        self.is_monitoring = False
        
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=5)
        
        # Final metrics logging
        if session_id in self.processing_metrics:
            final_metrics = self.processing_metrics[session_id]
            self._log_final_metrics(session_id, final_metrics)
            
        self.logger.info(f"Stopped performance monitoring for session {session_id}")
    
    def _monitoring_loop(self, session_id: str):
        """Main monitoring loop."""
        while self.is_monitoring:
            try:
                # Collect system metrics
                system_metrics = self._collect_system_metrics()
                self.system_metrics.append(system_metrics)
                
                # Log to database
                self._log_system_metrics(session_id, system_metrics)
                
                # Notify callbacks
                metrics_data = self._prepare_metrics_data(session_id, system_metrics)
                for callback in self.callbacks:
                    try:
                        callback(metrics_data)
                    except Exception as e:
                        self.logger.error(f"Callback error: {e}")
                
                time.sleep(self.sample_interval)
                
            except Exception as e:
                self.logger.error(f"Monitoring loop error: {e}")
                time.sleep(self.sample_interval)
    
    def _collect_system_metrics(self) -> SystemMetrics:
        """Collect current system metrics."""
        # CPU and memory
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        # GPU metrics
        gpu_metrics = []
        if GPUTIL_AVAILABLE:
            try:
                gpus = GPUtil.getGPUs()
                for i, gpu in enumerate(gpus):
                    gpu_metrics.append({
                        'gpu_id': i,
                        'name': gpu.name,
                        'utilization_percent': gpu.load * 100,
                        'memory_used_mb': gpu.memoryUsed,
                        'memory_total_mb': gpu.memoryTotal,
                        'memory_percent': gpu.memoryUtil * 100,
                        'temperature_c': gpu.temperature
                    })
            except Exception as e:
                self.logger.warning(f"Could not collect GPU metrics: {e}")
        elif TORCH_AVAILABLE and torch.cuda.is_available():
            try:
                for i in range(torch.cuda.device_count()):
                    props = torch.cuda.get_device_properties(i)
                    gpu_metrics.append({
                        'gpu_id': i,
                        'name': props.name,
                        'utilization_percent': torch.cuda.utilization(i),
                        'memory_used_mb': torch.cuda.memory_allocated(i) / 1024 / 1024,
                        'memory_total_mb': props.total_memory / 1024 / 1024,
                        'memory_percent': (torch.cuda.memory_allocated(i) / props.total_memory) * 100,
                        'temperature_c': None
                    })
            except Exception as e:
                self.logger.warning(f"Could not collect CUDA metrics: {e}")
        
        # Process metrics
        process_metrics = {}
        try:
            current_process = psutil.Process()
            process_metrics = {
                'pid': current_process.pid,
                'cpu_percent': current_process.cpu_percent(),
                'memory_mb': current_process.memory_info().rss / 1024 / 1024,
                'threads': current_process.num_threads(),
                'open_files': len(current_process.open_files()),
                'connections': len(current_process.connections())
            }
        except Exception as e:
            self.logger.warning(f"Could not collect process metrics: {e}")
        
        return SystemMetrics(
            timestamp=datetime.now(),
            cpu_percent=cpu_percent,
            memory_percent=memory.percent,
            memory_available_gb=memory.available / 1024 / 1024 / 1024,
            disk_usage_percent=disk.percent,
            gpu_metrics=gpu_metrics,
            process_metrics=process_metrics
        )
    
    def _log_system_metrics(self, session_id: str, metrics: SystemMetrics):
        """Log system metrics to database."""
        try:
            # Log CPU and memory metrics
            self.db_integration.log_performance_metric(
                session_id, "cpu_percent", metrics.cpu_percent, "gauge"
            )
            self.db_integration.log_performance_metric(
                session_id, "memory_percent", metrics.memory_percent, "gauge"
            )
            self.db_integration.log_performance_metric(
                session_id, "memory_available_gb", metrics.memory_available_gb, "gauge"
            )
            
            # Log GPU metrics
            if metrics.gpu_metrics:
                self.db_integration.log_gpu_utilization(session_id, metrics.gpu_metrics)
            
            # Log process metrics
            for key, value in metrics.process_metrics.items():
                if isinstance(value, (int, float)):
                    self.db_integration.log_performance_metric(
                        session_id, f"process_{key}", float(value), "gauge"
                    )
                    
        except Exception as e:
            self.logger.error(f"Failed to log system metrics: {e}")
    
    def _prepare_metrics_data(self, session_id: str, system_metrics: SystemMetrics) -> Dict[str, Any]:
        """Prepare metrics data for callbacks."""
        processing_metrics = self.processing_metrics.get(session_id)
        
        data = {
            'session_id': session_id,
            'timestamp': system_metrics.timestamp.isoformat(),
            'system': {
                'cpu_percent': system_metrics.cpu_percent,
                'memory_percent': system_metrics.memory_percent,
                'memory_available_gb': system_metrics.memory_available_gb,
                'disk_usage_percent': system_metrics.disk_usage_percent,
                'gpu_metrics': system_metrics.gpu_metrics,
                'process_metrics': system_metrics.process_metrics
            }
        }
        
        if processing_metrics:
            data['processing'] = {
                'files_processed': processing_metrics.files_processed,
                'total_files': processing_metrics.total_files,
                'completion_rate': processing_metrics.get_completion_rate(),
                'success_rate': processing_metrics.get_success_rate(),
                'avg_processing_time': processing_metrics.get_average_processing_time(),
                'files_per_minute': processing_metrics.get_files_per_minute(),
                'throughput_mbps': processing_metrics.get_throughput_mbps(),
                'avg_gpu_utilization': processing_metrics.get_average_gpu_utilization(),
                'current_rate': processing_metrics.get_current_rate()
            }
        
        return data
    
    def _log_final_metrics(self, session_id: str, metrics: ProcessingMetrics):
        """Log final processing metrics."""
        try:
            final_data = {
                'total_files': metrics.total_files,
                'files_processed': metrics.files_processed,
                'success_count': metrics.success_count,
                'error_count': metrics.error_count,
                'completion_rate': metrics.get_completion_rate(),
                'success_rate': metrics.get_success_rate(),
                'avg_processing_time': metrics.get_average_processing_time(),
                'files_per_minute': metrics.get_files_per_minute(),
                'throughput_mbps': metrics.get_throughput_mbps(),
                'avg_gpu_utilization': metrics.get_average_gpu_utilization()
            }
            
            # Log as JSON to database
            self.db_integration.log_performance_metric(
                session_id, "final_summary", 0, "summary"
            )
            
            self.logger.info(f"Final metrics for {session_id}: {json.dumps(final_data, indent=2)}")
            
        except Exception as e:
            self.logger.error(f"Failed to log final metrics: {e}")
    
    def update_processing_metrics(self, session_id: str, processing_time: float, 
                                success: bool = True, file_size: int = 0):
        """Update processing metrics for a file."""
        if session_id in self.processing_metrics:
            self.processing_metrics[session_id].update(processing_time, success, file_size)
    
    def set_total_files(self, session_id: str, total_files: int):
        """Set total files count for a session."""
        if session_id in self.processing_metrics:
            self.processing_metrics[session_id].total_files = total_files
    
    def add_callback(self, callback: Callable[[Dict[str, Any]], None]):
        """Add a callback for real-time metrics updates."""
        self.callbacks.append(callback)
    
    def remove_callback(self, callback: Callable[[Dict[str, Any]], None]):
        """Remove a callback."""
        if callback in self.callbacks:
            self.callbacks.remove(callback)
    
    def get_current_metrics(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get current metrics for a session."""
        if session_id not in self.processing_metrics:
            return None
        
        if not self.system_metrics:
            return None
        
        return self._prepare_metrics_data(session_id, self.system_metrics[-1])
    
    def get_metrics_history(self, session_id: str, minutes: int = 30) -> List[Dict[str, Any]]:
        """Get metrics history for a time window."""
        cutoff_time = datetime.now() - timedelta(minutes=minutes)
        
        recent_metrics = [
            self._prepare_metrics_data(session_id, sm)
            for sm in self.system_metrics
            if sm.timestamp >= cutoff_time
        ]
        
        return recent_metrics