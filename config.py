import os
from dataclasses import dataclass, field
from typing import List, Dict, Optional


@dataclass
class CameraConfig:
    camera_id: str
    name: str
    stream_url: str
    gate_device_id: str = ""
    mask_path: str = ""
    weights_vehicle: str = "models/yolo26n.pt"
    weights_plate: str = "models/license_plate_detector.pt"
    enabled: bool = True


@dataclass
class Config:
    telegram_bot_token: str = ""
    telegram_api_id: int = 0
    telegram_api_hash: str = ""

    parsec_domain: str = ""
    parsec_port: int = 10101
    parsec_organization: str = "SYSTEM"
    parsec_bot_username: str = ""
    parsec_bot_password: str = ""
    parsec_admin_username: str = ""
    parsec_admin_password: str = ""

    admin_chat_id: int = 0
    tech_chat_id: int = 0

    db_path: str = "data/gate_control.db"
    models_dir: str = "models"
    training_data_dir: str = "data/training"
    snapshots_dir: str = "data/snapshots"

    recognition_interval: float = 0.5
    confidence_vehicle: float = 0.5
    confidence_plate: float = 0.5
    confidence_ocr: float = 0.4

    gpu_enabled: bool = False
    device: str = "cpu"

    min_training_samples: int = 50

    default_vehicle_model: str = "yolo26n.pt"

    cameras: List[CameraConfig] = field(default_factory=list)

    @classmethod
    def from_env(cls) -> "Config":
        cfg = cls(
            telegram_bot_token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
            telegram_api_id=int(os.environ.get("TELEGRAM_API_ID", "0")),
            telegram_api_hash=os.environ.get("TELEGRAM_API_HASH", ""),
            parsec_domain=os.environ.get("PARSEC_DOMAIN", ""),
            parsec_port=int(os.environ.get("PARSEC_PORT", "10101")),
            parsec_organization=os.environ.get("PARSEC_ORGANIZATION", "SYSTEM"),
            parsec_bot_username=os.environ.get("PARSEC_BOT_USERNAME", ""),
            parsec_bot_password=os.environ.get("PARSEC_BOT_PASSWORD", ""),
            parsec_admin_username=os.environ.get("PARSEC_ADMIN_USERNAME", ""),
            parsec_admin_password=os.environ.get("PARSEC_ADMIN_PASSWORD", ""),
            admin_chat_id=int(os.environ.get("ADMIN_CHAT_ID", "0")),
            tech_chat_id=int(os.environ.get("TECH_CHAT_ID", "0")),
            db_path=os.environ.get("DB_PATH", "data/gate_control.db"),
            models_dir=os.environ.get("MODELS_DIR", "models"),
            training_data_dir=os.environ.get("TRAINING_DATA_DIR", "data/training"),
            snapshots_dir=os.environ.get("SNAPSHOTS_DIR", "data/snapshots"),
            recognition_interval=float(os.environ.get("RECOGNITION_INTERVAL", "0.5")),
            confidence_vehicle=float(os.environ.get("CONFIDENCE_VEHICLE", "0.5")),
            confidence_plate=float(os.environ.get("CONFIDENCE_PLATE", "0.5")),
            confidence_ocr=float(os.environ.get("CONFIDENCE_OCR", "0.4")),
            gpu_enabled=os.environ.get("GPU_ENABLED", "false").lower() == "true",
            device=os.environ.get("DEVICE", "cpu"),
            min_training_samples=int(os.environ.get("MIN_TRAINING_SAMPLES", "50")),
        )

        camera_urls = os.environ.get("CAMERA_URLS", "")
        if camera_urls:
            for i, url in enumerate(camera_urls.split(",")):
                url = url.strip()
                if url:
                    cam_id = f"cam_{i}"
                    cfg.cameras.append(CameraConfig(
                        camera_id=cam_id,
                        name=os.environ.get(f"CAMERA_{i}_NAME", f"Camera {i}"),
                        stream_url=url,
                        gate_device_id=os.environ.get(f"CAMERA_{i}_GATE_ID", ""),
                        mask_path=os.environ.get(f"CAMERA_{i}_MASK", ""),
                    ))

        return cfg


_config: Optional[Config] = None


def get_config() -> Config:
    global _config
    if _config is None:
        _config = Config.from_env()
    return _config
