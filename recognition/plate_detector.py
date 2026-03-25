import logging
import os
import numpy as np
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class PlateDetector:
    def __init__(self, weights_path: str = "models/license_plate_detector.pt",
                 device: str = "cpu", confidence: float = 0.5,
                 tensorrt_enabled: bool = True):
        self.weights_path = weights_path
        self.device = device
        self.confidence = confidence
        self.tensorrt_enabled = tensorrt_enabled
        self.model = None
        self._loaded = False

    def _get_engine_path(self, pt_path: str) -> str:
        return pt_path.rsplit(".", 1)[0] + ".engine"

    def _try_load_tensorrt(self, pt_path: str):
        engine_path = self._get_engine_path(pt_path)
        if os.path.exists(engine_path):
            from ultralytics import YOLO
            self.model = YOLO(engine_path)
            logger.info(f"Plate detector loaded (TensorRT): {engine_path}")
            return True
        try:
            from ultralytics import YOLO
            model = YOLO(pt_path)
            dev = int(self.device.split(":")[-1]) if "cuda" in str(self.device) else 0
            model.export(format="engine", half=True, device=dev)
            if os.path.exists(engine_path):
                self.model = YOLO(engine_path)
                logger.info(f"Plate detector exported to TensorRT: {engine_path}")
                return True
        except Exception as e:
            logger.warning(f"TensorRT export failed for plate detector: {e}")
        return False

    def load(self):
        if self._loaded:
            return
        try:
            from ultralytics import YOLO
            if not os.path.exists(self.weights_path):
                logger.warning(f"Plate detector weights not found: {self.weights_path}")
                self._loaded = True
                return

            if self.tensorrt_enabled and self.device != "cpu":
                if self._try_load_tensorrt(self.weights_path):
                    self._loaded = True
                    return

            self.model = YOLO(self.weights_path)
            logger.info(f"Plate detector loaded: {self.weights_path}")
            self._loaded = True
        except ImportError:
            logger.warning("ultralytics not available, using simulation mode")
            self._loaded = True
        except Exception as e:
            logger.error(f"Failed to load plate detector: {e}")
            self._loaded = True

    def detect(self, frame: np.ndarray) -> Dict[str, Any]:
        result = {
            "detected": False,
            "confidence": 0.0,
            "bbox": None,
            "plate_image": None,
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
                if int(class_id) == 0 and score > self.confidence and score > best_score:
                    best_score = score
                    h, w = frame.shape[:2]
                    x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
                    # Clamp coordinates to frame dimensions
                    x1 = max(0, min(x1, w))
                    y1 = max(0, min(y1, h))
                    x2 = max(0, min(x2, w))
                    y2 = max(0, min(y2, h))
                    if x2 <= x1 or y2 <= y1:
                        continue
                    plate_img = frame[y1:y2, x1:x2].copy()
                    best_detection = {
                        "detected": True,
                        "confidence": round(score, 3),
                        "bbox": [x1, y1, x2, y2],
                        "plate_image": plate_img,
                    }

            if best_detection:
                return best_detection

        except Exception as e:
            logger.error(f"Plate detection error: {e}")

        return result

    def update_weights(self, new_weights_path: str):
        if os.path.exists(new_weights_path):
            self.weights_path = new_weights_path
            self._loaded = False
            self.model = None
            self.load()
            logger.info(f"Plate detector weights updated: {new_weights_path}")
