import logging
import json
from typing import Dict, Optional, Callable

from db.database import get_db
from training.collector import TrainingCollector
from training.manager import TrainingManager

logger = logging.getLogger(__name__)


class AdminHandler:
    def __init__(self, tech_chat_id: int, training_collector: TrainingCollector,
                 training_manager: TrainingManager):
        self.tech_chat_id = tech_chat_id
        self.collector = training_collector
        self.manager = training_manager
        self.db = get_db()
        self._pending_corrections: Dict[int, Dict] = {}

    def create_review_message(self, event_id: int, camera_id: str,
                               result_data: Dict) -> Dict:
        text_parts = [
            f"🔍 Recognition Event #{event_id}",
            f"📷 Camera: {camera_id}",
            f"⏰ Time: {result_data.get('timestamp', 'N/A')}",
            "",
        ]

        if result_data.get("vehicle_detected"):
            text_parts.append(
                f"🚗 Vehicle: YES (confidence: {result_data.get('vehicle_confidence', 0):.1%})"
            )
            text_parts.append(f"   Class: {result_data.get('vehicle_class', 'N/A')}")
        else:
            text_parts.append("🚗 Vehicle: NO")

        text_parts.append("")

        if result_data.get("plate_detected"):
            text_parts.append(
                f"🔲 Plate: YES (confidence: {result_data.get('plate_confidence', 0):.1%})"
            )
        else:
            text_parts.append("🔲 Plate: NOT DETECTED")

        text_parts.append("")

        if result_data.get("ocr_text"):
            text_parts.append(f"📝 OCR Result: {result_data['ocr_text']}")
            text_parts.append(
                f"   Confidence: {result_data.get('ocr_confidence', 0):.1%}"
            )
            if result_data.get("final_plate"):
                text_parts.append(f"   Normalized: {result_data['final_plate']}")
        else:
            text_parts.append("📝 OCR: NO TEXT")

        text_parts.extend(["", "Please confirm or correct:"])

        message_data = {
            "text": "\n".join(text_parts),
            "event_id": event_id,
            "camera_id": camera_id,
            "buttons": self._get_review_buttons(event_id, result_data),
            "image_path": result_data.get("frame_path"),
            "plate_image_path": result_data.get("plate_image_path"),
        }

        self._pending_corrections[event_id] = {
            "camera_id": camera_id,
            "result_data": result_data,
            "status": "pending",
        }

        return message_data

    def _get_review_buttons(self, event_id: int, result_data: Dict) -> list:
        buttons = []

        buttons.append([
            {"text": "✅ Vehicle YES", "data": f"rv:{event_id}:v:1"},
            {"text": "❌ Vehicle NO", "data": f"rv:{event_id}:v:0"},
        ])

        if result_data.get("vehicle_detected"):
            buttons.append([
                {"text": "✅ Plate YES", "data": f"rv:{event_id}:p:1"},
                {"text": "❌ Plate NO", "data": f"rv:{event_id}:p:0"},
            ])

        if result_data.get("ocr_text"):
            buttons.append([
                {"text": f"✅ OCR OK: {result_data['ocr_text'][:20]}", "data": f"rv:{event_id}:o:1"},
                {"text": "✏️ Correct OCR", "data": f"rv:{event_id}:o:0"},
            ])

        buttons.append([
            {"text": "✅ All Correct", "data": f"rv:{event_id}:all:1"},
            {"text": "🗑 Skip", "data": f"rv:{event_id}:skip:0"},
        ])

        return buttons

    def process_callback(self, callback_data: str, message_id: int = None) -> Dict:
        result = {
            "action": "",
            "event_id": 0,
            "response_text": "",
            "need_text_input": False,
        }

        parts = callback_data.split(":")
        if len(parts) < 4 or parts[0] != "rv":
            return result

        event_id = int(parts[1])
        stage = parts[2]
        value = int(parts[3])

        result["event_id"] = event_id

        pending = self._pending_corrections.get(event_id)
        if not pending:
            result["response_text"] = "Event not found or already processed"
            return result

        camera_id = pending["camera_id"]
        event_data = pending["result_data"]

        if stage == "skip":
            self._pending_corrections.pop(event_id, None)
            result["action"] = "skipped"
            result["response_text"] = f"Event #{event_id} skipped"
            return result

        if stage == "all":
            self._process_all_correct(event_id, camera_id, event_data)
            self._pending_corrections.pop(event_id, None)
            result["action"] = "all_confirmed"
            result["response_text"] = f"✅ Event #{event_id}: All stages confirmed"
            self._check_training_ready(camera_id)
            return result

        if stage == "v":
            is_vehicle = bool(value)
            self.collector.add_vehicle_sample(
                camera_id, event_id,
                event_data.get("frame_path", ""),
                is_vehicle,
            )
            self.db.update_recognition_event(event_id, admin_vehicle_confirm=value)
            result["action"] = "vehicle_confirmed"
            result["response_text"] = f"Vehicle: {'YES' if is_vehicle else 'NO'} recorded"

        elif stage == "p":
            is_plate = bool(value)
            img_path = event_data.get("plate_image_path") or event_data.get("frame_path", "")
            self.collector.add_plate_sample(camera_id, event_id, img_path, is_plate)
            self.db.update_recognition_event(event_id, admin_plate_confirm=value)
            result["action"] = "plate_confirmed"
            result["response_text"] = f"Plate: {'YES' if is_plate else 'NO'} recorded"

        elif stage == "o":
            if value == 1:
                ocr_text = event_data.get("ocr_text", "")
                img_path = event_data.get("plate_image_path", "")
                self.collector.add_ocr_sample(camera_id, event_id, img_path, ocr_text)
                self.db.update_recognition_event(
                    event_id, admin_ocr_confirm=1, ocr_corrected=ocr_text
                )
                result["action"] = "ocr_confirmed"
                result["response_text"] = f"OCR confirmed: {ocr_text}"
            else:
                result["action"] = "ocr_correction_needed"
                result["need_text_input"] = True
                result["response_text"] = (
                    f"Please type the correct plate number for event #{event_id}:"
                )

        self.db.update_recognition_event(event_id, admin_reviewed=1)
        self._check_training_ready(camera_id)
        return result

    def process_ocr_correction(self, event_id: int, corrected_text: str) -> Dict:
        pending = self._pending_corrections.get(event_id)
        if not pending:
            return {"success": False, "message": "Event not found"}

        camera_id = pending["camera_id"]
        event_data = pending["result_data"]
        original_text = event_data.get("ocr_text", "")
        img_path = event_data.get("plate_image_path", "")

        self.collector.add_ocr_sample(
            camera_id, event_id, img_path,
            original_text, corrected_text,
        )
        self.db.update_recognition_event(
            event_id, admin_ocr_confirm=1, ocr_corrected=corrected_text
        )

        self._check_training_ready(camera_id)

        return {
            "success": True,
            "message": f"OCR corrected: {original_text} → {corrected_text}",
        }

    def _process_all_correct(self, event_id: int, camera_id: str, event_data: Dict):
        if event_data.get("frame_path"):
            self.collector.add_vehicle_sample(
                camera_id, event_id,
                event_data["frame_path"],
                event_data.get("vehicle_detected", False),
            )

        if event_data.get("plate_image_path") or event_data.get("frame_path"):
            img = event_data.get("plate_image_path") or event_data.get("frame_path")
            self.collector.add_plate_sample(
                camera_id, event_id, img,
                event_data.get("plate_detected", False),
            )

        if event_data.get("ocr_text") and event_data.get("plate_image_path"):
            self.collector.add_ocr_sample(
                camera_id, event_id,
                event_data["plate_image_path"],
                event_data["ocr_text"],
            )

        self.db.update_recognition_event(
            event_id,
            admin_vehicle_confirm=1 if event_data.get("vehicle_detected") else 0,
            admin_plate_confirm=1 if event_data.get("plate_detected") else 0,
            admin_ocr_confirm=1 if event_data.get("ocr_text") else 0,
            admin_reviewed=1,
        )

    def _check_training_ready(self, camera_id: str):
        triggered = self.manager.check_and_trigger_training(camera_id)
        for stage, ready in triggered.items():
            if ready:
                logger.info(f"Training triggered for {camera_id}/{stage}")
