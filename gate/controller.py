import logging
from typing import Optional, Dict
from datetime import datetime

from db.database import get_db
from parsec.api import ParsecAPI

logger = logging.getLogger(__name__)


class GateController:
    def __init__(self, parsec_api: Optional[ParsecAPI] = None):
        self.parsec = parsec_api
        self.db = get_db()
        self._session_id = None

    def check_plate_and_open(self, camera_id: str, plate_number: str,
                              event_id: int = None) -> Dict:
        result = {
            "plate": plate_number,
            "pass_found": False,
            "gate_opened": False,
            "pass_id": None,
            "details": "",
        }

        plate_clean = plate_number.upper().replace(" ", "")
        active_pass = self.db.find_active_pass_by_plate(plate_clean)

        if not active_pass:
            result["details"] = "No active pass found for this plate"
            self.db.save_gate_event(
                camera_id=camera_id,
                plate_number=plate_clean,
                action="check",
                success=False,
                details="No active pass"
            )
            return result

        result["pass_found"] = True
        result["pass_id"] = active_pass["id"]

        camera = None
        cameras = self.db.get_cameras()
        for cam in cameras:
            if cam["camera_id"] == camera_id:
                camera = cam
                break

        gate_device_id = camera.get("gate_device_id", "") if camera else ""

        if gate_device_id and self.parsec:
            try:
                if not self._session_id:
                    self._session_id = self.parsec.open_admin_session()

                if self._session_id:
                    success = self.parsec.open_door(self._session_id, gate_device_id)
                    result["gate_opened"] = success
                    result["details"] = "Gate opened successfully" if success else "Failed to open gate"
                else:
                    result["details"] = "Failed to get Parsec session"
            except Exception as e:
                result["details"] = f"Gate control error: {e}"
                logger.error(f"Gate control error: {e}")
        else:
            result["gate_opened"] = True
            result["details"] = "Gate open signal sent (simulated)" if not gate_device_id else "Parsec not configured"

        self.db.save_gate_event(
            camera_id=camera_id,
            plate_number=plate_clean,
            pass_id=active_pass["id"],
            action="open",
            success=result["gate_opened"],
            details=result["details"]
        )

        if event_id:
            self.db.update_recognition_event(
                event_id,
                matched_pass_id=active_pass["id"],
                gate_opened=1 if result["gate_opened"] else 0
            )

        logger.info(f"Gate control for {plate_clean}: opened={result['gate_opened']}")
        return result
