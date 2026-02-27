import logging
import os
import shutil
from typing import Optional, Dict
from datetime import datetime

from db.database import get_db

logger = logging.getLogger(__name__)


class TrainingCollector:
    def __init__(self, training_data_dir: str = "data/training"):
        self.training_data_dir = training_data_dir
        self.db = get_db()
        for stage in ["vehicle", "plate", "ocr"]:
            for sub in ["positive", "negative"]:
                os.makedirs(os.path.join(training_data_dir, stage, sub), exist_ok=True)

    def add_vehicle_sample(self, camera_id: str, event_id: int,
                           image_path: str, is_vehicle: bool):
        sub = "positive" if is_vehicle else "negative"
        dest_dir = os.path.join(self.training_data_dir, "vehicle", sub, camera_id)
        os.makedirs(dest_dir, exist_ok=True)

        filename = os.path.basename(image_path)
        dest_path = os.path.join(dest_dir, filename)
        try:
            if os.path.exists(image_path):
                shutil.copy2(image_path, dest_path)
        except Exception as e:
            logger.error(f"Failed to copy training sample: {e}")
            dest_path = image_path

        self.db.save_training_sample(
            camera_id=camera_id,
            event_id=event_id,
            stage="vehicle",
            image_path=dest_path,
            is_positive=1 if is_vehicle else 0,
        )
        logger.debug(f"Vehicle sample added: camera={camera_id}, positive={is_vehicle}")

    def add_plate_sample(self, camera_id: str, event_id: int,
                         image_path: str, is_plate: bool):
        sub = "positive" if is_plate else "negative"
        dest_dir = os.path.join(self.training_data_dir, "plate", sub, camera_id)
        os.makedirs(dest_dir, exist_ok=True)

        filename = os.path.basename(image_path)
        dest_path = os.path.join(dest_dir, filename)
        try:
            if os.path.exists(image_path):
                shutil.copy2(image_path, dest_path)
        except Exception as e:
            logger.error(f"Failed to copy training sample: {e}")
            dest_path = image_path

        self.db.save_training_sample(
            camera_id=camera_id,
            event_id=event_id,
            stage="plate",
            image_path=dest_path,
            is_positive=1 if is_plate else 0,
        )

    def add_ocr_sample(self, camera_id: str, event_id: int,
                       image_path: str, recognized_text: str,
                       corrected_text: str = None):
        dest_dir = os.path.join(self.training_data_dir, "ocr", "positive", camera_id)
        os.makedirs(dest_dir, exist_ok=True)

        filename = os.path.basename(image_path)
        dest_path = os.path.join(dest_dir, filename)
        try:
            if os.path.exists(image_path):
                shutil.copy2(image_path, dest_path)
        except Exception as e:
            dest_path = image_path

        final_text = corrected_text if corrected_text else recognized_text
        self.db.save_training_sample(
            camera_id=camera_id,
            event_id=event_id,
            stage="ocr",
            image_path=dest_path,
            label=final_text,
            is_positive=1 if not corrected_text else 0,
            corrected_value=corrected_text,
        )

    def get_samples_summary(self) -> Dict:
        summary = {}
        cameras = self.db.get_cameras()
        for cam in cameras:
            cam_id = cam["camera_id"]
            summary[cam_id] = {}
            for stage in ["vehicle", "plate", "ocr"]:
                count = self.db.get_training_samples_count(cam_id, stage, unused_only=True)
                total = self.db.get_training_samples_count(cam_id, stage, unused_only=False)
                summary[cam_id][stage] = {
                    "unused": count,
                    "total": total,
                }
        return summary

    def is_ready_for_training(self, camera_id: str, stage: str,
                               min_samples: int = 50) -> bool:
        count = self.db.get_training_samples_count(camera_id, stage, unused_only=True)
        return count >= min_samples
