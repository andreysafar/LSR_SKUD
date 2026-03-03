import sqlite3
import threading
import json
import uuid
from contextlib import contextmanager
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import asdict

from config.anpr_config import ANPRProcessingMetrics


class ANPRDatabase:
    """Database layer for ANPR batch processing operations."""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._local = threading.local()
        self._lock = threading.Lock()
        self._ensure_anpr_tables()
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get thread-local database connection."""
        if not hasattr(self._local, 'connection'):
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA cache_size=10000")
            conn.execute("PRAGMA temp_store=MEMORY")
            conn.row_factory = sqlite3.Row
            self._local.connection = conn
        return self._local.connection
    
    @contextmanager
    def get_connection(self):
        """Context manager for database transactions."""
        conn = self._get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    
    def _ensure_anpr_tables(self):
        """Ensure all ANPR-related tables exist."""
        with self.get_connection() as conn:
            # Batch processing sessions table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS batch_processing_sessions (
                    id INTEGER PRIMARY KEY,
                    session_id TEXT UNIQUE NOT NULL,
                    start_time TIMESTAMP NOT NULL,
                    end_time TIMESTAMP NULL,
                    input_directories TEXT NOT NULL,
                    total_files INTEGER DEFAULT 0,
                    processed_files INTEGER DEFAULT 0,
                    success_files INTEGER DEFAULT 0,
                    error_files INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'RUNNING' CHECK (status IN ('RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED')),
                    config_snapshot TEXT NOT NULL,
                    error_message TEXT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Batch processing results table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS batch_processing_results (
                    id INTEGER PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    folder_name TEXT NOT NULL,
                    subfolder_name TEXT NOT NULL,
                    plate_text TEXT NULL,
                    confidence REAL NULL,
                    processing_time REAL NOT NULL,
                    timestamp TIMESTAMP NOT NULL,
                    image_path TEXT NULL,
                    error_message TEXT NULL,
                    status TEXT DEFAULT 'SUCCESS' CHECK (status IN ('SUCCESS', 'FAILED', 'SKIPPED')),
                    frame_count INTEGER NULL,
                    vehicle_detected BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES batch_processing_sessions(session_id)
                )
            """)
            
            # Performance metrics table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS batch_processing_metrics (
                    id INTEGER PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    metric_name TEXT NOT NULL,
                    metric_value REAL NOT NULL,
                    metric_type TEXT NOT NULL,
                    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES batch_processing_sessions(session_id)
                )
            """)
            
            # GPU utilization tracking
            conn.execute("""
                CREATE TABLE IF NOT EXISTS gpu_utilization_log (
                    id INTEGER PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    gpu_id INTEGER NOT NULL,
                    utilization_percent REAL NOT NULL,
                    memory_used_mb REAL NOT NULL,
                    memory_total_mb REAL NOT NULL,
                    temperature_c REAL NULL,
                    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES batch_processing_sessions(session_id)
                )
            """)
            
            # Create indexes for better performance
            conn.execute("CREATE INDEX IF NOT EXISTS idx_batch_sessions_status ON batch_processing_sessions(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_batch_sessions_start_time ON batch_processing_sessions(start_time)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_batch_results_session_id ON batch_processing_results(session_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_batch_results_timestamp ON batch_processing_results(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_batch_results_status ON batch_processing_results(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_batch_metrics_session_id ON batch_processing_metrics(session_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_gpu_utilization_session_id ON gpu_utilization_log(session_id)")
    
    def create_batch_session(self, session_id: str, config: Dict[str, Any], 
                           input_directories: List[str]) -> str:
        """Create a new batch processing session."""
        with self.get_connection() as conn:
            conn.execute("""
                INSERT INTO batch_processing_sessions 
                (session_id, start_time, input_directories, config_snapshot, status)
                VALUES (?, ?, ?, ?, 'RUNNING')
            """, (
                session_id,
                datetime.now(),
                ",".join(input_directories),
                json.dumps(config)
            ))
        return session_id
    
    def update_session_totals(self, session_id: str, total_files: int):
        """Update the total files count for a session."""
        with self.get_connection() as conn:
            conn.execute("""
                UPDATE batch_processing_sessions 
                SET total_files = ?, updated_at = CURRENT_TIMESTAMP
                WHERE session_id = ?
            """, (total_files, session_id))
    
    def complete_session(self, session_id: str, status: str = "COMPLETED", 
                        error_message: Optional[str] = None):
        """Mark a batch processing session as completed."""
        with self.get_connection() as conn:
            conn.execute("""
                UPDATE batch_processing_sessions 
                SET end_time = ?, status = ?, error_message = ?, updated_at = CURRENT_TIMESTAMP
                WHERE session_id = ?
            """, (datetime.now(), status, error_message, session_id))
    
    def log_batch_result(self, session_id: str, file_path: str, folder_name: str,
                        subfolder_name: str, processing_time: float,
                        plate_text: Optional[str] = None, confidence: Optional[float] = None,
                        image_path: Optional[str] = None, error_message: Optional[str] = None,
                        frame_count: Optional[int] = None, vehicle_detected: bool = False):
        """Log a batch processing result."""
        status = "SUCCESS" if error_message is None else "FAILED"
        
        with self.get_connection() as conn:
            conn.execute("""
                INSERT INTO batch_processing_results 
                (session_id, file_path, folder_name, subfolder_name, plate_text, 
                 confidence, processing_time, timestamp, image_path, error_message, 
                 status, frame_count, vehicle_detected)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                session_id, file_path, folder_name, subfolder_name, plate_text,
                confidence, processing_time, datetime.now(), image_path, error_message,
                status, frame_count, vehicle_detected
            ))
            
            # Update session counters
            if status == "SUCCESS":
                conn.execute("""
                    UPDATE batch_processing_sessions 
                    SET processed_files = processed_files + 1, success_files = success_files + 1,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE session_id = ?
                """, (session_id,))
            else:
                conn.execute("""
                    UPDATE batch_processing_sessions 
                    SET processed_files = processed_files + 1, error_files = error_files + 1,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE session_id = ?
                """, (session_id,))
    
    def log_performance_metric(self, session_id: str, metric_name: str, 
                             metric_value: float, metric_type: str = "counter"):
        """Log a performance metric."""
        with self.get_connection() as conn:
            conn.execute("""
                INSERT INTO batch_processing_metrics 
                (session_id, metric_name, metric_value, metric_type)
                VALUES (?, ?, ?, ?)
            """, (session_id, metric_name, metric_value, metric_type))
    
    def log_gpu_utilization(self, session_id: str, gpu_id: int, utilization: float,
                          memory_used: float, memory_total: float, temperature: Optional[float] = None):
        """Log GPU utilization data."""
        with self.get_connection() as conn:
            conn.execute("""
                INSERT INTO gpu_utilization_log 
                (session_id, gpu_id, utilization_percent, memory_used_mb, memory_total_mb, temperature_c)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (session_id, gpu_id, utilization, memory_used, memory_total, temperature))
    
    def get_session_status(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get current status of a batch processing session."""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                SELECT * FROM batch_processing_sessions WHERE session_id = ?
            """, (session_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_active_sessions(self) -> List[Dict[str, Any]]:
        """Get all currently active batch processing sessions."""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                SELECT * FROM batch_processing_sessions 
                WHERE status = 'RUNNING' 
                ORDER BY start_time DESC
            """)
            return [dict(row) for row in cursor.fetchall()]
    
    def get_session_results(self, session_id: str, limit: int = 100, 
                          offset: int = 0) -> List[Dict[str, Any]]:
        """Get results for a specific session."""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                SELECT * FROM batch_processing_results 
                WHERE session_id = ? 
                ORDER BY timestamp DESC 
                LIMIT ? OFFSET ?
            """, (session_id, limit, offset))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_processing_statistics(self, start_date: datetime, 
                                end_date: datetime) -> Dict[str, Any]:
        """Get processing statistics for a date range."""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                SELECT 
                    COUNT(*) as total_sessions,
                    SUM(processed_files) as total_files_processed,
                    SUM(success_files) as total_success_files,
                    SUM(error_files) as total_error_files,
                    AVG(
                        CASE WHEN end_time IS NOT NULL AND start_time IS NOT NULL 
                        THEN (julianday(end_time) - julianday(start_time)) * 24 * 60
                        ELSE NULL END
                    ) as avg_session_duration_minutes
                FROM batch_processing_sessions 
                WHERE start_time BETWEEN ? AND ?
            """, (start_date, end_date))
            
            stats = dict(cursor.fetchone())
            
            # Get average processing time per file
            cursor = conn.execute("""
                SELECT AVG(processing_time) as avg_processing_time
                FROM batch_processing_results r
                JOIN batch_processing_sessions s ON r.session_id = s.session_id
                WHERE s.start_time BETWEEN ? AND ? AND r.status = 'SUCCESS'
            """, (start_date, end_date))
            
            avg_time_row = cursor.fetchone()
            stats['avg_processing_time'] = avg_time_row['avg_processing_time'] if avg_time_row else 0
            
            return stats
    
    def get_directory_performance(self, start_date: datetime, 
                                end_date: datetime) -> List[Dict[str, Any]]:
        """Get performance statistics by directory."""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                SELECT 
                    folder_name,
                    COUNT(*) as total_files,
                    AVG(processing_time) as avg_processing_time,
                    SUM(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END) as success_count,
                    SUM(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END) as error_count
                FROM batch_processing_results r
                JOIN batch_processing_sessions s ON r.session_id = s.session_id
                WHERE s.start_time BETWEEN ? AND ?
                GROUP BY folder_name
                ORDER BY total_files DESC
            """, (start_date, end_date))
            return [dict(row) for row in cursor.fetchall()]
    
    def cleanup_old_data(self, days_to_keep: int = 30):
        """Clean up old batch processing data."""
        cutoff_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        cutoff_date = cutoff_date.replace(day=cutoff_date.day - days_to_keep)
        
        with self.get_connection() as conn:
            # Clean up old results
            conn.execute("""
                DELETE FROM batch_processing_results 
                WHERE session_id IN (
                    SELECT session_id FROM batch_processing_sessions 
                    WHERE start_time < ?
                )
            """, (cutoff_date,))
            
            # Clean up old metrics
            conn.execute("""
                DELETE FROM batch_processing_metrics 
                WHERE session_id IN (
                    SELECT session_id FROM batch_processing_sessions 
                    WHERE start_time < ?
                )
            """, (cutoff_date,))
            
            # Clean up old GPU logs
            conn.execute("""
                DELETE FROM gpu_utilization_log 
                WHERE session_id IN (
                    SELECT session_id FROM batch_processing_sessions 
                    WHERE start_time < ?
                )
            """, (cutoff_date,))
            
            # Clean up old sessions
            conn.execute("""
                DELETE FROM batch_processing_sessions WHERE start_time < ?
            """, (cutoff_date,))