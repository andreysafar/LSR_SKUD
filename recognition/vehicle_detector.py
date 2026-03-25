import logging
import os
import numpy as np
from typing import Tuple, Optional, Dict, Any

logger = logging.getLogger(__name__)

VEHICLE_CLASSES = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}


class VehicleDetector:
    def __init__(self, weights_path: str = "models/yolo26n.pt",
                 device: str = "cpu", confidence: float = 0.5,
                 tensorrt_enabled: bool = True):
        self.weights_path = weights_path
        self.device = device
        self.confidence = confidence
        self.tensorrt_enabled = tensorrt_enabled
        self.model = None
        self._loaded = False

    def _get_engine_path(self, pt_path: str) -> str:
        """Путь к TensorRT engine файлу."""
        return pt_path.rsplit(".", 1)[0] + ".engine"

    def _try_load_tensorrt(self, pt_path: str):
        """Попытка загрузить TensorRT engine, при отсутствии — export из .pt."""
        engine_path = self._get_engine_path(pt_path)
        if os.path.exists(engine_path):
            try:
                from ultralytics import YOLO
                self.model = YOLO(engine_path)
                logger.info(f"Vehicle detector loaded (TensorRT): {engine_path}")
                return True
            except Exception as e:
                logger.warning(f"Vehicle detector: failed to load existing TensorRT engine '{engine_path}': {e}")
                return False
        # Попытка export
        try:
            import tensorrt  # noqa: F401 — verify TensorRT is installed before attempting export
        except ImportError:
            logger.warning(
                "Vehicle detector: 'tensorrt' package not found — skipping TensorRT export, "
                "falling back to .pt model."
            )
            return False
        try:
            from ultralytics import YOLO
            logger.info(
                f"Vehicle detector: starting TensorRT export for '{pt_path}' "
                f"(this may take several minutes on first run) …"
            )
            model = YOLO(pt_path)
            dev = int(self.device.split(":")[-1]) if "cuda" in str(self.device) else 0
            model.export(format="engine", half=True, device=dev)
            if os.path.exists(engine_path):
                self.model = YOLO(engine_path)
                logger.info(f"Vehicle detector exported and loaded (TensorRT): {engine_path}")
                return True
            logger.warning(
                f"Vehicle detector: TensorRT export completed but engine file not found at '{engine_path}'. "
                "Falling back to .pt model."
            )
        except Exception as e:
            logger.warning(
                f"Vehicle detector: TensorRT export failed — falling back to .pt model. Error: {e}"
            )
        return False

    def load(self):
        if self._loaded:
            return
        try:
            from ultralytics import YOLO
            weights = self.weights_path if os.path.exists(self.weights_path) else "yolo26n.pt"

            # TensorRT → TorchScript → .pt
            if self.tensorrt_enabled and self.device != "cpu":
                if self._try_load_tensorrt(weights):
                    self._loaded = True
                    return

            # Fallback: стандартная загрузка .pt
            self.model = YOLO(weights)
            logger.info(f"Vehicle detector loaded: {weights}")
            self._loaded = True
        except ImportError:
            logger.warning("ultralytics not available, using simulation mode")
            self._loaded = True
        except Exception as e:
            logger.error(f"Failed to load vehicle detector: {e}")
            self._loaded = True

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
