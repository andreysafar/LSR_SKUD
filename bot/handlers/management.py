"""Рабочее место управляющей компании (УК) в Telegram-боте.

Команды:
- /blacklist         — список жителей в чёрном списке
- /blacklist_add     — добавить жителя в чёрный список
- /blacklist_remove  — удалить жителя из чёрного списка
- /incidents         — список инцидентов
- /resolve_incident  — закрыть инцидент с указанием решения
"""
import logging
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_MANAGEMENT_ROLE = "EmployeeWriter"
_ACCESS_DENIED_MSG = "Доступ запрещён: недостаточно прав (роль управляющей компании не подтверждена)."

INCIDENT_TYPE_NAMES = {
    "parking_violation": "Парковка в проезде",
    "wrong_spot": "Занятие чужого м/м",
    "overstay": "Превышение времени",
    "unauthorized": "Нахождение без пропуска",
    "other": "Прочее",
}

VIOLATION_TYPE_NAMES = {
    "manual": "Ручное добавление",
    "parking_violation": "Нарушение парковки",
    "overstay": "Превышение времени",
    "unauthorized": "Нахождение без пропуска",
    "wrong_spot": "Занятие чужого м/м",
}


class ManagementHandler:
    """Handler for Management Company (УК) operations."""

    ROLE_NAME = "EmployeeWriter"  # Parsec role for management

    def __init__(self, db, parsec=None):
        self.db = db
        self.parsec = parsec

    def _verify_management_role(self, session_id: str) -> Optional[str]:
        """Проверка роли сотрудника УК через Parsec.

        Returns:
            None если проверка прошла успешно, иначе строка с ошибкой.
        """
        if not self.parsec:
            return "Parsec API не настроен, проверка роли невозможна."
        try:
            is_management = self.parsec.check_role(session_id, _MANAGEMENT_ROLE)
        except Exception as e:
            logger.error(f"CheckRole failed: {e}")
            return "Ошибка проверки роли. Попробуйте позже."
        if not is_management:
            return _ACCESS_DENIED_MSG
        return None

    # --- Blacklist operations ---

    def get_blacklist(self, session_id: str, limit: int = 50) -> Dict:
        """Получить список нарушителей из чёрного списка.

        Returns:
            {"success": bool, "data": list, "message": str}
        """
        error = self._verify_management_role(session_id)
        if error:
            return {"success": False, "data": [], "message": error}

        try:
            users = self.db.get_blacklisted_users(limit=limit)
            return {
                "success": True,
                "data": users,
                "message": f"Найдено записей в чёрном списке: {len(users)}",
            }
        except Exception as e:
            logger.error(f"get_blacklist failed: {e}")
            return {"success": False, "data": [], "message": "Ошибка получения чёрного списка."}

    def add_to_blacklist(self, session_id: str, parsec_person_id: str,
                         user_id: int = None) -> Dict:
        """Добавить жителя в чёрный список. При наличии Parsec API блокирует персону.

        Returns:
            {"success": bool, "message": str}
        """
        error = self._verify_management_role(session_id)
        if error:
            return {"success": False, "message": error}

        try:
            self.db.add_to_blacklist(
                owner_parsec_id=parsec_person_id,
                owner_user_id=user_id,
                violation_type="manual",
            )
        except Exception as e:
            logger.error(f"add_to_blacklist DB failed: {e}")
            return {"success": False, "message": "Ошибка записи в базу данных."}

        parsec_error = None
        if self.parsec:
            try:
                self.parsec.block_person(parsec_person_id)
            except Exception as e:
                logger.error(f"block_person failed for {parsec_person_id}: {e}")
                parsec_error = str(e)

        if parsec_error:
            return {
                "success": True,
                "message": (
                    f"Житель {parsec_person_id} добавлен в чёрный список, "
                    f"но ошибка блокировки в Parsec: {parsec_error}"
                ),
            }
        return {
            "success": True,
            "message": f"Житель {parsec_person_id} добавлен в чёрный список.",
        }

    def remove_from_blacklist(self, session_id: str, parsec_person_id: str) -> Dict:
        """Удалить жителя из чёрного списка. При наличии Parsec API разблокирует персону.

        Returns:
            {"success": bool, "message": str}
        """
        error = self._verify_management_role(session_id)
        if error:
            return {"success": False, "message": error}

        try:
            deleted = self.db.remove_from_blacklist(parsec_person_id)
        except Exception as e:
            logger.error(f"remove_from_blacklist DB failed: {e}")
            return {"success": False, "message": "Ошибка удаления из базы данных."}

        if deleted == 0:
            return {
                "success": False,
                "message": f"Житель {parsec_person_id} не найден в чёрном списке.",
            }

        parsec_error = None
        if self.parsec:
            try:
                self.parsec.unblock_person(parsec_person_id)
            except Exception as e:
                logger.error(f"unblock_person failed for {parsec_person_id}: {e}")
                parsec_error = str(e)

        if parsec_error:
            return {
                "success": True,
                "message": (
                    f"Житель {parsec_person_id} удалён из чёрного списка, "
                    f"но ошибка разблокировки в Parsec: {parsec_error}"
                ),
            }
        return {
            "success": True,
            "message": f"Житель {parsec_person_id} удалён из чёрного списка.",
        }

    # --- Incident operations ---

    def get_incidents(self, session_id: str, resolved: bool = None,
                      limit: int = 50) -> Dict:
        """Получить список инцидентов.

        Returns:
            {"success": bool, "data": list, "message": str}
        """
        error = self._verify_management_role(session_id)
        if error:
            return {"success": False, "data": [], "message": error}

        try:
            incidents = self.db.get_incidents(resolved=resolved, limit=limit)
            status_label = ""
            if resolved is True:
                status_label = " (закрытые)"
            elif resolved is False:
                status_label = " (открытые)"
            return {
                "success": True,
                "data": incidents,
                "message": f"Инциденты{status_label}: {len(incidents)}",
            }
        except Exception as e:
            logger.error(f"get_incidents failed: {e}")
            return {"success": False, "data": [], "message": "Ошибка получения инцидентов."}

    def resolve_incident(self, session_id: str, incident_id: int,
                         resolution: str) -> Dict:
        """Закрыть инцидент с указанием решения.

        Returns:
            {"success": bool, "message": str}
        """
        error = self._verify_management_role(session_id)
        if error:
            return {"success": False, "message": error}

        if not resolution or not resolution.strip():
            return {"success": False, "message": "Необходимо указать текст решения."}

        try:
            updated = self.db.resolve_incident(incident_id, resolution.strip())
        except Exception as e:
            logger.error(f"resolve_incident failed: {e}")
            return {"success": False, "message": "Ошибка обновления инцидента."}

        if not updated:
            return {
                "success": False,
                "message": f"Инцидент #{incident_id} не найден.",
            }
        return {
            "success": True,
            "message": f"Инцидент #{incident_id} закрыт.",
        }

    # --- Formatting methods for Telegram ---

    def format_blacklist(self, users: List[Dict]) -> str:
        """Форматирование чёрного списка для Telegram-сообщения."""
        if not users:
            return "Чёрный список пуст."

        lines = [f"Чёрный список ({len(users)} записей):"]
        for u in users:
            parsec_id = u.get("owner_parsec_id", "—")
            name = u.get("full_name") or "—"
            phone = u.get("phone_number") or "—"
            vtype = VIOLATION_TYPE_NAMES.get(
                u.get("violation_type", ""), u.get("violation_type", "—")
            )
            count = u.get("count", 0)
            last_at = u.get("last_violation_at", "—")
            # Сокращаем дату до "ДД.ММ.ГГГГ ЧЧ:ММ" для читаемости
            try:
                dt = datetime.strptime(last_at, "%Y-%m-%d %H:%M:%S")
                last_at = dt.strftime("%d.%m.%Y %H:%M")
            except (ValueError, TypeError):
                pass

            line = (
                f"• {name} | {phone}\n"
                f"  Parsec ID: {parsec_id}\n"
                f"  Тип: {vtype} | Нарушений: {count} | Последнее: {last_at}"
            )
            lines.append(line)

        return "\n\n".join(lines)

    def format_incidents(self, incidents: List[Dict]) -> str:
        """Форматирование списка инцидентов для Telegram-сообщения."""
        if not incidents:
            return "Инцидентов нет."

        lines = [f"Инциденты ({len(incidents)}):"]
        for inc in incidents:
            inc_id = inc.get("id", "?")
            itype = INCIDENT_TYPE_NAMES.get(
                inc.get("incident_type", ""), inc.get("incident_type", "—")
            )
            desc = inc.get("description") or "—"
            plate = inc.get("plate_number") or "—"
            apartment = inc.get("apartment") or "—"
            created_at = inc.get("created_at", "—")
            resolved_at = inc.get("resolved_at")
            resolution = inc.get("resolution") or "—"

            try:
                dt = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S")
                created_at = dt.strftime("%d.%m.%Y %H:%M")
            except (ValueError, TypeError):
                pass

            status = "Закрыт" if resolved_at else "Открыт"
            line = (
                f"#{inc_id} [{status}] {itype}\n"
                f"  Дата: {created_at} | Т/С: {plate} | Кв.: {apartment}\n"
                f"  Описание: {desc}"
            )
            if resolved_at:
                line += f"\n  Решение: {resolution}"
            lines.append(line)

        return "\n\n".join(lines)
