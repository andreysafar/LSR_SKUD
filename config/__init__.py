"""Configuration module for LSR_SKUD with ANPR integration."""

from .anpr_config import (
    ANPRBatchConfig,
    ANPRProcessingMetrics,
    ANPRDaemonConfig
)

__all__ = [
    "ANPRBatchConfig",
    "ANPRProcessingMetrics", 
    "ANPRDaemonConfig"
]