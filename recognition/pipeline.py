import logging
import os
import threading
import time
import json
from datetime import datetime
from typing import Dict, Any, Optional, Callable, List

from recognition.vehicle_detector import VehicleDetector
from recognition.plate_detector import PlateDetector
from recognition.ocr_engine import OCREngine
from recognition.camera_manager import CameraManager
from recognition.plate_tracker import PlateTracker

logger = logging.getLogger(__name__)


class RecognitionResult:
    def __init__(self):
        self.camera_id = ""
        self.timestamp = ""
        self.frame_path = ""
        self.vehicle_detected = False
        self.vehicle_confidence = 0.0
        self.vehicle_class = ""
        self.vehicle_bbox = None
        self.plate_detected = False
        self.plate_confidence = 0.0
        self.plate_bbox = None
        self.plate_image_path = ""
        self.ocr_text = ""
        self.ocr_confidence = 0.0
        self.normalized_plate = ""
        self.is_valid_ru = False
        self.is_duplicate: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "camera_id": self.camera_id,
            "timestamp": self.timestamp,
            "frame_path": self.frame_path,
            "vehicle_detected": self.vehicle_detected,
            "vehicle_confidence": self.vehicle_confidence,
            "vehicle_class": self.vehicle_class,
            "vehicle_bbox": json.dumps(self.vehicle_bbox) if self.vehicle_bbox else None,
            "plate_detected": self.plate_detected,
            "plate_confidence": self.plate_confidence,
            "plate_bbox": json.dumps(self.plate_bbox) if self.plate_bbox else None,
            "plate_image_path": self.plate_image_path,
            "ocr_text": self.ocr_text,
            "ocr_confidence": self.ocr_confidence,
            "final_plate": self.normalized_plate,
        }


class CameraDetectors:
    def __init__(self, camera_id: str, config: Dict[str, Any],
                 shared_ocr: Optional[OCREngine] = None):
        self.camera_id = camera_id
        weights_dir = config.get("models_dir", "models")
        cam_weights_v = os.path.join(weights_dir, f"{camera_id}_vehicle.pt")
        cam_weights_p = os.path.join(weights_dir, f"{camera_id}_plate.pt")

        vehicle_weights = cam_weights_v if os.path.exists(cam_weights_v) else config.get("weights_vehicle", "models/yolo26n.pt")
        plate_weights = cam_weights_p if os.path.exists(cam_weights_p) else config.get("weights_plate", "models/license_plate_detector.pt")

        if not os.path.exists(cam_weights_v):
            logger.warning(f"Per-camera vehicle weights not found for {camera_id}, "
                           f"falling back to default: {vehicle_weights}")
        if not os.path.exists(cam_weights_p):
            logger.warning(f"Per-camera plate weights not found for {camera_id}, "
                           f"falling back to default: {plate_weights}")

        device = config.get("device", "cpu")
        tensorrt_enabled = config.get("tensorrt_enabled", True)

        self.vehicle_detector = VehicleDetector(
            weights_path=vehicle_weights,
            device=device,
            confidence=config.get("confidence_vehicle", 0.5),
            tensorrt_enabled=tensorrt_enabled,
        )
        self.plate_detector = PlateDetector(
            weights_path=plate_weights,
            device=device,
            confidence=config.get("confidence_plate", 0.5),
            tensorrt_enabled=tensorrt_enabled,
        )
        self.ocr_engine = shared_ocr or OCREngine(
            gpu=config.get("gpu_enabled", False),
            confidence=config.get("confidence_ocr", 0.4)
        )
        self.plate_tracker = PlateTracker(
            cooldown_seconds=config.get("plate_cooldown_seconds", 30.0),
            vote_threshold=config.get("plate_vote_threshold", 2),
        )

    def load_all(self):
        self.vehicle_detector.load()
        self.plate_detector.load()
        self.ocr_engine.load()


class RecognitionPipeline:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.camera_manager = CameraManager()
        self.detectors: Dict[str, CameraDetectors] = {}
        self._running = False
        self._on_result_callback: Optional[Callable] = None
        self._process_interval = config.get("recognition_interval", 0.5)
        self._last_process_time: Dict[str, float] = {}
        self.snapshots_dir = config.get("snapshots_dir", "data/snapshots")
        os.makedirs(self.snapshots_dir, exist_ok=True)
        # Shared OCR engine singleton for cross-camera batching
        ocr_backend = config.get("ocr_backend", "easyocr")
        self.shared_ocr = OCREngine(
            languages=config.get("ocr_languages", ["en"]),
            gpu=config.get("gpu", False),
            confidence=config.get("ocr_confidence", 0.4),
            backend=ocr_backend,
        )

    def add_camera(self, camera_id: str, stream_url: str, name: str = "",
                   mask_path: str = ""):
        self.camera_manager.add_camera(camera_id, stream_url, name, mask_path)
        self.detectors[camera_id] = CameraDetectors(camera_id, self.config,
                                                      shared_ocr=self.shared_ocr)

    def set_result_callback(self, callback: Callable):
        self._on_result_callback = callback

    def _cleanup_trackers(self):
        """Cleanup stale plate tracks across all cameras."""
        for camera_id, det in self.detectors.items():
            det.plate_tracker.cleanup(max_age_seconds=300.0)

    def _cleanup_timer_loop(self):
        """Periodic cleanup thread: runs every 60 seconds while pipeline is active."""
        while self._running:
            time.sleep(60)
            if self._running:
                try:
                    self._cleanup_trackers()
                except Exception as e:
                    logger.error(f"Plate tracker cleanup error: {e}")

    def start(self):
        self._running = True
        self.camera_manager.set_frame_callback(self._on_frame)
        for det in self.detectors.values():
            det.load_all()
        self.camera_manager.start()
        cleanup_thread = threading.Thread(
            target=self._cleanup_timer_loop, daemon=True, name="plate-tracker-cleanup"
        )
        cleanup_thread.start()
        logger.info("Recognition pipeline started")

    def stop(self):
        self._running = False
        self.camera_manager.stop()
        logger.info("Recognition pipeline stopped")

    def _on_frame(self, camera_id: str, frame):
        now = time.time()
        last = self._last_process_time.get(camera_id, 0)
        if now - last < self._process_interval:
            return
        self._last_process_time[camera_id] = now

        try:
            result = self.process_frame(camera_id, frame)
            if result and result.vehicle_detected and self._on_result_callback:
                self._on_result_callback(result)
        except Exception as e:
            logger.error(f"Pipeline processing error for {camera_id}: {e}")

    def process_frame(self, camera_id: str, frame) -> Optional[RecognitionResult]:
        det = self.detectors.get(camera_id)
        if not det:
            return None

        result = RecognitionResult()
        result.camera_id = camera_id
        result.timestamp = datetime.now().isoformat()

        cam = self.camera_manager.cameras.get(camera_id)
        if cam and cam.mask_path:
            frame = cam.apply_mask(frame, cam.mask_path)

        vehicle = det.vehicle_detector.detect(frame)
        result.vehicle_detected = vehicle["detected"]
        result.vehicle_confidence = vehicle["confidence"]
        result.vehicle_class = vehicle.get("class_name", "")
        result.vehicle_bbox = vehicle.get("bbox")

        if not vehicle["detected"]:
            return result

        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        frame_filename = f"{camera_id}_{timestamp_str}.jpg"
        frame_path = os.path.join(self.snapshots_dir, frame_filename)
        try:
            import cv2
            cv2.imwrite(frame_path, frame)
            result.frame_path = frame_path
        except Exception:
            pass

        plate = det.plate_detector.detect(frame)
        result.plate_detected = plate["detected"]
        result.plate_confidence = plate["confidence"]
        result.plate_bbox = plate.get("bbox")

        if not plate["detected"]:
            return result

        if plate.get("plate_image") is not None:
            plate_filename = f"{camera_id}_{timestamp_str}_plate.jpg"
            plate_path = os.path.join(self.snapshots_dir, plate_filename)
            try:
                import cv2
                cv2.imwrite(plate_path, plate["plate_image"])
                result.plate_image_path = plate_path
            except Exception:
                pass

            ocr = det.ocr_engine.recognize(plate["plate_image"])
            result.ocr_text = ocr["text"]
            result.ocr_confidence = ocr["confidence"]
            result.normalized_plate = ocr["normalized"]
            result.is_valid_ru = ocr["is_valid_ru"]

            if result.normalized_plate:
                track_result = det.plate_tracker.update(
                    result.normalized_plate, result.ocr_confidence
                )

                if not track_result["is_new_event"]:
                    # Duplicate detection within cooldown - skip gate trigger
                    logger.debug(
                        f"Plate {result.normalized_plate} duplicate suppressed "
                        f"(camera {camera_id})"
                    )
                    result.is_duplicate = True
                else:
                    # Use best reading from tracker for improved accuracy
                    result.normalized_plate = track_result["best_plate"]

        return result

    def update_camera_weights(self, camera_id: str, stage: str, weights_path: str):
        det = self.detectors.get(camera_id)
        if not det:
            return
        if stage == "vehicle":
            det.vehicle_detector.update_weights(weights_path)
        elif stage == "plate":
            det.plate_detector.update_weights(weights_path)
        logger.info(f"Updated {stage} weights for camera {camera_id}")

    def get_status(self) -> Dict[str, Any]:
        cam_status = self.camera_manager.get_camera_status()
        return {
            "running": self._running,
            "cameras": cam_status,
            "detectors_loaded": {cid: True for cid in self.detectors},
        }
