import logging
import threading
import time
import os
import numpy as np
from typing import Dict, Optional, Callable
from datetime import datetime

logger = logging.getLogger(__name__)


class CameraStream:
    def __init__(self, camera_id: str, stream_url: str, name: str = ""):
        self.camera_id = camera_id
        self.stream_url = stream_url
        self.name = name or camera_id
        self.cap = None
        self.last_frame = None
        self.last_frame_time = None
        self.status = "offline"
        self.error = None
        self.frame_count = 0
        self._lock = threading.Lock()

    def connect(self) -> bool:
        try:
            import cv2
            self.cap = cv2.VideoCapture(self.stream_url)
            if self.cap.isOpened():
                self.status = "online"
                logger.info(f"Camera {self.camera_id} connected: {self.stream_url}")
                return True
            else:
                self.status = "error"
                self.error = "Failed to open stream"
                return False
        except ImportError:
            logger.warning("cv2 not available")
            self.status = "error"
            self.error = "OpenCV not available"
            return False
        except Exception as e:
            self.status = "error"
            self.error = str(e)
            logger.error(f"Camera {self.camera_id} connection failed: {e}")
            return False

    def read_frame(self) -> Optional[np.ndarray]:
        if self.cap is None or not self.cap.isOpened():
            return None
        try:
            ret, frame = self.cap.read()
            if ret:
                with self._lock:
                    self.last_frame = frame
                    self.last_frame_time = datetime.now()
                    self.frame_count += 1
                    self.status = "online"
                return frame
            else:
                self.status = "error"
                self.error = "Failed to read frame"
                return None
        except Exception as e:
            self.status = "error"
            self.error = str(e)
            return None

    def get_last_frame(self) -> Optional[np.ndarray]:
        with self._lock:
            return self.last_frame.copy() if self.last_frame is not None else None

    def disconnect(self):
        if self.cap:
            self.cap.release()
        self.status = "offline"
        self.cap = None

    def apply_mask(self, frame: np.ndarray, mask_path: str) -> np.ndarray:
        if not mask_path or not os.path.exists(mask_path):
            return frame
        try:
            import cv2
            mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)
            if mask is not None:
                mask = cv2.resize(mask, (frame.shape[1], frame.shape[0]))
                return cv2.bitwise_and(frame, frame, mask=mask.astype(np.uint8))
        except Exception as e:
            logger.error(f"Failed to apply mask: {e}")
        return frame


class CameraManager:
    def __init__(self):
        self.cameras: Dict[str, CameraStream] = {}
        self._running = False
        self._threads: Dict[str, threading.Thread] = {}
        self._on_frame_callback: Optional[Callable] = None

    def add_camera(self, camera_id: str, stream_url: str, name: str = ""):
        cam = CameraStream(camera_id, stream_url, name)
        self.cameras[camera_id] = cam
        logger.info(f"Camera added: {camera_id} ({name})")

    def remove_camera(self, camera_id: str):
        if camera_id in self.cameras:
            self.cameras[camera_id].disconnect()
            del self.cameras[camera_id]
            if camera_id in self._threads:
                del self._threads[camera_id]

    def set_frame_callback(self, callback: Callable):
        self._on_frame_callback = callback

    def start(self):
        self._running = True
        for cam_id, cam in self.cameras.items():
            t = threading.Thread(target=self._capture_loop, args=(cam_id,), daemon=True)
            self._threads[cam_id] = t
            t.start()
        logger.info(f"Camera manager started with {len(self.cameras)} cameras")

    def stop(self):
        self._running = False
        for cam in self.cameras.values():
            cam.disconnect()
        logger.info("Camera manager stopped")

    def _capture_loop(self, camera_id: str):
        cam = self.cameras.get(camera_id)
        if not cam:
            return

        reconnect_delay = 5
        while self._running:
            if not cam.connect():
                logger.warning(f"Camera {camera_id} reconnecting in {reconnect_delay}s...")
                time.sleep(reconnect_delay)
                continue

            while self._running and cam.status == "online":
                frame = cam.read_frame()
                if frame is not None and self._on_frame_callback:
                    try:
                        self._on_frame_callback(camera_id, frame)
                    except Exception as e:
                        logger.error(f"Frame callback error for {camera_id}: {e}")
                time.sleep(0.1)

            cam.disconnect()
            time.sleep(reconnect_delay)

    def get_camera_status(self) -> Dict[str, Dict]:
        status = {}
        for cam_id, cam in self.cameras.items():
            status[cam_id] = {
                "name": cam.name,
                "status": cam.status,
                "error": cam.error,
                "frame_count": cam.frame_count,
                "last_frame_time": cam.last_frame_time.isoformat() if cam.last_frame_time else None,
            }
        return status

    def get_snapshot(self, camera_id: str) -> Optional[np.ndarray]:
        cam = self.cameras.get(camera_id)
        if cam:
            return cam.get_last_frame()
        return None
