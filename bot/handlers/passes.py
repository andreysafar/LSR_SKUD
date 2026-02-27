import logging
import re
import secrets
from datetime import datetime, timedelta
from typing import Dict, Optional, List

logger = logging.getLogger(__name__)

RU_PLATE_PATTERN = re.compile(
    r'^[АВЕКМНОРСТУХ]\d{3}[АВЕКМНОРСТУХ]{2}\d{2,3}$'
)

LATIN_TO_CYRILLIC = {
    'A': 'А', 'B': 'В', 'C': 'С', 'E': 'Е', 'H': 'Н',
    'K': 'К', 'M': 'М', 'O': 'О', 'P': 'Р', 'T': 'Т',
    'X': 'Х', 'Y': 'У',
}


def normalize_plate_input(text: str) -> str:
    text = text.upper().strip()
    text = re.sub(r'[^A-ZА-Я0-9]', '', text)
    result = []
    for ch in text:
        result.append(LATIN_TO_CYRILLIC.get(ch, ch))
    return ''.join(result)


def plate_to_hex_code(plate: str) -> str:
    plate_bytes = plate.encode("utf-8")
    hex_str = plate_bytes.hex().upper()
    if len(hex_str) < 8:
        hex_str = hex_str.ljust(8, "0")
    elif len(hex_str) > 8:
        hex_str = hex_str[:8]
    return hex_str


class PassHandler:
    def __init__(self, db, parsec_api):
        self.db = db
        self.parsec = parsec_api

    def _compute_validity(self, duration: str):
        now = datetime.now()
        if duration == "day_end":
            valid_from = now.strftime("%Y-%m-%d %H:%M:%S")
            valid_to = now.replace(hour=23, minute=59, second=59).strftime("%Y-%m-%d %H:%M:%S")
            duration_text = "until end of day"
        elif duration == "3hours":
            valid_from = now.strftime("%Y-%m-%d %H:%M:%S")
            valid_to = (now + timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S")
            duration_text = "for 3 hours"
        elif duration == "24hours":
            valid_from = now.strftime("%Y-%m-%d %H:%M:%S")
            valid_to = (now + timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
            duration_text = "for 24 hours"
        elif duration == "week":
            valid_from = now.strftime("%Y-%m-%d %H:%M:%S")
            valid_to = (now + timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
            duration_text = "for 1 week"
        else:
            valid_from = now.strftime("%Y-%m-%d %H:%M:%S")
            valid_to = (now + timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
            duration_text = "for 24 hours"
        return valid_from, valid_to, duration_text

    def create_vehicle_pass(self, user_id: int, plate_number: str,
                             access_group_id: str = None,
                             duration: str = "day_end") -> Dict:
        result = {
            "success": False,
            "message": "",
            "pass_data": None,
        }

        plate_clean = normalize_plate_input(plate_number)
        if not plate_clean:
            result["message"] = "Invalid plate number"
            return result

        user = self.db.get_user(user_id)
        if not user:
            result["message"] = "User not authenticated"
            return result

        valid_from, valid_to, duration_text = self._compute_validity(duration)

        parsec_identifier_code = None
        if self.parsec and self.parsec.host and access_group_id:
            try:
                session_data = self.parsec.open_admin_session()
                if session_data:
                    session_id = session_data["session_id"]
                    plate_code = self.parsec.get_unique_card_code(session_id) or secrets.token_hex(4).upper()
                    vehicle_id = self.parsec.create_vehicle(
                        session_id, plate_number=plate_clean,
                        org_id=session_data.get("root_org_unit_id"),
                    )
                    if vehicle_id:
                        success = self.parsec.add_vehicle_plate_identifier(
                            session_id, vehicle_id, access_group_id,
                            plate_code=plate_code, name=plate_clean,
                            valid_from=valid_from, valid_to=valid_to,
                        )
                        if success:
                            parsec_identifier_code = plate_code
                            logger.info(f"Parsec vehicle+identifier created: {plate_clean}")
                        else:
                            logger.warning(f"Failed to add plate identifier in Parsec for {plate_clean}")
                    else:
                        logger.warning(f"Failed to create vehicle in Parsec for {plate_clean}")
                    self.parsec.close_session(session_id)
            except Exception as e:
                logger.error(f"Parsec vehicle pass creation failed: {e}")

        pass_data = self.db.create_pass(
            user_id=user_id,
            pass_type="vehicle",
            plate_number=plate_clean,
            valid_from=valid_from,
            valid_to=valid_to,
            access_group_id=access_group_id or user.get("default_access_group"),
            parsec_pass_id=parsec_identifier_code,
        )

        result["success"] = True
        result["message"] = f"Vehicle pass created for {plate_clean} ({duration_text})"
        result["pass_data"] = pass_data
        logger.info(f"Vehicle pass created: user={user_id}, plate={plate_clean}")
        return result

    def create_access_pass(self, user_id: int, access_group_id: str,
                            access_group_name: str = "",
                            duration: str = "day_end") -> Dict:
        result = {
            "success": False,
            "message": "",
            "pass_data": None,
        }

        user = self.db.get_user(user_id)
        if not user:
            result["message"] = "User not authenticated"
            return result

        valid_from, valid_to, _ = self._compute_validity(duration)

        parsec_identifier_code = None
        if self.parsec and self.parsec.host and user.get("parsec_person_id"):
            try:
                session_data = self.parsec.open_admin_session()
                if session_data:
                    session_id = session_data["session_id"]
                    code = secrets.token_hex(4).upper()
                    success = self.parsec.add_access_identifier(
                        session_id, user["parsec_person_id"],
                        accgroup_id=access_group_id, code=code,
                        name=access_group_name,
                        valid_from=valid_from, valid_to=valid_to,
                    )
                    if success:
                        parsec_identifier_code = code
                    self.parsec.close_session(session_id)
            except Exception as e:
                logger.error(f"Parsec access pass creation failed: {e}")

        pass_data = self.db.create_pass(
            user_id=user_id,
            pass_type="access_group",
            access_group_id=access_group_id,
            access_group_name=access_group_name,
            valid_from=valid_from,
            valid_to=valid_to,
            parsec_pass_id=parsec_identifier_code,
        )

        result["success"] = True
        result["message"] = f"Access pass created for {access_group_name}"
        result["pass_data"] = pass_data
        return result

    def get_user_passes(self, user_id: int) -> List[Dict]:
        return self.db.get_active_passes(user_id)

    def cancel_pass(self, pass_id: int, user_id: int) -> bool:
        passes = self.db.get_active_passes(user_id)
        for p in passes:
            if p["id"] == pass_id:
                if p.get("parsec_pass_id") and self.parsec and self.parsec.host:
                    try:
                        session_data = self.parsec.open_admin_session()
                        if session_data:
                            self.parsec.delete_identifier(
                                session_data["session_id"], p["parsec_pass_id"]
                            )
                            self.parsec.close_session(session_data["session_id"])
                    except Exception as e:
                        logger.error(f"Parsec identifier deletion failed: {e}")
                self.db.deactivate_pass(pass_id)
                return True
        return False

    def is_plate_like(self, text: str) -> bool:
        text = text.strip().upper()
        text = re.sub(r'[^A-ZА-Я0-9]', '', text)
        if len(text) < 6 or len(text) > 9:
            return False
        has_letter = bool(re.search(r'[A-ZА-Я]', text))
        has_digit = bool(re.search(r'[0-9]', text))
        return has_letter and has_digit
