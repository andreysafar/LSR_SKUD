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


class ReportExporter:
    def __init__(self, db):
        self.db = db

    def export_passes(self, date_from: str = None, date_to: str = None,
                       subtype: str = None, format: str = "csv") -> bytes:
        """Реестр пропусков за период."""
        passes = self.db.get_active_passes_by_subtype(subtype)
        if date_from or date_to:
            filtered = []
            for p in passes:
                created = p.get("created_at", "")
                if date_from and created < date_from:
                    continue
                if date_to and created > date_to:
                    continue
                filtered.append(p)
            passes = filtered

        columns = ["id", "plate_number", "pass_subtype", "vehicle_brand",
                    "driver_phone", "valid_from", "valid_to", "status",
                    "parking_spot_id", "created_at"]
        headers = ["ID", "Номер т/с", "Тип", "Марка", "Тел. водителя",
                    "Начало", "Окончание", "Статус", "М/М", "Создан"]

        return self._export_data(passes, columns, headers, format)

    def export_entry_exit_log(self, date_from: str = None, date_to: str = None,
                                format: str = "csv") -> bytes:
        """Журнал въезда/выезда."""
        entries = self.db.get_entry_exit_log(
            limit=10000, date_from=date_from, date_to=date_to
        )
        columns = ["plate_number", "entry_time", "exit_time",
                    "duration_minutes", "pass_subtype", "entry_camera_id",
                    "exit_camera_id"]
        headers = ["Номер т/с", "Въезд", "Выезд", "Длительность (мин)",
                    "Тип пропуска", "Камера въезда", "Камера выезда"]

        return self._export_data(entries, columns, headers, format)

    def export_incidents(self, date_from: str = None, date_to: str = None,
                          format: str = "csv") -> bytes:
        """Реестр инцидентов."""
        incidents = self.db.get_incidents(limit=10000)
        if date_from or date_to:
            filtered = []
            for inc in incidents:
                created = inc.get("created_at", "")
                if date_from and created < date_from:
                    continue
                if date_to and created > date_to:
                    continue
                filtered.append(inc)
            incidents = filtered

        columns = ["id", "incident_type", "description", "plate_number",
                    "apartment", "created_at", "resolved_at", "resolution"]
        headers = ["ID", "Тип", "Описание", "Номер т/с", "Квартира",
                    "Дата", "Решено", "Решение"]

        return self._export_data(incidents, columns, headers, format)

    def export_violation_summary(self, format: str = "csv") -> bytes:
        """Сводка по нарушениям (для ЧС)."""
        with self.db.get_connection() as conn:
            rows = conn.execute("""
                SELECT v.owner_parsec_id, v.violation_type, v.count,
                       v.last_violation_at, u.full_name, u.phone_number
                FROM violation_counts v
                LEFT JOIN users u ON v.owner_user_id = u.user_id
                ORDER BY v.count DESC
            """).fetchall()

        data = [dict(r) for r in rows]
        columns = ["owner_parsec_id", "full_name", "phone_number",
                    "violation_type", "count", "last_violation_at"]
        headers = ["Parsec ID", "ФИО", "Телефон", "Тип нарушения",
                    "Кол-во", "Последнее"]

        return self._export_data(data, columns, headers, format)

    def _export_data(self, data: List[Dict], columns: List[str],
                      headers: List[str], format: str) -> bytes:
        if format == "excel" and HAS_PANDAS:
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
