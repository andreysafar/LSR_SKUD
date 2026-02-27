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

    def _find_person_by_phone(self, session_id: str, phone: str) -> Optional[Dict]:
        try:
            templates = self.parsec.get_person_extra_field_templates(session_id)
            phone_template_id = None
            for t in templates:
                name_lower = t["name"].lower()
                if "телефон" in name_lower or "phone" in name_lower or "тел" in name_lower:
                    phone_template_id = t["id"]
                    break

            if phone_template_id:
                persons = self.parsec.person_search(
                    session_id,
                    field_id=phone_template_id,
                    relation=6,
                    value=phone,
                    value1=None,
                )
                if persons:
                    return persons[0]
        except Exception as e:
            logger.warning(f"PersonSearch by phone failed: {e}")

        return None

    def authenticate_by_phone(self, user_id: int, phone: str) -> Dict:
        result = {
            "success": False,
            "message": "",
            "person": None,
        }

        phone_norm = self.normalize_phone(phone)
        logger.info(f"Auth attempt: user={user_id}, phone={phone_norm}")

        if not self.parsec or not self.parsec.host:
            self.db.save_user(user_id, phone_number=phone_norm)
            result["success"] = True
            result["message"] = "Registered (Parsec offline mode)"
            return result

        try:
            session_data = self.parsec.open_bot_session()
            if not session_data:
                result["message"] = "Cannot connect to Parsec system"
                return result

            session_id = session_data["session_id"]
            person = self._find_person_by_phone(session_id, phone_norm)
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

    def authenticate_by_name(self, user_id: int, phone: str,
                              last_name: str, first_name: str = "",
                              middle_name: str = "") -> Dict:
        result = {
            "success": False,
            "message": "",
            "person": None,
        }

        phone_norm = self.normalize_phone(phone)

        if not self.parsec or not self.parsec.host:
            self.db.save_user(user_id, phone_number=phone_norm)
            result["success"] = True
            result["message"] = "Registered (Parsec offline mode)"
            return result

        try:
            session_data = self.parsec.open_bot_session()
            if not session_data:
                result["message"] = "Cannot connect to Parsec system"
                return result

            session_id = session_data["session_id"]
            persons = self.parsec.find_people(
                session_id, lastname=last_name,
                firstname=first_name, middlename=middle_name,
            )
            self.parsec.close_session(session_id)

            if not persons:
                result["message"] = "Person not found in Parsec system"
                return result

            if len(persons) == 1:
                person = persons[0]
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
                result["message"] = f"Multiple matches found ({len(persons)}). Please provide full name."
                result["persons"] = persons

        except Exception as e:
            logger.error(f"Authentication error: {e}")
            result["message"] = f"Authentication error: {e}"

        return result

    def get_user_access_groups(self, user_id: int) -> list:
        if not self.parsec or not self.parsec.host:
            return []

        try:
            session_data = self.parsec.open_bot_session()
            if not session_data:
                return []
            session_id = session_data["session_id"]
            groups = self.parsec.get_access_groups(session_id)
            self.parsec.close_session(session_id)
            return groups
        except Exception as e:
            logger.error(f"Failed to get access groups: {e}")
            return []
