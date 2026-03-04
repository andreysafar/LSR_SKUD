# Re-export from package so "from config import get_config" and "import config" work.
# The config/ package takes precedence; this file is for any edge case or IDE resolution.
from config.app_config import Config, CameraConfig, get_config
from config.anpr_config import ANPRBatchConfig, ANPRDaemonConfig, ANPRProcessingMetrics

__all__ = [
    "Config",
    "CameraConfig",
    "get_config",
    "ANPRBatchConfig",
    "ANPRDaemonConfig",
    "ANPRProcessingMetrics",
]
