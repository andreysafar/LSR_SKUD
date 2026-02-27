import logging
import re
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


class PassHandler:
    def __init__(self, db, parsec_api):
        self.db = db
        self.parsec = parsec_api

    def create_vehicle_pass(self, user_id: int, plate_number: str,
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

        pass_data = self.db.create_pass(
            user_id=user_id,
            pass_type="vehicle",
            plate_number=plate_clean,
            valid_from=valid_from,
            valid_to=valid_to,
            access_group_id=user.get("default_access_group"),
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

        now = datetime.now()
        if duration == "day_end":
            valid_from = now.strftime("%Y-%m-%d %H:%M:%S")
            valid_to = now.replace(hour=23, minute=59, second=59).strftime("%Y-%m-%d %H:%M:%S")
        elif duration == "24hours":
            valid_from = now.strftime("%Y-%m-%d %H:%M:%S")
            valid_to = (now + timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
        else:
            valid_from = now.strftime("%Y-%m-%d %H:%M:%S")
            valid_to = (now + timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")

        parsec_pass_id = None
        if self.parsec and self.parsec.domain and user.get("parsec_person_id"):
            try:
                session_id = self.parsec.open_admin_session()
                if session_id:
                    parsec_pass_id = self.parsec.create_pass(
                        session_id, user["parsec_person_id"],
                        access_group_id, valid_from, valid_to,
                    )
                    self.parsec.close_session(session_id)
            except Exception as e:
                logger.error(f"Parsec pass creation failed: {e}")

        pass_data = self.db.create_pass(
            user_id=user_id,
            pass_type="access_group",
            access_group_id=access_group_id,
            access_group_name=access_group_name,
            valid_from=valid_from,
            valid_to=valid_to,
            parsec_pass_id=parsec_pass_id,
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
