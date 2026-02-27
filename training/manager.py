import logging
import os
import json
import subprocess
from typing import Dict, Optional, List
from datetime import datetime

from db.database import get_db

logger = logging.getLogger(__name__)


class TrainingManager:
    def __init__(self, training_data_dir: str = "data/training",
                 models_dir: str = "models",
                 min_samples: int = 50):
        self.training_data_dir = training_data_dir
        self.models_dir = models_dir
        self.min_samples = min_samples
        self.db = get_db()
        os.makedirs(models_dir, exist_ok=True)

    def check_and_trigger_training(self, camera_id: str) -> Dict[str, bool]:
        triggered = {}
        for stage in ["vehicle", "plate", "ocr"]:
            count = self.db.get_training_samples_count(camera_id, stage, unused_only=True)
            if count >= self.min_samples:
                triggered[stage] = True
                self._create_training_session(camera_id, stage, count)
            else:
                triggered[stage] = False
        return triggered

    def _create_training_session(self, camera_id: str, stage: str,
                                  samples_count: int):
        session_id = self.db.save_training_session(
            camera_id=camera_id,
            stage=stage,
            samples_count=samples_count,
        )

        samples = self.db.get_training_samples(camera_id, stage, unused_only=True)
        self._export_training_data(camera_id, stage, samples)
        sample_ids = [s["id"] for s in samples]
        self.db.mark_samples_used(sample_ids)

        logger.info(f"Training session {session_id} created for {camera_id}/{stage} "
                     f"with {samples_count} samples")
        return session_id

    def _export_training_data(self, camera_id: str, stage: str,
                               samples: List[Dict]):
        export_dir = os.path.join(self.training_data_dir, "export",
                                   camera_id, stage)
        os.makedirs(export_dir, exist_ok=True)

        manifest = {
            "camera_id": camera_id,
            "stage": stage,
            "samples_count": len(samples),
            "exported_at": datetime.now().isoformat(),
            "samples": [],
        }

        for sample in samples:
            manifest["samples"].append({
                "id": sample["id"],
                "image_path": sample["image_path"],
                "label": sample.get("label"),
                "is_positive": sample.get("is_positive"),
                "corrected_value": sample.get("corrected_value"),
            })

        manifest_path = os.path.join(export_dir, "manifest.json")
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)

        logger.info(f"Training data exported to {export_dir}")

    def generate_docker_compose(self) -> str:
        compose = {
            "version": "3.8",
            "services": {
                "trainer": {
                    "build": {
                        "context": "./training",
                        "dockerfile": "Dockerfile",
                    },
                    "volumes": [
                        "./data/training:/app/data",
                        "./models:/app/models",
                    ],
                    "environment": [
                        "CUDA_VISIBLE_DEVICES=0",
                    ],
                    "deploy": {
                        "resources": {
                            "reservations": {
                                "devices": [{
                                    "driver": "nvidia",
                                    "count": 1,
                                    "capabilities": ["gpu"],
                                }]
                            }
                        }
                    },
                    "command": "python train.py",
                }
            }
        }

        import yaml
        return yaml.dump(compose, default_flow_style=False, allow_unicode=True)

    def get_training_status(self) -> Dict:
        sessions = self.db.get_training_sessions(limit=50)
        status = {
            "sessions": sessions,
            "pending_by_camera": {},
        }

        cameras = self.db.get_cameras()
        for cam in cameras:
            cam_id = cam["camera_id"]
            status["pending_by_camera"][cam_id] = {}
            for stage in ["vehicle", "plate", "ocr"]:
                count = self.db.get_training_samples_count(cam_id, stage, unused_only=True)
                status["pending_by_camera"][cam_id][stage] = {
                    "pending_samples": count,
                    "ready": count >= self.min_samples,
                    "min_required": self.min_samples,
                }

        return status
