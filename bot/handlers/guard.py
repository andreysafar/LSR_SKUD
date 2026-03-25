"""Рабочее место охраны в Telegram-боте.

Команды:
- /duty — начать смену, текущее состояние
- /passes — список активных разовых/гостевых пропусков
- /journal — журнал въезда/выезда за смену
- /incident — зафиксировать инцидент
- /create_pass — создать пропуск по обращению
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

INCIDENT_TYPES = {
    "parking_violation": "Парковка в проезде",
    "wrong_spot": "Занятие чужого м/м",
    "overstay": "Превышение времени",
    "unauthorized": "Нахождение без пропуска",
    "other": "Прочее",
}


class GuardHandler:
    def __init__(self, db, parsec_api=None):
        self.db = db
        self.parsec = parsec_api

    def get_duty_status(self) -> Dict:
        """Текущее состояние для начала смены."""
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")

        vehicles_on_premises = self.db.get_vehicles_on_premises()
        active_loading = self.db.get_active_passes_by_subtype("loading")
        active_guest = self.db.get_active_passes_by_subtype("guest")
        unresolved_incidents = self.db.get_incidents(resolved=False, limit=10)

        # Проверяем пропуска с истекающим временем (ближайшие 10 мин)
        expiring_soon = []
        for p in active_loading:
            try:
                valid_to = datetime.strptime(p["valid_to"], "%Y-%m-%d %H:%M:%S")
                remaining = (valid_to - now).total_seconds() / 60
                if 0 < remaining <= 10:
                    expiring_soon.append({**p, "remaining_min": int(remaining)})
            except (ValueError, KeyError):
                pass

        return {
            "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
            "vehicles_on_premises": len(vehicles_on_premises),
            "vehicles_list": vehicles_on_premises[:20],
            "active_loading_passes": len(active_loading),
            "active_guest_passes": len(active_guest),
            "expiring_soon": expiring_soon,
            "unresolved_incidents": len(unresolved_incidents),
            "incidents_list": unresolved_incidents,
        }

    def format_duty_status(self, status: Dict) -> str:
        """Форматирование статуса смены для Telegram."""
        lines = [
            f"Начало смены: {status['timestamp']}",
            f"Т/С на территории: {status['vehicles_on_premises']}",
            f"Разовые пропуска: {status['active_loading_passes']}",
            f"Гостевые пропуска: {status['active_guest_passes']}",
            f"Нерешённые инциденты: {status['unresolved_incidents']}",
        ]

        if status["expiring_soon"]:
            lines.append("\nИстекающие пропуска:")
            for p in status["expiring_soon"]:
                lines.append(
                    f"  {p.get('plate_number', '?')} — "
                    f"осталось {p['remaining_min']} мин"
                )

        return "\n".join(lines)

    def get_active_passes_list(self, subtype: str = None) -> List[Dict]:
        """Список активных пропусков с деталями для охраны."""
        passes = self.db.get_active_passes_by_subtype(subtype)
        enriched = []
        for p in passes:
            entry = {
                "id": p["id"],
                "plate_number": p.get("plate_number", ""),
                "pass_subtype": p.get("pass_subtype", "regular"),
                "vehicle_brand": p.get("vehicle_brand", ""),
                "driver_phone": p.get("driver_phone", ""),
                "valid_from": p.get("valid_from", ""),
                "valid_to": p.get("valid_to", ""),
                "parking_spot_id": p.get("parking_spot_id"),
            }
            # Получить данные собственника
            if p.get("user_id"):
                user = self.db.get_user(p["user_id"])
                if user:
                    entry["owner_name"] = user.get("full_name", "")
                    entry["owner_phone"] = user.get("phone_number", "")

            # Получить номер м/м
            if p.get("parking_spot_id"):
                spots = self.db.get_parking_spots()
                for s in spots:
                    if s["id"] == p["parking_spot_id"]:
                        entry["parking_spot_number"] = s.get("spot_number", "")
                        break

            enriched.append(entry)
        return enriched

    def format_passes_list(self, passes: List[Dict]) -> str:
        """Форматирование списка пропусков для Telegram."""
        if not passes:
            return "Активных пропусков нет"

        lines = []
        for p in passes:
            subtype_names = {
                "loading": "Разовый",
                "guest": "Гостевой",
                "regular": "Обычный",
            }
            subtype = subtype_names.get(p.get("pass_subtype", ""), "")
            line = f"{subtype} | {p.get('plate_number', '?')}"
            if p.get("vehicle_brand"):
                line += f" ({p['vehicle_brand']})"
            if p.get("owner_phone"):
                line += f" | Собственник: {p.get('owner_phone', '')}"
            if p.get("parking_spot_number"):
                line += f" | М/М: {p['parking_spot_number']}"
            if p.get("driver_phone"):
                line += f" | Водитель: {p['driver_phone']}"
            try:
                valid_to = datetime.strptime(p["valid_to"], "%Y-%m-%d %H:%M:%S")
                remaining = (valid_to - datetime.now()).total_seconds() / 60
                if remaining > 0:
                    line += f" | Ещё {int(remaining)} мин"
            except (ValueError, KeyError):
                pass
            lines.append(line)

        return "\n".join(lines)

    def get_journal(self, limit: int = 30, date_from: str = None) -> List[Dict]:
        """Журнал въезда/выезда для охраны (только чтение)."""
        if not date_from:
            date_from = datetime.now().strftime("%Y-%m-%d 00:00:00")
        return self.db.get_entry_exit_log(limit=limit, date_from=date_from)

    def format_journal(self, entries: List[Dict]) -> str:
        """Форматирование журнала для Telegram."""
        if not entries:
            return "Записей за сегодня нет"

        lines = []
        for e in entries:
            entry_time = e.get("entry_time", "?")
            exit_time = e.get("exit_time", "—")
            plate = e.get("plate_number", "?")
            duration = e.get("duration_minutes")
            subtype = e.get("pass_subtype", "")

            if entry_time and len(entry_time) > 16:
                entry_time = entry_time[11:16]
            if exit_time and exit_time != "—" and len(exit_time) > 16:
                exit_time = exit_time[11:16]

            line = f"{entry_time}→{exit_time} | {plate}"
            if duration:
                line += f" | {int(duration)} мин"
            if subtype:
                line += f" | {subtype}"
            lines.append(line)

        return "\n".join(lines)

    def create_incident(self, incident_type: str, description: str,
                         plate_number: str = None, apartment: str = None,
                         reported_by_user_id: int = None) -> int:
        """Фиксация инцидента охраной."""
        incident_id = self.db.create_incident(
            incident_type=incident_type,
            description=description,
            plate_number=plate_number,
            apartment=apartment,
            reported_by_user_id=reported_by_user_id,
            reported_by_role="guard",
        )
        logger.info(f"Incident created: type={incident_type}, id={incident_id}")
        return incident_id

    def get_incident_types(self) -> Dict[str, str]:
        return INCIDENT_TYPES
