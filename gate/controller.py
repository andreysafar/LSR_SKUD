import logging
from typing import Optional, Dict, List
from datetime import datetime

from db.database import get_db
from parsec.api import ParsecAPI

logger = logging.getLogger(__name__)


class GateController:
    def __init__(self, parsec_api: Optional[ParsecAPI] = None):
        self.parsec = parsec_api
        self.db = get_db()
        self._session_id = None

    def _ensure_session(self) -> Optional[str]:
        if self._session_id:
            if self.parsec and self.parsec.continue_session(self._session_id):
                return self._session_id
        if self.parsec:
            session_data = self.parsec.open_admin_session()
            if session_data:
                self._session_id = session_data["session_id"]
                return self._session_id
        return None

    def _get_camera(self, camera_id: str) -> Optional[Dict]:
        cameras = self.db.get_cameras()
        for cam in cameras:
            if cam["camera_id"] == camera_id:
                return cam
        return None

    def check_plate_and_open(self, camera_id: str, plate_number: str,
                              event_id: int = None) -> Dict:
        """Распознан номер камерой. Логика зависит от типа камеры:
        - gpu: наша камера распознала → отправляем в Parsec
        - parsec_native: Parsec сам решает, мы только логируем
        В обоих случаях ведём журнал въезда/выезда.
        """
        result = {
            "plate": plate_number,
            "pass_found": False,
            "gate_opened": False,
            "pass_id": None,
            "details": "",
            "direction": None,
            "entry_exit_id": None,
        }

        plate_clean = plate_number.upper().replace(" ", "")
        camera = self._get_camera(camera_id)
        direction = camera.get("direction", "both") if camera else "both"
        recognition_type = camera.get("recognition_type", "gpu").lower() if camera else "gpu"
        gate_territory_id = camera.get("gate_device_id", "") if camera else ""
        result["direction"] = direction

        # Ищем активный пропуск
        active_pass = self.db.find_active_pass_by_plate(plate_clean)

        if not active_pass:
            result["details"] = "Активный пропуск не найден"
            self.db.save_gate_event(
                camera_id=camera_id,
                plate_number=plate_clean,
                action="check",
                success=False,
                details="No active pass"
            )
            # Запись для уведомления "въезд без пропуска" (обрабатывается в notifications)
            return result

        result["pass_found"] = True
        result["pass_id"] = active_pass["id"]

        # Для direction=="both" определяем фактическое направление по журналу
        actual_direction = direction
        if direction == "both":
            existing = self.db.get_vehicles_on_premises()
            is_on_premises = any(
                v["plate_number"].upper().replace(" ", "") == plate_clean
                for v in existing
            )
            actual_direction = "exit" if is_on_premises else "entry"

        # Проверка лимита одновременного нахождения (только для фактических въездов)
        owner_parsec_id = active_pass.get("owner_parsec_id")
        if owner_parsec_id and actual_direction == "entry":
            limit_ok = self._check_parking_limit(owner_parsec_id)
            if not limit_ok:
                result["details"] = "Превышен лимит одновременного нахождения т/с"
                result["gate_opened"] = False
                self.db.save_gate_event(
                    camera_id=camera_id,
                    plate_number=plate_clean,
                    pass_id=active_pass["id"],
                    action="check",
                    success=False,
                    details="Parking limit exceeded"
                )
                return result

        # Открытие ворот: Parsec принимает решение
        if recognition_type == "gpu" and gate_territory_id and self.parsec:
            # Наша GPU-камера → отправляем событие в Parsec
            result["gate_opened"] = self._send_to_parsec(
                gate_territory_id, plate_clean, active_pass
            )
            result["details"] = ("Ворота открыты (GPU→Parsec)" if result["gate_opened"]
                                 else "Parsec отказал в доступе")
        elif recognition_type == "parsec_native":
            # Parsec сам открыл — мы просто логируем
            result["gate_opened"] = True
            result["details"] = "Ворота открыты (штатное Parsec)"
        else:
            result["gate_opened"] = False
            logger.error(f"Cannot process plate {plate_clean}: no valid recognition path "
                         f"(recognition_type={recognition_type}, territory={gate_territory_id}, "
                         f"parsec={'available' if self.parsec else 'unavailable'})")
            result["details"] = "Нет доступного способа обработки распознавания"

        # Логирование gate event
        self.db.save_gate_event(
            camera_id=camera_id,
            plate_number=plate_clean,
            pass_id=active_pass["id"],
            action="open",
            success=result["gate_opened"],
            details=result["details"]
        )

        # Журнал въезда/выезда
        if result["gate_opened"]:
            entry_exit_id = self._record_entry_exit(
                camera_id, plate_clean, direction, active_pass
            )
            result["entry_exit_id"] = entry_exit_id

        # Обновление recognition event
        if event_id:
            self.db.update_recognition_event(
                event_id,
                matched_pass_id=active_pass["id"],
                gate_opened=1 if result["gate_opened"] else 0
            )

        logger.info(f"Gate control: plate={plate_clean}, direction={direction}, "
                     f"opened={result['gate_opened']}")
        return result

    def _send_to_parsec(self, territory_id: str, plate_clean: str,
                         active_pass: Dict) -> bool:
        """Отправка распознанного номера в Parsec для принятия решения.
        GPU-камера эмулирует считывание номера. Parsec сам решает, открывать ли."""
        try:
            session_id = self._ensure_session()
            if not session_id:
                logger.error("Cannot send to Parsec: no session available")
                return False

            # Отправляем распознанный номер в Parsec для идентификации
            success = self.parsec.send_plate_recognition(
                session_id, territory_id, plate_clean
            )
            if success:
                return True

            # Попытка через SendVerificationCommand если есть person_id
            owner_parsec_id = active_pass.get("owner_parsec_id")
            if owner_parsec_id:
                success = self.parsec.send_verification_command(
                    session_id, territory_id, owner_parsec_id
                )
                if success:
                    return True

            logger.error(f"Failed to send plate recognition to Parsec: "
                         f"territory={territory_id}, plate={plate_clean}")
            return False
        except Exception as e:
            logger.error(f"Send to Parsec error: {e}")
            self._session_id = None
            return False

    def _record_entry_exit(self, camera_id: str, plate_number: str,
                            direction: str, active_pass: Dict) -> Optional[int]:
        """Запись в парный журнал въезда/выезда."""
        if direction == "entry" or direction == "both":
            # Проверяем, нет ли уже открытой записи
            existing = self.db.get_vehicles_on_premises()
            for v in existing:
                if v["plate_number"].upper().replace(" ", "") == plate_number:
                    if direction == "both":
                        # Если direction=both и т/с уже на территории → это выезд
                        exit_record = self.db.record_exit(plate_number, camera_id)
                        if exit_record:
                            logger.info(f"Exit recorded: {plate_number}, duration={exit_record.get('duration_minutes')}min")
                            return exit_record["id"]
                    logger.warning(f"Duplicate entry suppressed: {plate_number} already on premises")
                    return None  # Уже на территории, дубль entry

            # Новый въезд
            entry_id = self.db.record_entry(
                plate_number=plate_number,
                camera_id=camera_id,
                pass_id=active_pass.get("id"),
                pass_subtype=active_pass.get("pass_subtype", "regular"),
                owner_parsec_id=active_pass.get("owner_parsec_id"),
                owner_user_id=active_pass.get("user_id"),
            )
            logger.info(f"Entry recorded: {plate_number}, id={entry_id}")
            return entry_id

        elif direction == "exit":
            exit_record = self.db.record_exit(plate_number, camera_id)
            if exit_record:
                logger.info(f"Exit recorded: {plate_number}, duration={exit_record.get('duration_minutes')}min")
                return exit_record["id"]
            return None

        return None

    def _check_parking_limit(self, owner_parsec_id: str) -> bool:
        """Проверка: кол-во т/с на территории < кол-во м/м собственника."""
        vehicles_count = self.db.count_vehicles_on_premises(owner_parsec_id)
        spots_count = self.db.get_parking_spots_count(owner_parsec_id)
        if spots_count == 0:
            # Нет привязанных м/м — не ограничиваем (для обычных пропусков)
            return True
        return vehicles_count < spots_count

    def check_tag_plate_match(self, camera_id: str, tag_code: str,
                               plate_number: str) -> Dict:
        """Проверка соответствия метки и номера т/с.
        Вызывается когда по метке (IDENTIFTYPE=0) въехало т/с и камера распознала номер."""
        result = {
            "match": False,
            "tag_code": tag_code,
            "plate_detected": plate_number,
            "expected_plates": [],
            "person_id": None,
        }

        if not self.parsec or not self.parsec.host:
            return result

        try:
            session_id = self._ensure_session()
            if not session_id:
                return result

            # Найти человека по метке
            person = self.parsec.find_person_by_identifier(session_id, tag_code)
            if not person:
                result["details"] = "Владелец метки не найден"
                return result

            result["person_id"] = person["id"]

            # Получить все идентификаторы этого человека
            identifiers = self.parsec.get_person_identifiers(session_id, person["id"])

            # Найти привязанные номера (IDENTIFTYPE=1)
            plate_identifiers = [i for i in identifiers if i.get("identif_type") == 1]
            expected_plates = [i.get("name", "").upper().replace(" ", "")
                               for i in plate_identifiers if i.get("name")]
            result["expected_plates"] = expected_plates

            plate_clean = plate_number.upper().replace(" ", "")
            result["match"] = plate_clean in expected_plates

            if not result["match"]:
                logger.warning(
                    f"Tag-plate mismatch: tag={tag_code}, detected={plate_clean}, "
                    f"expected={expected_plates}"
                )

        except Exception as e:
            logger.error(f"check_tag_plate_match error: {e}")
            self._session_id = None

        return result
