"""Система уведомлений для пропускного режима ЖК.

Использует APScheduler для планирования уведомлений:
- Через 30/35/40 мин после создания разового пропуска → собственнику/охране
- Прибытие/убытие гостя → собственнику
- Въезд без пропуска/метки → охране + УК
- Несоответствие номера и метки → охране
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Callable, Dict, Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from db.database import get_db

logger = logging.getLogger(__name__)


class NotificationScheduler:
    """Планировщик уведомлений на APScheduler."""

    def __init__(self, send_message_callback: Callable = None,
                 guard_chat_id: int = None, uk_chat_id: int = None,
                 parsec_api=None):
        self._scheduler = AsyncIOScheduler()
        self.send_message = send_message_callback
        self.guard_chat_id = guard_chat_id
        self.uk_chat_id = uk_chat_id
        self.db = get_db()
        self.parsec = parsec_api

    def start(self):
        """Запуск планировщика."""
        self._scheduler.start()
        logger.info("NotificationScheduler started")

    def shutdown(self, wait: bool = True):
        """Остановка планировщика."""
        self._scheduler.shutdown(wait=wait)
        logger.info("NotificationScheduler shut down")

    def schedule_loading_pass_notifications(self, pass_id: int,
                                              owner_user_id: int,
                                              plate_number: str,
                                              created_at_str: str):
        """Планирование уведомлений для разового пропуска (40 мин).

        Уведомления планируются относительно момента создания пропуска:
        - creation + 30 мин (осталось 10 мин)
        - creation + 35 мин (осталось 5 мин)
        - creation + 40 мин (проверка выезда)
        """
        try:
            created_at = datetime.strptime(created_at_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            logger.error(f"Invalid created_at format: {created_at_str}")
            return

        now = datetime.now()

        # Через 30 мин после создания (осталось 10 мин)
        notify_30 = created_at + timedelta(minutes=30)
        if notify_30 > now:
            job_id = f"loading_10min_{pass_id}"
            self._scheduler.add_job(
                self._notify_loading_expiring,
                trigger='date',
                run_date=notify_30,
                args=[owner_user_id, plate_number, 10],
                id=job_id,
                replace_existing=True,
            )

        # Через 35 мин после создания (осталось 5 мин)
        notify_35 = created_at + timedelta(minutes=35)
        if notify_35 > now:
            job_id = f"loading_5min_{pass_id}"
            self._scheduler.add_job(
                self._notify_loading_expiring,
                trigger='date',
                run_date=notify_35,
                args=[owner_user_id, plate_number, 5],
                id=job_id,
                replace_existing=True,
            )

        # Через 40 мин после создания (проверка выезда)
        notify_40 = created_at + timedelta(minutes=40)
        if notify_40 > now:
            job_id = f"loading_check_{pass_id}"
            self._scheduler.add_job(
                self._check_loading_overstay,
                trigger='date',
                run_date=notify_40,
                args=[pass_id, owner_user_id, plate_number],
                id=job_id,
                replace_existing=True,
            )

    def schedule_guest_arrival_notification(self, owner_user_id: int,
                                              plate_number: str,
                                              parking_spot: str = ""):
        """Уведомление собственнику о прибытии гостя."""
        if self.send_message:
            text = f"Ваш гость прибыл (т/с {plate_number})"
            if parking_spot:
                text += f", м/м {parking_spot}"
            asyncio.ensure_future(
                self._send_notification(owner_user_id, text)
            )

    def schedule_guest_departure_notification(self, owner_user_id: int,
                                                plate_number: str,
                                                duration_min: float = None):
        """Уведомление собственнику об убытии гостя."""
        if self.send_message:
            text = f"Ваш гость уехал (т/с {plate_number})"
            if duration_min is not None:
                text += f", время на территории: {int(duration_min)} мин"
            asyncio.ensure_future(
                self._send_notification(owner_user_id, text)
            )

    def notify_unauthorized_entry(self, plate_number: str, camera_id: str):
        """Уведомление охране и УК: въезд без пропуска/метки."""
        text = (f"Въезд т/с без пропуска!\n"
                f"Номер: {plate_number}\n"
                f"Камера: {camera_id}\n"
                f"Время: {datetime.now().strftime('%H:%M:%S')}")
        if self.guard_chat_id:
            asyncio.ensure_future(
                self._send_notification(self.guard_chat_id, text)
            )
        if self.uk_chat_id:
            asyncio.ensure_future(
                self._send_notification(self.uk_chat_id, text)
            )

    def notify_tag_plate_mismatch(self, tag_code: str, detected_plate: str,
                                    expected_plates: list, camera_id: str):
        """Уведомление охране: несоответствие метки и номера."""
        text = (f"Несоответствие метки и номера т/с!\n"
                f"Метка: {tag_code}\n"
                f"Распознан: {detected_plate}\n"
                f"Ожидались: {', '.join(expected_plates)}\n"
                f"Камера: {camera_id}")
        if self.guard_chat_id:
            asyncio.ensure_future(
                self._send_notification(self.guard_chat_id, text)
            )

    def notify_parking_limit_exceeded(self, owner_name: str,
                                        plate_number: str,
                                        current_count: int,
                                        max_spots: int):
        """Уведомление охране: попытка превышения лимита м/м."""
        text = (f"Попытка превышения лимита м/м!\n"
                f"Собственник: {owner_name}\n"
                f"Номер: {plate_number}\n"
                f"Т/С на территории: {current_count}/{max_spots}")
        if self.guard_chat_id:
            asyncio.ensure_future(
                self._send_notification(self.guard_chat_id, text)
            )

    def notify_incident(self, owner_user_id: int, incident_type: str,
                         description: str):
        """Уведомление собственнику об инциденте от охраны."""
        if not self.send_message:
            logger.warning("No send_message callback, cannot notify incident")
            return

        type_names = {
            "parking_violation": "Парковка в проезде",
            "wrong_spot": "Занятие чужого м/м",
            "overstay": "Превышение времени",
            "unauthorized": "Нахождение без пропуска",
            "other": "Прочее",
        }
        type_text = type_names.get(incident_type, incident_type)
        text = (f"Инцидент: {type_text}\n"
                f"{description}")
        asyncio.ensure_future(
            self._send_notification(owner_user_id, text)
        )

    def cancel_pass_notifications(self, pass_id: int):
        """Отмена уведомлений при отмене пропуска."""
        for suffix in ["10min", "5min", "check"]:
            job_id = f"loading_{suffix}_{pass_id}"
            try:
                self._scheduler.remove_job(job_id)
            except Exception:
                pass

    async def handle_violation(self, owner_parsec_id: str, owner_user_id: int,
                               violation_type: str, description: str):
        """Handle a violation: increment counter, notify, auto-block on 2nd offense."""
        count = self.db.increment_violation(
            owner_parsec_id, violation_type, owner_user_id=owner_user_id
        )

        if count == 1:
            # First violation - warning
            await self._send_notification(
                owner_user_id,
                f"Предупреждение! {description}\n"
                f"При повторном нарушении вы будете добавлены в чёрный список."
            )
        elif count >= 2:
            # Second violation - blacklist
            await self._send_notification(
                owner_user_id,
                f"Повторное нарушение: {description}\n"
                f"Вы добавлены в чёрный список. Создание пропусков заблокировано. "
                f"Обратитесь в УК."
            )
            # Auto-block in Parsec
            if self.parsec:
                try:
                    session_id = self.parsec.get_bot_session_id()
                    if session_id:
                        self.parsec.block_person(session_id, owner_parsec_id)
                        logger.info(f"Auto-blocked {owner_parsec_id} after violation #{count}")
                except Exception as e:
                    logger.error(f"Failed to auto-block: {e}")
            # Notify guard
            if self.guard_chat_id:
                await self._send_notification(
                    self.guard_chat_id,
                    f"Автоблокировка: нарушитель {owner_parsec_id} "
                    f"добавлен в ЧС ({violation_type}, нарушение #{count})"
                )

        return count

    # --- Внутренние методы ---

    async def _notify_loading_expiring(self, owner_user_id: int,
                                         plate_number: str, minutes_left: int):
        text = (f"Разовый пропуск для {plate_number} истекает "
                f"через {minutes_left} мин. Необходимо покинуть паркинг.")
        await self._send_notification(owner_user_id, text)

    async def _check_loading_overstay(self, pass_id: int,
                                        owner_user_id: int,
                                        plate_number: str):
        """Проверка: выехал ли т/с после окончания разового пропуска."""
        plate_clean = plate_number.upper().replace(" ", "")
        vehicles = self.db.get_vehicles_on_premises()
        still_present = any(
            v["plate_number"].upper().replace(" ", "") == plate_clean
            for v in vehicles
        )
        if still_present:
            # Уведомление охране
            text = (f"Т/С {plate_number} по разовому пропуску превышает "
                    f"допустимое время нахождения (40 мин)!")
            if self.guard_chat_id:
                await self._send_notification(self.guard_chat_id, text)

            # Уведомление собственнику
            await self._send_notification(
                owner_user_id,
                f"Т/С {plate_number} превысило допустимое время разового пропуска. "
                f"Необходимо немедленно покинуть паркинг."
            )

            # Инкремент нарушений
            user = self.db.get_user(owner_user_id)
            if user and user.get("parsec_person_id"):
                count = self.db.increment_violation(
                    user["parsec_person_id"], "overstay",
                    owner_user_id=owner_user_id
                )
                if count >= 2:
                    # Второе нарушение -> уведомление о блокировке
                    await self._send_notification(
                        owner_user_id,
                        "Повторное нарушение! Вы добавлены в чёрный список. "
                        "Создание пропусков заблокировано. Обратитесь в УК."
                    )
                    # Auto-block in Parsec
                    if self.parsec:
                        try:
                            session_id = self.parsec.get_bot_session_id()
                            if session_id:
                                self.parsec.block_person(session_id, user["parsec_person_id"])
                                logger.info(f"Auto-blocked person {user['parsec_person_id']} after 2nd violation")
                        except Exception as e:
                            logger.error(f"Failed to auto-block person: {e}")

    async def _send_notification(self, chat_id: int, text: str):
        if self.send_message:
            try:
                await self.send_message(chat_id=chat_id, text=text)
            except Exception as e:
                logger.error(f"Failed to send notification to {chat_id}: {e}")
        else:
            logger.warning(f"No send_message callback, notification lost: {text[:50]}...")
