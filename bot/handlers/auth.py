import logging
import re
from typing import Optional, Dict

logger = logging.getLogger(__name__)

PHONE_PATTERN = re.compile(r'^\+?[78]?\d{10}$')


class AuthHandler:
    def __init__(self, db, parsec_api):
        self.db = db
        self.parsec = parsec_api

    def normalize_phone(self, phone: str) -> str:
        phone = re.sub(r'[\s\-\(\)]', '', phone)
        if phone.startswith('8') and len(phone) == 11:
            phone = '7' + phone[1:]
        phone = phone.lstrip('+')
        return phone

    def authenticate_by_phone(self, user_id: int, phone: str) -> Dict:
        result = {
            "success": False,
            "message": "",
            "person": None,
        }

        phone_norm = self.normalize_phone(phone)
        logger.info(f"Auth attempt: user={user_id}, phone={phone_norm}")

        if not self.parsec or not self.parsec.domain:
            self.db.save_user(user_id, phone_number=phone_norm)
            result["success"] = True
            result["message"] = "Registered (Parsec offline mode)"
            return result

        try:
            session_id = self.parsec.open_bot_session()
            if not session_id:
                result["message"] = "Cannot connect to Parsec system"
                return result

            person = self.parsec.find_person_by_phone(session_id, phone_norm)
            self.parsec.close_session(session_id)

            if person:
                full_name = f"{person.get('last_name', '')} {person.get('first_name', '')}".strip()
                self.db.save_user(
                    user_id,
                    phone_number=phone_norm,
                    parsec_person_id=person["id"],
                    full_name=full_name,
                )
                result["success"] = True
                result["message"] = f"Authenticated as {full_name}"
                result["person"] = person
            else:
                result["message"] = "Phone number not found in Parsec system"

        except Exception as e:
            logger.error(f"Authentication error: {e}")
            result["message"] = f"Authentication error: {e}"

        return result

    def get_user_access_groups(self, user_id: int) -> list:
        user = self.db.get_user(user_id)
        if not user or not user.get("parsec_person_id"):
            return []

        if not self.parsec or not self.parsec.domain:
            return []

        try:
            session_id = self.parsec.open_bot_session()
            if not session_id:
                return []
            groups = self.parsec.get_person_access_groups(session_id, user["parsec_person_id"])
            self.parsec.close_session(session_id)
            return groups
        except Exception as e:
            logger.error(f"Failed to get access groups: {e}")
            return []
