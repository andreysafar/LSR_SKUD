import os
import json
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime


@dataclass
class ANPRBatchConfig:
    """Configuration for ANPR batch processing operations."""
    
    # Batch Processing Settings
    input_directories: List[str] = field(default_factory=list)
    cpu_workers: int = 4
    gpu_workers: int = 4 
    ffmpeg_gpu_workers: int = 0
    recognition_interval: float = 0.5
    
    # Video Processing
    video_extension: str = ".issvd"
    frame_skip: int = 10
    confidence_threshold: float = 0.25
    
    # Performance Optimization
    queue_size_multiplier: int = 2
    format_cache_enabled: bool = True
    timeout_seconds: int = 120
    
    # Output Configuration
    output_csv_path: str = "batch_processing/plates.csv"
    output_images_dir: str = "data/snapshots"
    
    # Advanced Settings
    use_torchscript: bool = True
    half_precision: bool = True
    process_timeout: int = 3600  # 1 hour default
    
    @classmethod
    def from_env(cls) -> "ANPRBatchConfig":
        """Create configuration from environment variables."""
        return cls(
            input_directories=cls._parse_directories(),
            cpu_workers=int(os.environ.get("ANPR_CPU_WORKERS", "4")),
            gpu_workers=int(os.environ.get("ANPR_GPU_WORKERS", "4")),
            ffmpeg_gpu_workers=int(os.environ.get("ANPR_FFMPEG_GPU_WORKERS", "0")),
            recognition_interval=float(os.environ.get("ANPR_RECOGNITION_INTERVAL", "0.5")),
            video_extension=os.environ.get("ANPR_VIDEO_EXTENSION", ".issvd"),
            frame_skip=int(os.environ.get("ANPR_FRAME_SKIP", "10")),
            confidence_threshold=float(os.environ.get("ANPR_CONFIDENCE_THRESHOLD", "0.25")),
            queue_size_multiplier=int(os.environ.get("ANPR_QUEUE_SIZE_MULTIPLIER", "2")),
            format_cache_enabled=os.environ.get("ANPR_FORMAT_CACHE_ENABLED", "true").lower() == "true",
            timeout_seconds=int(os.environ.get("ANPR_TIMEOUT_SECONDS", "120")),
            output_csv_path=os.environ.get("ANPR_OUTPUT_CSV_PATH", "batch_processing/plates.csv"),
            output_images_dir=os.environ.get("ANPR_OUTPUT_IMAGES_DIR", "data/snapshots"),
            use_torchscript=os.environ.get("ANPR_USE_TORCHSCRIPT", "true").lower() == "true",
            half_precision=os.environ.get("ANPR_HALF_PRECISION", "true").lower() == "true",
            process_timeout=int(os.environ.get("ANPR_PROCESS_TIMEOUT", "3600"))
        )
    
    @classmethod
    def _parse_directories(cls) -> List[str]:
        """Parse input directories from environment variables."""
        directories_env = os.environ.get("ANPR_INPUT_DIRECTORIES", "")
        if not directories_env:
            return []
        return [d.strip() for d in directories_env.split(",") if d.strip()]
    
    def validate(self) -> Dict[str, str]:
        """Validate configuration and return any errors."""
        errors = {}
        
        if self.cpu_workers < 1:
            errors["cpu_workers"] = "Must be at least 1"
        
        if self.gpu_workers < 1:
            errors["gpu_workers"] = "Must be at least 1"
            
        if self.ffmpeg_gpu_workers < 0:
            errors["ffmpeg_gpu_workers"] = "Cannot be negative"
            
        if not 0.1 <= self.confidence_threshold <= 1.0:
            errors["confidence_threshold"] = "Must be between 0.1 and 1.0"
            
        if self.frame_skip < 1:
            errors["frame_skip"] = "Must be at least 1"
            
        if self.queue_size_multiplier < 1:
            errors["queue_size_multiplier"] = "Must be at least 1"
            
        if not self.output_csv_path:
            errors["output_csv_path"] = "Cannot be empty"
            
        if not self.output_images_dir:
            errors["output_images_dir"] = "Cannot be empty"
            
        return errors
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary for serialization."""
        return {
            "input_directories": self.input_directories,
            "cpu_workers": self.cpu_workers,
            "gpu_workers": self.gpu_workers,
            "ffmpeg_gpu_workers": self.ffmpeg_gpu_workers,
            "recognition_interval": self.recognition_interval,
            "video_extension": self.video_extension,
            "frame_skip": self.frame_skip,
            "confidence_threshold": self.confidence_threshold,
            "queue_size_multiplier": self.queue_size_multiplier,
            "format_cache_enabled": self.format_cache_enabled,
            "timeout_seconds": self.timeout_seconds,
            "output_csv_path": self.output_csv_path,
            "output_images_dir": self.output_images_dir,
            "use_torchscript": self.use_torchscript,
            "half_precision": self.half_precision,
            "process_timeout": self.process_timeout
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ANPRBatchConfig":
        """Create configuration from dictionary."""
        return cls(**data)


@dataclass
class ANPRProcessingMetrics:
    """Metrics for ANPR processing performance."""
    
    session_id: str
    start_time: datetime
    files_processed: int = 0
    total_files: int = 0
    processing_times: List[float] = field(default_factory=list)
    error_count: int = 0
    gpu_utilization: List[float] = field(default_factory=list)
    success_count: int = 0
    
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
    
    def get_average_gpu_utilization(self) -> float:
        """Get average GPU utilization."""
        if not self.gpu_utilization:
            return 0.0
        return sum(self.gpu_utilization) / len(self.gpu_utilization)


@dataclass
class ANPRDaemonConfig:
    """Configuration for ANPR daemon operations."""
    
    pid_file: str = "batch_processing/process_videos.pid"
    log_file: str = "batch_processing/process_videos.log"
    max_retries: int = 3
    restart_delay: int = 5
    health_check_interval: int = 30
    max_log_size_mb: int = 100
    log_rotation_count: int = 5
    
    @classmethod
    def from_env(cls) -> "ANPRDaemonConfig":
        """Create daemon configuration from environment variables."""
        return cls(
            pid_file=os.environ.get("ANPR_PID_FILE", "batch_processing/process_videos.pid"),
            log_file=os.environ.get("ANPR_LOG_FILE", "batch_processing/process_videos.log"),
            max_retries=int(os.environ.get("ANPR_MAX_RETRIES", "3")),
            restart_delay=int(os.environ.get("ANPR_RESTART_DELAY", "5")),
            health_check_interval=int(os.environ.get("ANPR_HEALTH_CHECK_INTERVAL", "30")),
            max_log_size_mb=int(os.environ.get("ANPR_MAX_LOG_SIZE_MB", "100")),
            log_rotation_count=int(os.environ.get("ANPR_LOG_ROTATION_COUNT", "5"))
        )