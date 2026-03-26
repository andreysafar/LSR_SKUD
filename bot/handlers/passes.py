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


LOADING_DURATION_MIN = 40  # Разовый пропуск на погрузку/разгрузку


class PassHandler:
    def __init__(self, db, parsec_api):
        self.db = db
        self.parsec = parsec_api

    def _compute_validity(self, duration: str):
        now = datetime.now()
        if duration == "loading":
            valid_from = now.strftime("%Y-%m-%d %H:%M:%S")
            valid_to = (now + timedelta(minutes=LOADING_DURATION_MIN)).strftime("%Y-%m-%d %H:%M:%S")
            duration_text = f"разовый на {LOADING_DURATION_MIN} мин"
        elif duration == "day_end":
            valid_from = now.strftime("%Y-%m-%d %H:%M:%S")
            valid_to = now.replace(hour=23, minute=59, second=59).strftime("%Y-%m-%d %H:%M:%S")
            duration_text = "до конца дня"
        elif duration == "3hours":
            valid_from = now.strftime("%Y-%m-%d %H:%M:%S")
            valid_to = (now + timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S")
            duration_text = "на 3 часа"
        elif duration == "24hours":
            valid_from = now.strftime("%Y-%m-%d %H:%M:%S")
            valid_to = (now + timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
            duration_text = "на 24 часа"
        elif duration == "week":
            valid_from = now.strftime("%Y-%m-%d %H:%M:%S")
            valid_to = (now + timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
            duration_text = "на 1 неделю"
        else:
            valid_from = now.strftime("%Y-%m-%d %H:%M:%S")
            valid_to = (now + timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
            duration_text = "на 24 часа"
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

        if not RU_PLATE_PATTERN.match(plate_clean):
            result["message"] = "Некорректный формат номера. Ожидается формат А123ВС77."
            return result

        user = self.db.get_user(user_id)
        if not user:
            result["message"] = "User not authenticated"
            return result

        # Проверка чёрного списка
        if user.get("parsec_person_id") and self.parsec and self.parsec.host:
            if self._is_blocked(user["parsec_person_id"]):
                result["message"] = ("Вы находитесь в чёрном списке. "
                                     "Создание пропусков невозможно. Обратитесь в УК.")
                return result

        valid_from, valid_to, duration_text = self._compute_validity(duration)

        parsec_identifier_code = None
        if self.parsec and self.parsec.host and access_group_id:
            session_id = None
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
            except Exception as e:
                logger.error(f"Parsec vehicle pass creation failed: {e}")
            finally:
                if session_id:
                    try:
                        self.parsec.close_session(session_id)
                    except Exception as e:
                        logger.error(f"Failed to close Parsec session: {e}")

        pass_data = self.db.create_pass(
            user_id=user_id,
            pass_type="vehicle",
            plate_number=plate_clean,
            valid_from=valid_from,
            valid_to=valid_to,
            access_group_id=access_group_id or user.get("default_access_group"),
            parsec_pass_id=parsec_identifier_code,
        )

        if self.parsec and self.parsec.host and access_group_id and parsec_identifier_code:
            result["success"] = True
        elif not (self.parsec and self.parsec.host and access_group_id):
            result["success"] = True
        else:
            result["success"] = False
            result["message"] = f"Пропуск сохранён, но не удалось создать идентификатор в Parsec для {plate_clean}"
            result["pass_data"] = pass_data
            logger.warning(f"Vehicle pass saved without Parsec identifier: user={user_id}, plate={plate_clean}")
            return result

        result["message"] = f"Vehicle pass created for {plate_clean} ({duration_text})"
        result["pass_data"] = pass_data
        logger.info(f"Vehicle pass created: user={user_id}, plate={plate_clean}")
        return result

    def create_loading_pass(self, user_id: int, plate_number: str,
                            access_group_id: str = None) -> Dict:
        """Разовый пропуск на погрузку/разгрузку (40 мин, без м/м)."""
        result = {"success": False, "message": "", "pass_data": None}

        plate_clean = normalize_plate_input(plate_number)
        if not plate_clean:
            result["message"] = "Некорректный номер т/с"
            return result

        if not RU_PLATE_PATTERN.match(plate_clean):
            result["message"] = "Некорректный формат номера. Ожидается формат А123ВС77."
            return result

        user = self.db.get_user(user_id)
        if not user:
            result["message"] = "Пользователь не авторизован"
            return result

        # Проверка чёрного списка (Parsec BlockPerson)
        if user.get("parsec_person_id") and self.parsec and self.parsec.host:
            if self._is_blocked(user["parsec_person_id"]):
                result["message"] = ("Вы находитесь в чёрном списке. "
                                     "Создание пропусков невозможно. Обратитесь в УК.")
                return result

        valid_from, valid_to, duration_text = self._compute_validity("loading")

        parsec_identifier_code = None
        if self.parsec and self.parsec.host and access_group_id:
            session_id = None
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
            except Exception as e:
                logger.error(f"Parsec loading pass creation failed: {e}")
            finally:
                if session_id:
                    try:
                        self.parsec.close_session(session_id)
                    except Exception as e:
                        logger.error(f"Failed to close Parsec session: {e}")

        pass_data = self.db.create_pass_extended(
            user_id=user_id,
            pass_type="vehicle",
            plate_number=plate_clean,
            valid_from=valid_from,
            valid_to=valid_to,
            pass_subtype="loading",
            max_duration_min=LOADING_DURATION_MIN,
            owner_parsec_id=user.get("parsec_person_id"),
            access_group_id=access_group_id or user.get("default_access_group"),
            parsec_pass_id=parsec_identifier_code,
        )

        if self.parsec and self.parsec.host and access_group_id and not parsec_identifier_code:
            result["success"] = False
            result["message"] = f"Пропуск сохранён, но не удалось создать идентификатор в Parsec для {plate_clean}"
            result["pass_data"] = pass_data
            return result

        result["success"] = True
        result["message"] = (f"Разовый пропуск на погрузку создан для {plate_clean} "
                             f"({duration_text})")
        result["pass_data"] = pass_data
        logger.info(f"Loading pass created: user={user_id}, plate={plate_clean}")
        return result

    def create_guest_pass(self, user_id: int, plate_number: str,
                           parking_spot_id: int,
                           access_group_id: str = None,
                           duration: str = "day_end",
                           driver_phone: str = None,
                           vehicle_brand: str = None) -> Dict:
        """Гостевой пропуск с указанием м/м."""
        result = {"success": False, "message": "", "pass_data": None}

        plate_clean = normalize_plate_input(plate_number)
        if not plate_clean:
            result["message"] = "Некорректный номер т/с"
            return result

        if not RU_PLATE_PATTERN.match(plate_clean):
            result["message"] = "Некорректный формат номера. Ожидается формат А123ВС77."
            return result

        user = self.db.get_user(user_id)
        if not user:
            result["message"] = "Пользователь не авторизован"
            return result

        # Проверка чёрного списка
        if user.get("parsec_person_id") and self.parsec and self.parsec.host:
            if self._is_blocked(user["parsec_person_id"]):
                result["message"] = ("Вы находитесь в чёрном списке. "
                                     "Создание пропусков невозможно. Обратитесь в УК.")
                return result

        # Валидация м/м: принадлежит ли собственнику
        spots = self.db.get_parking_spots(owner_user_id=user_id)
        spot_ids = [s["id"] for s in spots]
        if parking_spot_id not in spot_ids:
            # Попробуем по parsec_person_id
            if user.get("parsec_person_id"):
                spots_parsec = self.db.get_parking_spots(owner_parsec_id=user["parsec_person_id"])
                spot_ids = [s["id"] for s in spots_parsec]
            if parking_spot_id not in spot_ids:
                result["message"] = "Указанное м/м не принадлежит вам"
                return result

        valid_from, valid_to, duration_text = self._compute_validity(duration)

        parsec_identifier_code = None
        if self.parsec and self.parsec.host and access_group_id:
            session_id = None
            try:
                session_data = self.parsec.open_admin_session()
                if session_data:
                    session_id = session_data["session_id"]
                    plate_code = self.parsec.get_unique_card_code(session_id) or secrets.token_hex(4).upper()
                    vehicle_id = self.parsec.create_vehicle(
                        session_id, plate_number=plate_clean,
                        model=vehicle_brand or "",
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
            except Exception as e:
                logger.error(f"Parsec guest pass creation failed: {e}")
            finally:
                if session_id:
                    try:
                        self.parsec.close_session(session_id)
                    except Exception as e:
                        logger.error(f"Failed to close Parsec session: {e}")

        pass_data = self.db.create_pass_extended(
            user_id=user_id,
            pass_type="vehicle",
            plate_number=plate_clean,
            valid_from=valid_from,
            valid_to=valid_to,
            pass_subtype="guest",
            parking_spot_id=parking_spot_id,
            driver_phone=driver_phone,
            vehicle_brand=vehicle_brand,
            owner_parsec_id=user.get("parsec_person_id"),
            access_group_id=access_group_id or user.get("default_access_group"),
            parsec_pass_id=parsec_identifier_code,
        )

        if self.parsec and self.parsec.host and access_group_id and not parsec_identifier_code:
            result["success"] = False
            result["message"] = f"Пропуск сохранён, но не удалось создать идентификатор в Parsec для {plate_clean}"
            result["pass_data"] = pass_data
            return result

        result["success"] = True
        result["message"] = (f"Гостевой пропуск создан для {plate_clean} "
                             f"({duration_text})")
        result["pass_data"] = pass_data
        logger.info(f"Guest pass created: user={user_id}, plate={plate_clean}, spot={parking_spot_id}")
        return result

    def _is_blocked(self, parsec_person_id: str) -> bool:
        """Проверка, заблокирован ли пользователь в Parsec."""
        # Проверяем локальный счётчик нарушений
        total_violations = self.db.get_violation_count(parsec_person_id)
        if total_violations >= 2:
            return True
        return False

    def get_user_parking_spots(self, user_id: int) -> List[Dict]:
        """Получить м/м пользователя для выбора при создании гостевого пропуска."""
        user = self.db.get_user(user_id)
        if not user:
            return []
        spots = self.db.get_parking_spots(owner_user_id=user_id)
        if not spots and user.get("parsec_person_id"):
            spots = self.db.get_parking_spots(owner_parsec_id=user["parsec_person_id"])
        return spots

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
            session_id = None
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
            except Exception as e:
                logger.error(f"Parsec access pass creation failed: {e}")
            finally:
                if session_id:
                    try:
                        self.parsec.close_session(session_id)
                    except Exception as e:
                        logger.error(f"Failed to close Parsec session: {e}")

        pass_data = self.db.create_pass(
            user_id=user_id,
            pass_type="access_group",
            access_group_id=access_group_id,
            access_group_name=access_group_name,
            valid_from=valid_from,
            valid_to=valid_to,
            parsec_pass_id=parsec_identifier_code,
        )

        if self.parsec and self.parsec.host and user.get("parsec_person_id") and not parsec_identifier_code:
            result["success"] = False
            result["message"] = f"Пропуск сохранён, но не удалось создать идентификатор в Parsec для {access_group_name}"
            result["pass_data"] = pass_data
            return result

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
                    session_id = None
                    try:
                        session_data = self.parsec.open_admin_session()
                        if session_data:
                            session_id = session_data["session_id"]
                            self.parsec.delete_identifier(
                                session_id, p["parsec_pass_id"]
                            )
                    except Exception as e:
                        logger.error(f"Parsec identifier deletion failed: {e}")
                    finally:
                        if session_id:
                            try:
                                self.parsec.close_session(session_id)
                            except Exception as e:
                                logger.error(f"Failed to close Parsec session: {e}")
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
