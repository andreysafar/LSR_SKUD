import sqlite3
import os
import json
import threading
from datetime import datetime
from typing import Optional, List, Dict, Any
from contextlib import contextmanager


class Database:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, db_path: str = "data/gate_control.db"):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self, db_path: str = "data/gate_control.db"):
        if self._initialized:
            return
        self.db_path = db_path
        try:
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
        except OSError:
            pass
        self._local = threading.local()
        self._init_schema()
        self._initialized = True

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path)
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA foreign_keys=ON")
        return self._local.conn

    @contextmanager
    def get_connection(self):
        conn = self._get_conn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def _init_schema(self):
        with self.get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    phone_number TEXT,
                    parsec_person_id TEXT,
                    full_name TEXT,
                    default_access_group TEXT,
                    is_admin INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now'))
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS passes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    pass_type TEXT NOT NULL,
                    plate_number TEXT,
                    access_group_id TEXT,
                    access_group_name TEXT,
                    valid_from TEXT NOT NULL,
                    valid_to TEXT NOT NULL,
                    status TEXT DEFAULT 'active',
                    parsec_pass_id TEXT,
                    created_at TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS cameras (
                    camera_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    stream_url TEXT NOT NULL,
                    gate_device_id TEXT,
                    mask_path TEXT,
                    weights_vehicle TEXT DEFAULT 'models/yolo26n.pt',
                    weights_plate TEXT DEFAULT 'models/license_plate_detector.pt',
                    enabled INTEGER DEFAULT 1,
                    last_frame_at TEXT,
                    status TEXT DEFAULT 'offline',
                    created_at TEXT DEFAULT (datetime('now'))
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS recognition_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    camera_id TEXT NOT NULL,
                    timestamp TEXT DEFAULT (datetime('now')),
                    frame_path TEXT,
                    vehicle_detected INTEGER DEFAULT 0,
                    vehicle_confidence REAL,
                    vehicle_class TEXT,
                    vehicle_bbox TEXT,
                    plate_detected INTEGER DEFAULT 0,
                    plate_confidence REAL,
                    plate_bbox TEXT,
                    plate_image_path TEXT,
                    ocr_text TEXT,
                    ocr_confidence REAL,
                    ocr_corrected TEXT,
                    final_plate TEXT,
                    matched_pass_id INTEGER,
                    gate_opened INTEGER DEFAULT 0,
                    admin_vehicle_confirm INTEGER,
                    admin_plate_confirm INTEGER,
                    admin_ocr_confirm INTEGER,
                    admin_reviewed INTEGER DEFAULT 0,
                    telegram_message_id INTEGER,
                    FOREIGN KEY (camera_id) REFERENCES cameras(camera_id),
                    FOREIGN KEY (matched_pass_id) REFERENCES passes(id)
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS training_samples (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    camera_id TEXT NOT NULL,
                    event_id INTEGER,
                    stage TEXT NOT NULL,
                    image_path TEXT NOT NULL,
                    label TEXT,
                    is_positive INTEGER,
                    corrected_value TEXT,
                    used_in_training INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (camera_id) REFERENCES cameras(camera_id),
                    FOREIGN KEY (event_id) REFERENCES recognition_events(id)
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS training_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    camera_id TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    samples_count INTEGER,
                    started_at TEXT,
                    completed_at TEXT,
                    status TEXT DEFAULT 'pending',
                    metrics TEXT,
                    weights_path TEXT,
                    FOREIGN KEY (camera_id) REFERENCES cameras(camera_id)
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS gate_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    camera_id TEXT NOT NULL,
                    plate_number TEXT NOT NULL,
                    pass_id INTEGER,
                    action TEXT NOT NULL,
                    success INTEGER DEFAULT 0,
                    timestamp TEXT DEFAULT (datetime('now')),
                    details TEXT,
                    FOREIGN KEY (camera_id) REFERENCES cameras(camera_id),
                    FOREIGN KEY (pass_id) REFERENCES passes(id)
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS parking_spots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    spot_number TEXT NOT NULL UNIQUE,
                    owner_parsec_id TEXT,
                    owner_user_id INTEGER,
                    level TEXT,
                    section TEXT,
                    is_active INTEGER DEFAULT 1,
                    created_at TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (owner_user_id) REFERENCES users(user_id)
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS entry_exit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    plate_number TEXT NOT NULL,
                    tag_code TEXT,
                    entry_camera_id TEXT,
                    entry_time TEXT,
                    exit_camera_id TEXT,
                    exit_time TEXT,
                    duration_minutes REAL,
                    pass_id INTEGER,
                    pass_subtype TEXT,
                    owner_parsec_id TEXT,
                    owner_user_id INTEGER,
                    created_at TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (entry_camera_id) REFERENCES cameras(camera_id),
                    FOREIGN KEY (exit_camera_id) REFERENCES cameras(camera_id),
                    FOREIGN KEY (pass_id) REFERENCES passes(id)
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS incidents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    incident_type TEXT NOT NULL,
                    description TEXT,
                    plate_number TEXT,
                    apartment TEXT,
                    pass_id INTEGER,
                    entry_exit_id INTEGER,
                    reported_by_user_id INTEGER,
                    reported_by_role TEXT,
                    resolved_at TEXT,
                    resolution TEXT,
                    created_at TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (pass_id) REFERENCES passes(id),
                    FOREIGN KEY (entry_exit_id) REFERENCES entry_exit_log(id),
                    FOREIGN KEY (reported_by_user_id) REFERENCES users(user_id)
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS violation_counts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    owner_parsec_id TEXT NOT NULL,
                    owner_user_id INTEGER,
                    violation_type TEXT NOT NULL,
                    count INTEGER DEFAULT 1,
                    last_violation_at TEXT DEFAULT (datetime('now')),
                    UNIQUE(owner_parsec_id, violation_type)
                )
            """)

            # Indexes (on columns that exist in the base schema)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_passes_plate ON passes(plate_number)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_passes_status ON passes(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_recognition_camera ON recognition_events(camera_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_recognition_plate ON recognition_events(final_plate)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_training_camera_stage ON training_samples(camera_id, stage)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_gate_events_plate ON gate_events(plate_number)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_entry_exit_plate ON entry_exit_log(plate_number)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_entry_exit_open ON entry_exit_log(plate_number, exit_time)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_entry_exit_owner ON entry_exit_log(owner_parsec_id, exit_time)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_incidents_type ON incidents(incident_type)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_incidents_plate ON incidents(plate_number)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_incidents_resolved ON incidents(resolved_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_parking_spots_owner ON parking_spots(owner_parsec_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_parking_spots_user ON parking_spots(owner_user_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_violation_counts_owner ON violation_counts(owner_parsec_id)")

            # Миграции: добавление новых столбцов к существующим таблицам
            self._migrate_schema(conn)

            # Indexes on migrated columns (must come after _migrate_schema)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_passes_subtype ON passes(pass_subtype)")

    def _migrate_schema(self, conn: sqlite3.Connection):
        """Добавление новых столбцов к существующим таблицам (безопасная миграция)."""
        migrations = [
            # passes: подтип пропуска, м/м, телефон водителя, марка, макс. длительность
            ("passes", "pass_subtype", "TEXT DEFAULT 'regular'"),
            ("passes", "parking_spot_id", "INTEGER"),
            ("passes", "driver_phone", "TEXT"),
            ("passes", "vehicle_brand", "TEXT"),
            ("passes", "max_duration_min", "INTEGER"),
            ("passes", "owner_parsec_id", "TEXT"),
            # cameras: направление камеры (entry/exit/both)
            ("cameras", "direction", "TEXT DEFAULT 'both'"),
            # cameras: тип распознавания (gpu/parsec_native)
            ("cameras", "recognition_type", "TEXT DEFAULT 'gpu'"),
        ]
        for table, column, col_type in migrations:
            try:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
            except sqlite3.OperationalError:
                pass  # Столбец уже существует

    def save_user(self, user_id: int, phone_number: str = None,
                  parsec_person_id: str = None, full_name: str = None) -> Dict:
        with self.get_connection() as conn:
            conn.execute("""
                INSERT INTO users (user_id, phone_number, parsec_person_id, full_name)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    phone_number = COALESCE(excluded.phone_number, phone_number),
                    parsec_person_id = COALESCE(excluded.parsec_person_id, parsec_person_id),
                    full_name = COALESCE(excluded.full_name, full_name),
                    updated_at = datetime('now')
            """, (user_id, phone_number, parsec_person_id, full_name))
            row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
            return dict(row) if row else {}

    def get_user(self, user_id: int) -> Optional[Dict]:
        with self.get_connection() as conn:
            row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
            return dict(row) if row else None

    def get_user_by_phone(self, phone: str) -> Optional[Dict]:
        with self.get_connection() as conn:
            phone_clean = phone.replace("+", "").replace(" ", "").replace("-", "")
            row = conn.execute(
                "SELECT * FROM users WHERE REPLACE(REPLACE(REPLACE(phone_number, '+', ''), ' ', ''), '-', '') = ?",
                (phone_clean,)
            ).fetchone()
            return dict(row) if row else None

    def set_default_access_group(self, user_id: int, group_id: str) -> bool:
        with self.get_connection() as conn:
            conn.execute(
                "UPDATE users SET default_access_group = ?, updated_at = datetime('now') WHERE user_id = ?",
                (group_id, user_id)
            )
            return True

    def create_pass(self, user_id: int, pass_type: str, valid_from: str,
                    valid_to: str, plate_number: str = None,
                    access_group_id: str = None, access_group_name: str = None,
                    parsec_pass_id: str = None) -> Dict:
        with self.get_connection() as conn:
            cursor = conn.execute("""
                INSERT INTO passes (user_id, pass_type, plate_number, access_group_id,
                    access_group_name, valid_from, valid_to, parsec_pass_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (user_id, pass_type, plate_number, access_group_id,
                  access_group_name, valid_from, valid_to, parsec_pass_id))
            row = conn.execute("SELECT * FROM passes WHERE id = ?", (cursor.lastrowid,)).fetchone()
            return dict(row) if row else {}

    def get_active_passes(self, user_id: int = None) -> List[Dict]:
        with self.get_connection() as conn:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if user_id is not None:
                rows = conn.execute(
                    "SELECT * FROM passes WHERE user_id = ? AND status = 'active' AND valid_to > ? ORDER BY created_at DESC",
                    (user_id, now)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM passes WHERE status = 'active' AND valid_to > ? ORDER BY created_at DESC",
                    (now,)
                ).fetchall()
            return [dict(r) for r in rows]

    def find_active_pass_by_plate(self, plate_number: str) -> Optional[Dict]:
        with self.get_connection() as conn:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            plate_clean = plate_number.upper().replace(" ", "")
            row = conn.execute("""
                SELECT * FROM passes
                WHERE UPPER(REPLACE(plate_number, ' ', '')) = ?
                AND status = 'active' AND valid_to > ?
                ORDER BY valid_to DESC LIMIT 1
            """, (plate_clean, now)).fetchone()
            return dict(row) if row else None

    def deactivate_pass(self, pass_id: int) -> bool:
        with self.get_connection() as conn:
            cursor = conn.execute(
                "UPDATE passes SET status = 'expired' WHERE id = ?", (pass_id,)
            )
            return cursor.rowcount > 0

    def save_camera(self, camera_id: str, name: str, stream_url: str,
                    gate_device_id: str = "", mask_path: str = "",
                    direction: str = 'both',
                    recognition_type: str = 'gpu') -> Dict:
        with self.get_connection() as conn:
            conn.execute("""
                INSERT INTO cameras (camera_id, name, stream_url, gate_device_id, mask_path,
                    direction, recognition_type)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(camera_id) DO UPDATE SET
                    name = excluded.name,
                    stream_url = excluded.stream_url,
                    gate_device_id = COALESCE(NULLIF(excluded.gate_device_id, ''), gate_device_id),
                    mask_path = COALESCE(NULLIF(excluded.mask_path, ''), mask_path),
                    direction = COALESCE(NULLIF(excluded.direction, ''), direction),
                    recognition_type = COALESCE(NULLIF(excluded.recognition_type, ''), recognition_type)
            """, (camera_id, name, stream_url, gate_device_id, mask_path,
                  direction, recognition_type))
            row = conn.execute("SELECT * FROM cameras WHERE camera_id = ?", (camera_id,)).fetchone()
            return dict(row) if row else {}

    def get_cameras(self, enabled_only: bool = False) -> List[Dict]:
        with self.get_connection() as conn:
            if enabled_only:
                rows = conn.execute("SELECT * FROM cameras WHERE enabled = 1").fetchall()
            else:
                rows = conn.execute("SELECT * FROM cameras").fetchall()
            return [dict(r) for r in rows]

    def update_camera_status(self, camera_id: str, status: str):
        with self.get_connection() as conn:
            conn.execute(
                "UPDATE cameras SET status = ?, last_frame_at = datetime('now') WHERE camera_id = ?",
                (status, camera_id)
            )

    def save_recognition_event(self, camera_id: str, **kwargs) -> int:
        with self.get_connection() as conn:
            fields = ["camera_id"]
            values = [camera_id]
            placeholders = ["?"]
            for k, v in kwargs.items():
                fields.append(k)
                values.append(json.dumps(v) if isinstance(v, (list, dict)) else v)
                placeholders.append("?")
            sql = f"INSERT INTO recognition_events ({', '.join(fields)}) VALUES ({', '.join(placeholders)})"
            cursor = conn.execute(sql, values)
            return cursor.lastrowid

    def get_recognition_events(self, camera_id: str = None, limit: int = 50,
                                plate_filter: str = None) -> List[Dict]:
        with self.get_connection() as conn:
            sql = "SELECT * FROM recognition_events WHERE 1=1"
            params = []
            if camera_id:
                sql += " AND camera_id = ?"
                params.append(camera_id)
            if plate_filter:
                sql += " AND (final_plate LIKE ? OR ocr_text LIKE ?)"
                params.extend([f"%{plate_filter}%", f"%{plate_filter}%"])
            sql += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]

    def update_recognition_event(self, event_id: int, **kwargs):
        with self.get_connection() as conn:
            sets = []
            values = []
            for k, v in kwargs.items():
                sets.append(f"{k} = ?")
                values.append(v)
            values.append(event_id)
            conn.execute(
                f"UPDATE recognition_events SET {', '.join(sets)} WHERE id = ?",
                values
            )

    def save_training_sample(self, camera_id: str, stage: str,
                              image_path: str, event_id: int = None,
                              label: str = None, is_positive: int = None,
                              corrected_value: str = None) -> int:
        with self.get_connection() as conn:
            cursor = conn.execute("""
                INSERT INTO training_samples (camera_id, event_id, stage, image_path,
                    label, is_positive, corrected_value)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (camera_id, event_id, stage, image_path, label, is_positive, corrected_value))
            return cursor.lastrowid

    def get_training_samples_count(self, camera_id: str, stage: str,
                                    unused_only: bool = True) -> int:
        with self.get_connection() as conn:
            sql = "SELECT COUNT(*) FROM training_samples WHERE camera_id = ? AND stage = ?"
            params = [camera_id, stage]
            if unused_only:
                sql += " AND used_in_training = 0"
            row = conn.execute(sql, params).fetchone()
            return row[0] if row else 0

    def get_training_samples(self, camera_id: str, stage: str,
                              unused_only: bool = True) -> List[Dict]:
        with self.get_connection() as conn:
            sql = "SELECT * FROM training_samples WHERE camera_id = ? AND stage = ?"
            params = [camera_id, stage]
            if unused_only:
                sql += " AND used_in_training = 0"
            sql += " ORDER BY created_at"
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]

    def mark_samples_used(self, sample_ids: List[int]):
        if not sample_ids:
            return
        with self.get_connection() as conn:
            placeholders = ",".join(["?"] * len(sample_ids))
            conn.execute(
                f"UPDATE training_samples SET used_in_training = 1 WHERE id IN ({placeholders})",
                sample_ids
            )

    def save_training_session(self, camera_id: str, stage: str,
                               samples_count: int) -> int:
        with self.get_connection() as conn:
            cursor = conn.execute("""
                INSERT INTO training_sessions (camera_id, stage, samples_count,
                    started_at, status)
                VALUES (?, ?, ?, datetime('now'), 'running')
            """, (camera_id, stage, samples_count))
            return cursor.lastrowid

    def update_training_session(self, session_id: int, **kwargs):
        with self.get_connection() as conn:
            sets = []
            values = []
            for k, v in kwargs.items():
                sets.append(f"{k} = ?")
                values.append(json.dumps(v) if isinstance(v, (dict, list)) else v)
            values.append(session_id)
            conn.execute(
                f"UPDATE training_sessions SET {', '.join(sets)} WHERE id = ?",
                values
            )

    def get_training_sessions(self, camera_id: str = None,
                               limit: int = 20) -> List[Dict]:
        with self.get_connection() as conn:
            sql = "SELECT * FROM training_sessions WHERE 1=1"
            params = []
            if camera_id:
                sql += " AND camera_id = ?"
                params.append(camera_id)
            sql += " ORDER BY started_at DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]

    def save_gate_event(self, camera_id: str, plate_number: str,
                        action: str, pass_id: int = None,
                        success: bool = False, details: str = None) -> int:
        with self.get_connection() as conn:
            cursor = conn.execute("""
                INSERT INTO gate_events (camera_id, plate_number, pass_id,
                    action, success, details)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (camera_id, plate_number, pass_id, action,
                  1 if success else 0, details))
            return cursor.lastrowid

    def get_gate_events(self, limit: int = 50, camera_id: str = None) -> List[Dict]:
        with self.get_connection() as conn:
            sql = "SELECT * FROM gate_events WHERE 1=1"
            params = []
            if camera_id:
                sql += " AND camera_id = ?"
                params.append(camera_id)
            sql += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]

    # --- Parking spots ---

    def save_parking_spot(self, spot_number: str, owner_parsec_id: str = None,
                          owner_user_id: int = None, level: str = None,
                          section: str = None) -> Dict:
        with self.get_connection() as conn:
            conn.execute("""
                INSERT INTO parking_spots (spot_number, owner_parsec_id, owner_user_id, level, section)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(spot_number) DO UPDATE SET
                    owner_parsec_id = COALESCE(NULLIF(excluded.owner_parsec_id, ''), owner_parsec_id),
                    owner_user_id = COALESCE(excluded.owner_user_id, owner_user_id),
                    level = COALESCE(NULLIF(excluded.level, ''), level),
                    section = COALESCE(NULLIF(excluded.section, ''), section)
            """, (spot_number, owner_parsec_id, owner_user_id, level, section))
            row = conn.execute("SELECT * FROM parking_spots WHERE spot_number = ?", (spot_number,)).fetchone()
            return dict(row) if row else {}

    def get_parking_spots(self, owner_parsec_id: str = None,
                          owner_user_id: int = None) -> List[Dict]:
        with self.get_connection() as conn:
            if owner_parsec_id:
                rows = conn.execute(
                    "SELECT * FROM parking_spots WHERE owner_parsec_id = ? AND is_active = 1",
                    (owner_parsec_id,)
                ).fetchall()
            elif owner_user_id:
                rows = conn.execute(
                    "SELECT * FROM parking_spots WHERE owner_user_id = ? AND is_active = 1",
                    (owner_user_id,)
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM parking_spots WHERE is_active = 1").fetchall()
            return [dict(r) for r in rows]

    def get_parking_spots_count(self, owner_parsec_id: str) -> int:
        with self.get_connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM parking_spots WHERE owner_parsec_id = ? AND is_active = 1",
                (owner_parsec_id,)
            ).fetchone()
            return row[0] if row else 0

    # --- Entry/Exit log ---

    def record_entry(self, plate_number: str, camera_id: str,
                     pass_id: int = None, pass_subtype: str = None,
                     tag_code: str = None, owner_parsec_id: str = None,
                     owner_user_id: int = None) -> int:
        with self.get_connection() as conn:
            cursor = conn.execute("""
                INSERT INTO entry_exit_log (plate_number, entry_camera_id, entry_time,
                    pass_id, pass_subtype, tag_code, owner_parsec_id, owner_user_id)
                VALUES (?, ?, datetime('now'), ?, ?, ?, ?, ?)
            """, (plate_number, camera_id, pass_id, pass_subtype,
                  tag_code, owner_parsec_id, owner_user_id))
            return cursor.lastrowid

    def record_exit(self, plate_number: str, camera_id: str) -> Optional[Dict]:
        with self.get_connection() as conn:
            plate_clean = plate_number.upper().replace(" ", "")
            row = conn.execute("""
                SELECT * FROM entry_exit_log
                WHERE UPPER(REPLACE(plate_number, ' ', '')) = ?
                AND exit_time IS NULL
                ORDER BY entry_time DESC LIMIT 1
            """, (plate_clean,)).fetchone()
            if row:
                conn.execute("""
                    UPDATE entry_exit_log SET
                        exit_camera_id = ?,
                        exit_time = datetime('now'),
                        duration_minutes = ROUND(
                            (julianday('now') - julianday(entry_time)) * 24 * 60, 1
                        )
                    WHERE id = ?
                """, (camera_id, row["id"]))
                updated = conn.execute(
                    "SELECT * FROM entry_exit_log WHERE id = ?", (row["id"],)
                ).fetchone()
                return dict(updated) if updated else None
            return None

    def get_vehicles_on_premises(self, owner_parsec_id: str = None) -> List[Dict]:
        """Т/С, которые сейчас на территории (entry есть, exit нет)."""
        with self.get_connection() as conn:
            if owner_parsec_id:
                rows = conn.execute("""
                    SELECT * FROM entry_exit_log
                    WHERE owner_parsec_id = ? AND exit_time IS NULL
                    ORDER BY entry_time DESC
                """, (owner_parsec_id,)).fetchall()
            else:
                rows = conn.execute("""
                    SELECT * FROM entry_exit_log
                    WHERE exit_time IS NULL
                    ORDER BY entry_time DESC
                """).fetchall()
            return [dict(r) for r in rows]

    def count_vehicles_on_premises(self, owner_parsec_id: str) -> int:
        with self.get_connection() as conn:
            row = conn.execute("""
                SELECT COUNT(*) FROM entry_exit_log
                WHERE owner_parsec_id = ? AND exit_time IS NULL
            """, (owner_parsec_id,)).fetchone()
            return row[0] if row else 0

    def get_entry_exit_log(self, limit: int = 50, plate_filter: str = None,
                           date_from: str = None, date_to: str = None) -> List[Dict]:
        with self.get_connection() as conn:
            sql = "SELECT * FROM entry_exit_log WHERE 1=1"
            params = []
            if plate_filter:
                sql += " AND plate_number LIKE ?"
                params.append(f"%{plate_filter}%")
            if date_from:
                sql += " AND entry_time >= ?"
                params.append(date_from)
            if date_to:
                sql += " AND entry_time <= ?"
                params.append(date_to)
            sql += " ORDER BY entry_time DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]

    # --- Incidents ---

    def create_incident(self, incident_type: str, description: str = None,
                        plate_number: str = None, apartment: str = None,
                        pass_id: int = None, entry_exit_id: int = None,
                        reported_by_user_id: int = None,
                        reported_by_role: str = None) -> int:
        with self.get_connection() as conn:
            cursor = conn.execute("""
                INSERT INTO incidents (incident_type, description, plate_number,
                    apartment, pass_id, entry_exit_id, reported_by_user_id, reported_by_role)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (incident_type, description, plate_number, apartment,
                  pass_id, entry_exit_id, reported_by_user_id, reported_by_role))
            return cursor.lastrowid

    def get_incidents(self, limit: int = 50, incident_type: str = None,
                      resolved: bool = None) -> List[Dict]:
        with self.get_connection() as conn:
            sql = "SELECT * FROM incidents WHERE 1=1"
            params = []
            if incident_type:
                sql += " AND incident_type = ?"
                params.append(incident_type)
            if resolved is True:
                sql += " AND resolved_at IS NOT NULL"
            elif resolved is False:
                sql += " AND resolved_at IS NULL"
            sql += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]

    def resolve_incident(self, incident_id: int, resolution: str) -> bool:
        with self.get_connection() as conn:
            cursor = conn.execute("""
                UPDATE incidents SET resolved_at = datetime('now'), resolution = ?
                WHERE id = ?
            """, (resolution, incident_id))
            return cursor.rowcount > 0

    # --- Violation counts ---

    def increment_violation(self, owner_parsec_id: str, violation_type: str,
                            owner_user_id: int = None) -> int:
        """Инкремент счётчика нарушений. Возвращает новое значение count."""
        with self.get_connection() as conn:
            conn.execute("""
                INSERT INTO violation_counts (owner_parsec_id, owner_user_id, violation_type, count)
                VALUES (?, ?, ?, 1)
                ON CONFLICT(owner_parsec_id, violation_type) DO UPDATE SET
                    count = count + 1,
                    last_violation_at = datetime('now'),
                    owner_user_id = COALESCE(excluded.owner_user_id, owner_user_id)
            """, (owner_parsec_id, owner_user_id, violation_type))
            row = conn.execute("""
                SELECT count FROM violation_counts
                WHERE owner_parsec_id = ? AND violation_type = ?
            """, (owner_parsec_id, violation_type)).fetchone()
            return row[0] if row else 1

    def get_violation_count(self, owner_parsec_id: str,
                            violation_type: str = None) -> int:
        with self.get_connection() as conn:
            if violation_type:
                row = conn.execute("""
                    SELECT count FROM violation_counts
                    WHERE owner_parsec_id = ? AND violation_type = ?
                """, (owner_parsec_id, violation_type)).fetchone()
                return (row[0] or 0) if row else 0
            else:
                row = conn.execute("""
                    SELECT COALESCE(SUM(count), 0) FROM violation_counts
                    WHERE owner_parsec_id = ?
                """, (owner_parsec_id,)).fetchone()
                return (row[0] or 0) if row else 0

    # --- Extended pass creation ---

    def create_pass_extended(self, user_id: int, pass_type: str,
                             valid_from: str, valid_to: str,
                             plate_number: str = None,
                             pass_subtype: str = 'regular',
                             parking_spot_id: int = None,
                             driver_phone: str = None,
                             vehicle_brand: str = None,
                             max_duration_min: int = None,
                             owner_parsec_id: str = None,
                             access_group_id: str = None,
                             access_group_name: str = None,
                             parsec_pass_id: str = None) -> Dict:
        with self.get_connection() as conn:
            cursor = conn.execute("""
                INSERT INTO passes (user_id, pass_type, plate_number, access_group_id,
                    access_group_name, valid_from, valid_to, parsec_pass_id,
                    pass_subtype, parking_spot_id, driver_phone, vehicle_brand,
                    max_duration_min, owner_parsec_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (user_id, pass_type, plate_number, access_group_id,
                  access_group_name, valid_from, valid_to, parsec_pass_id,
                  pass_subtype, parking_spot_id, driver_phone, vehicle_brand,
                  max_duration_min, owner_parsec_id))
            row = conn.execute("SELECT * FROM passes WHERE id = ?", (cursor.lastrowid,)).fetchone()
            return dict(row) if row else {}

    def get_active_passes_by_subtype(self, subtype: str = None,
                                      user_id: int = None) -> List[Dict]:
        with self.get_connection() as conn:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            sql = "SELECT * FROM passes WHERE status = 'active' AND valid_to > ?"
            params = [now]
            if subtype:
                sql += " AND pass_subtype = ?"
                params.append(subtype)
            if user_id is not None:
                sql += " AND user_id = ?"
                params.append(user_id)
            sql += " ORDER BY created_at DESC"
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]

    def get_stats(self) -> Dict:
        with self.get_connection() as conn:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            today = datetime.now().strftime("%Y-%m-%d")
            stats = {
                "total_users": conn.execute("SELECT COUNT(*) FROM users").fetchone()[0],
                "active_passes": conn.execute(
                    "SELECT COUNT(*) FROM passes WHERE status='active' AND valid_to > ?", (now,)
                ).fetchone()[0],
                "vehicle_passes": conn.execute(
                    "SELECT COUNT(*) FROM passes WHERE pass_type='vehicle' AND status='active' AND valid_to > ?", (now,)
                ).fetchone()[0],
                "cameras_online": conn.execute(
                    "SELECT COUNT(*) FROM cameras WHERE status='online'"
                ).fetchone()[0],
                "cameras_total": conn.execute("SELECT COUNT(*) FROM cameras").fetchone()[0],
                "recognitions_today": conn.execute(
                    "SELECT COUNT(*) FROM recognition_events WHERE timestamp >= ?", (today,)
                ).fetchone()[0],
                "gates_opened_today": conn.execute(
                    "SELECT COUNT(*) FROM gate_events WHERE timestamp >= ? AND success=1", (today,)
                ).fetchone()[0],
                "pending_reviews": conn.execute(
                    "SELECT COUNT(*) FROM recognition_events WHERE admin_reviewed=0 AND vehicle_detected=1"
                ).fetchone()[0],
                "vehicles_on_premises": conn.execute(
                    "SELECT COUNT(*) FROM entry_exit_log WHERE exit_time IS NULL"
                ).fetchone()[0],
                "loading_passes_active": conn.execute(
                    "SELECT COUNT(*) FROM passes WHERE pass_subtype='loading' AND status='active' AND valid_to > ?",
                    (now,)
                ).fetchone()[0],
                "guest_passes_active": conn.execute(
                    "SELECT COUNT(*) FROM passes WHERE pass_subtype='guest' AND status='active' AND valid_to > ?",
                    (now,)
                ).fetchone()[0],
                "incidents_unresolved": conn.execute(
                    "SELECT COUNT(*) FROM incidents WHERE resolved_at IS NULL"
                ).fetchone()[0],
                "training_samples": {},
            }
            stages = ["vehicle", "plate", "ocr"]
            for stage in stages:
                count = conn.execute(
                    "SELECT COUNT(*) FROM training_samples WHERE stage=? AND used_in_training=0",
                    (stage,)
                ).fetchone()[0]
                stats["training_samples"][stage] = count
            return stats


_db_instance: Optional[Database] = None


def get_db(db_path: str = "data/gate_control.db") -> Database:
    global _db_instance
    if _db_instance is None:
        _db_instance = Database(db_path)
    return _db_instance
