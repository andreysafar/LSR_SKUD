import logging
import os
import numpy as np
from typing import Tuple, Optional, Dict, Any

logger = logging.getLogger(__name__)

VEHICLE_CLASSES = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}


class VehicleDetector:
    def __init__(self, weights_path: str = "models/yolov8n.pt",
                 device: str = "cpu", confidence: float = 0.5):
        self.weights_path = weights_path
        self.device = device
        self.confidence = confidence
        self.model = None
        self._loaded = False

    def load(self):
        if self._loaded:
            return
        try:
            from ultralytics import YOLO
            if os.path.exists(self.weights_path):
                self.model = YOLO(self.weights_path)
                logger.info(f"Vehicle detector loaded: {self.weights_path}")
            else:
                self.model = YOLO("yolov8n.pt")
                logger.info("Vehicle detector loaded with default yolov8n.pt")
            self._loaded = True
        except ImportError:
            logger.warning("ultralytics not available, using simulation mode")
            self._loaded = True
        except Exception as e:
            logger.error(f"Failed to load vehicle detector: {e}")

    def detect(self, frame: np.ndarray) -> Dict[str, Any]:
        result = {
            "detected": False,
            "confidence": 0.0,
            "class_id": None,
            "class_name": None,
            "bbox": None,
        }

        if not self._loaded:
            self.load()

        if self.model is None:
            return result

        try:
            results = self.model(frame, device=self.device, verbose=False)[0]

            best_score = 0
            best_detection = None

            for det in results.boxes.data.tolist():
                x1, y1, x2, y2, score, class_id = det
                class_id = int(class_id)
                if class_id in VEHICLE_CLASSES and score > self.confidence and score > best_score:
                    best_score = score
                    best_detection = {
                        "detected": True,
                        "confidence": round(score, 3),
                        "class_id": class_id,
                        "class_name": VEHICLE_CLASSES[class_id],
                        "bbox": [int(x1), int(y1), int(x2), int(y2)],
                    }

            if best_detection:
                return best_detection

        except Exception as e:
            logger.error(f"Vehicle detection error: {e}")

        return result

    def update_weights(self, new_weights_path: str):
        if os.path.exists(new_weights_path):
            self.weights_path = new_weights_path
            self._loaded = False
            self.model = None
            self.load()
            logger.info(f"Vehicle detector weights updated: {new_weights_path}")
