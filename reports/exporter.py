"""Экспорт отчётов в CSV/Excel.

Отчёты: реестры пропусков, чёрный список, инциденты,
несоответствия меток, журнал въезда/выезда.
"""
import csv
import io
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False


def _parse_dt(value: str) -> Optional[datetime]:
    """Parse a datetime string, returning None on failure."""
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except (ValueError, TypeError):
            continue
    return None


class ReportExporter:
    def __init__(self, db):
        self.db = db

    def export_passes(self, date_from: str = None, date_to: str = None,
                       subtype: str = None,
                       export_format: str = "csv") -> bytes:
        """Реестр пропусков за период (включая исторические)."""
        # Получаем ВСЕ пропуска (не только активные) через прямой запрос
        with self.db.get_connection() as conn:
            sql = "SELECT * FROM passes WHERE 1=1"
            params: list = []
            if subtype:
                sql += " AND pass_subtype = ?"
                params.append(subtype)
            sql += " ORDER BY created_at DESC"
            rows = conn.execute(sql, params).fetchall()
        passes = [dict(r) for r in rows]

        # Фильтрация по дате — сравниваем через datetime, а не строки
        if date_from or date_to:
            dt_from = _parse_dt(date_from) if date_from else None
            dt_to = _parse_dt(date_to) if date_to else None
            filtered = []
            for p in passes:
                created = _parse_dt(p.get("created_at", ""))
                if created is None:
                    continue
                if dt_from and created < dt_from:
                    continue
                if dt_to and created > dt_to:
                    continue
                filtered.append(p)
            passes = filtered

        columns = ["id", "plate_number", "pass_subtype", "vehicle_brand",
                    "driver_phone", "valid_from", "valid_to", "status",
                    "parking_spot_id", "created_at"]
        headers = ["ID", "Номер т/с", "Тип", "Марка", "Тел. водителя",
                    "Начало", "Окончание", "Статус", "М/М", "Создан"]

        return self._export_data(passes, columns, headers, export_format)

    def export_entry_exit_log(self, date_from: str = None, date_to: str = None,
                                export_format: str = "csv") -> bytes:
        """Журнал въезда/выезда."""
        entries = self.db.get_entry_exit_log(
            limit=10000, date_from=date_from, date_to=date_to
        )
        columns = ["plate_number", "entry_time", "exit_time",
                    "duration_minutes", "pass_subtype", "entry_camera_id",
                    "exit_camera_id"]
        headers = ["Номер т/с", "Въезд", "Выезд", "Длительность (мин)",
                    "Тип пропуска", "Камера въезда", "Камера выезда"]

        return self._export_data(entries, columns, headers, export_format)

    def export_incidents(self, date_from: str = None, date_to: str = None,
                          export_format: str = "csv") -> bytes:
        """Реестр инцидентов."""
        incidents = self.db.get_incidents(limit=10000)
        if date_from or date_to:
            dt_from = _parse_dt(date_from) if date_from else None
            dt_to = _parse_dt(date_to) if date_to else None
            filtered = []
            for inc in incidents:
                created = _parse_dt(inc.get("created_at", ""))
                if created is None:
                    continue
                if dt_from and created < dt_from:
                    continue
                if dt_to and created > dt_to:
                    continue
                filtered.append(inc)
            incidents = filtered

        columns = ["id", "incident_type", "description", "plate_number",
                    "apartment", "created_at", "resolved_at", "resolution"]
        headers = ["ID", "Тип", "Описание", "Номер т/с", "Квартира",
                    "Дата", "Решено", "Решение"]

        return self._export_data(incidents, columns, headers, export_format)

    def export_violation_summary(self, export_format: str = "csv") -> bytes:
        """Сводка по нарушениям (для ЧС)."""
        with self.db.get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM violation_counts ORDER BY count DESC"
            ).fetchall()
            violation_data = [dict(r) for r in rows]

        # Обогащаем данными пользователей
        data = []
        for v in violation_data:
            entry = dict(v)
            if v.get("owner_user_id"):
                user = self.db.get_user(v["owner_user_id"])
                if user:
                    entry["full_name"] = user.get("full_name", "")
                    entry["phone_number"] = user.get("phone_number", "")
            data.append(entry)

        columns = ["owner_parsec_id", "full_name", "phone_number",
                    "violation_type", "count", "last_violation_at"]
        headers = ["Parsec ID", "ФИО", "Телефон", "Тип нарушения",
                    "Кол-во", "Последнее"]

        return self._export_data(data, columns, headers, export_format)

    def export_blacklist(self, violation_threshold: int = 2,
                          export_format: str = "csv") -> bytes:
        """Экспорт чёрного списка: лица с нарушениями >= порога."""
        with self.db.get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM violation_counts WHERE count >= ? "
                "ORDER BY count DESC",
                (violation_threshold,),
            ).fetchall()
            violation_data = [dict(r) for r in rows]

        # Обогащаем данными пользователей
        data = []
        for v in violation_data:
            entry = dict(v)
            if v.get("owner_user_id"):
                user = self.db.get_user(v["owner_user_id"])
                if user:
                    entry["full_name"] = user.get("full_name", "")
                    entry["phone_number"] = user.get("phone_number", "")
                    entry["apartment"] = user.get("apartment", "")
            data.append(entry)

        columns = ["owner_parsec_id", "full_name", "phone_number",
                    "apartment", "violation_type", "count",
                    "last_violation_at"]
        headers = ["Parsec ID", "ФИО", "Телефон", "Квартира",
                    "Тип нарушения", "Кол-во", "Последнее"]

        return self._export_data(data, columns, headers, export_format)

    def _export_data(self, data: List[Dict], columns: List[str],
                      headers: List[str], export_format: str) -> bytes:
        if export_format == "excel":
            if not HAS_PANDAS:
                raise RuntimeError(
                    "Excel export requires pandas and openpyxl. "
                    "Install them with: pip install pandas openpyxl"
                )
            return self._to_excel(data, columns, headers)
        return self._to_csv(data, columns, headers)

    def _to_csv(self, data: List[Dict], columns: List[str],
                 headers: List[str]) -> bytes:
        output = io.StringIO()
        writer = csv.writer(output, delimiter=";")
        writer.writerow(headers)
        for row in data:
            writer.writerow([row.get(col, "") for col in columns])
        return output.getvalue().encode("utf-8-sig")

    def _to_excel(self, data: List[Dict], columns: List[str],
                    headers: List[str]) -> bytes:
        rows = []
        for row in data:
            rows.append({h: row.get(c, "") for h, c in zip(headers, columns)})
        df = pd.DataFrame(rows)
        output = io.BytesIO()
        df.to_excel(output, index=False, engine="openpyxl")
        return output.getvalue()
