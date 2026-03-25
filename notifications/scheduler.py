"""Система уведомлений для пропускного режима ЖК.

Использует asyncio tasks для планирования уведомлений:
- За 5-10 мин до окончания разового пропуска → собственнику
- Превышение 40 мин → охране + собственнику
- Прибытие/убытие гостя → собственнику
- Въезд без пропуска/метки → охране + УК
- Несоответствие номера и метки → охране
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Callable, Dict, Any

from db.database import get_db

logger = logging.getLogger(__name__)


class NotificationScheduler:
    """Планировщик уведомлений на asyncio tasks."""

    def __init__(self, send_message_callback: Callable = None,
                 guard_chat_id: int = None, uk_chat_id: int = None):
        self._tasks: Dict[str, asyncio.Task] = {}
        self.send_message = send_message_callback
        self.guard_chat_id = guard_chat_id
        self.uk_chat_id = uk_chat_id
        self.db = get_db()

    def schedule_loading_pass_notifications(self, pass_id: int,
                                              owner_user_id: int,
                                              plate_number: str,
                                              valid_to_str: str):
        """Планирование уведомлений для разового пропуска (40 мин)."""
        try:
            valid_to = datetime.strptime(valid_to_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            logger.error(f"Invalid valid_to format: {valid_to_str}")
            return

        now = datetime.now()

        # За 10 мин до окончания
        notify_10 = valid_to - timedelta(minutes=10)
        if notify_10 > now:
            delay_10 = (notify_10 - now).total_seconds()
            task_key = f"loading_10min_{pass_id}"
            self._schedule_task(
                task_key, delay_10,
                self._notify_loading_expiring,
                owner_user_id, plate_number, 10
            )

        # За 5 мин до окончания
        notify_5 = valid_to - timedelta(minutes=5)
        if notify_5 > now:
            delay_5 = (notify_5 - now).total_seconds()
            task_key = f"loading_5min_{pass_id}"
            self._schedule_task(
                task_key, delay_5,
                self._notify_loading_expiring,
                owner_user_id, plate_number, 5
            )

        # Проверка выезда после окончания (через 1 мин после valid_to)
        check_time = valid_to + timedelta(minutes=1)
        if check_time > now:
            delay_check = (check_time - now).total_seconds()
            task_key = f"loading_check_{pass_id}"
            self._schedule_task(
                task_key, delay_check,
                self._check_loading_overstay,
                pass_id, owner_user_id, plate_number
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
            if duration_min:
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
            task_key = f"loading_{suffix}_{pass_id}"
            if task_key in self._tasks:
                self._tasks[task_key].cancel()
                del self._tasks[task_key]

    # --- Внутренние методы ---

    def _schedule_task(self, task_key: str, delay_seconds: float,
                        coro_func, *args):
        if task_key in self._tasks:
            self._tasks[task_key].cancel()

        async def _delayed():
            await asyncio.sleep(delay_seconds)
            try:
                await coro_func(*args)
            except Exception as e:
                logger.error(f"Notification task {task_key} error: {e}")
            finally:
                self._tasks.pop(task_key, None)

        self._tasks[task_key] = asyncio.ensure_future(_delayed())

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
                    # Второе нарушение → уведомление о блокировке
                    await self._send_notification(
                        owner_user_id,
                        "Повторное нарушение! Вы добавлены в чёрный список. "
                        "Создание пропусков заблокировано. Обратитесь в УК."
                    )

    async def _send_notification(self, chat_id: int, text: str):
        if self.send_message:
            try:
                await self.send_message(chat_id=chat_id, text=text)
            except Exception as e:
                logger.error(f"Failed to send notification to {chat_id}: {e}")
        else:
            logger.warning(f"No send_message callback, notification lost: {text[:50]}...")
