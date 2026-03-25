import uuid
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import asdict

from db.database import Database
from db.anpr_schema import ANPRDatabase
from config.anpr_config import ANPRBatchConfig, ANPRProcessingMetrics

logger = logging.getLogger(__name__)


class BatchProcessingResult:
    """Result from a single batch processing operation."""
    
    def __init__(self, file_path: str, folder_name: str, subfolder_name: str,
                 processing_time: float, success: bool = True, 
                 plate_text: Optional[str] = None, confidence: Optional[float] = None,
                 image_path: Optional[str] = None, error_message: Optional[str] = None,
                 frame_count: Optional[int] = None, vehicle_detected: bool = False):
        self.file_path = file_path
        self.folder_name = folder_name
        self.subfolder_name = subfolder_name
        self.processing_time = processing_time
        self.success = success
        self.plate_text = plate_text
        self.confidence = confidence
        self.image_path = image_path
        self.error_message = error_message
        self.frame_count = frame_count
        self.vehicle_detected = vehicle_detected
        self.timestamp = datetime.now()


class ANPRDatabaseIntegration:
    """Integration layer between ANPR batch processing and main database."""
    
    def __init__(self, db: Database):
        self.db = db
        self.anpr_db = ANPRDatabase(db.db_path)
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def create_batch_session(self, config: ANPRBatchConfig) -> str:
        """Create a new batch processing session."""
        session_id = str(uuid.uuid4())
        
        try:
            config_dict = asdict(config)
            self.anpr_db.create_batch_session(
                session_id, 
                config_dict, 
                config.input_directories
            )
            
            self.logger.info(f"Created batch processing session: {session_id}")
            return session_id
            
        except Exception as e:
            self.logger.error(f"Failed to create batch session: {e}")
            raise
    
    def update_session_totals(self, session_id: str, total_files: int):
        """Update total files count for a session."""
        try:
            self.anpr_db.update_session_totals(session_id, total_files)
            self.logger.info(f"Updated session {session_id} with {total_files} total files")
        except Exception as e:
            self.logger.error(f"Failed to update session totals: {e}")
            raise
    
    def log_batch_result(self, session_id: str, result: BatchProcessingResult):
        """Log a batch processing result."""
        try:
            self.anpr_db.log_batch_result(
                session_id=session_id,
                file_path=result.file_path,
                folder_name=result.folder_name,
                subfolder_name=result.subfolder_name,
                processing_time=result.processing_time,
                plate_text=result.plate_text,
                confidence=result.confidence,
                image_path=result.image_path,
                error_message=result.error_message,
                frame_count=result.frame_count,
                vehicle_detected=result.vehicle_detected
            )
            
            # If plate was detected successfully, also add to main recognition results
            if result.success and result.plate_text and result.image_path:
                self._add_to_main_results(result)
                
        except Exception as e:
            self.logger.error(f"Failed to log batch result: {e}")
            # Don't raise here to avoid breaking the processing pipeline
    
    def _add_to_main_results(self, result: BatchProcessingResult):
        """Add successful recognition to main results table."""
        try:
            with self.db.get_connection() as conn:
                conn.execute("""
                    INSERT INTO recognition_events 
                    (camera_id, timestamp, frame_path, plate_text, confidence, 
                     source_type, processing_time)
                    VALUES (?, ?, ?, ?, ?, 'batch_processing', ?)
                """, (
                    result.folder_name,  # Use folder name as camera_id for batch processing
                    result.timestamp,
                    result.image_path,
                    result.plate_text,
                    result.confidence,
                    result.processing_time
                ))
        except Exception as e:
            self.logger.warning(f"Failed to add result to main recognition table: {e}")
    
    def mark_session_completed(self, session_id: str, status: str = "COMPLETED", 
                             error_message: Optional[str] = None):
        """Mark a batch processing session as completed."""
        try:
            self.anpr_db.complete_session(session_id, status, error_message)
            self.logger.info(f"Marked session {session_id} as {status}")
        except Exception as e:
            self.logger.error(f"Failed to complete session: {e}")
            raise
    
    def mark_session_failed(self, session_id: str, error_message: str):
        """Mark a batch processing session as failed."""
        self.mark_session_completed(session_id, "FAILED", error_message)
    
    def get_session_status(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get current status of a batch processing session."""
        try:
            status = self.anpr_db.get_session_status(session_id)
            if status:
                # Calculate additional metrics
                total_files = status.get('total_files', 0)
                processed_files = status.get('processed_files', 0)
                
                if total_files > 0:
                    completion_rate = processed_files / total_files
                    status['completion_rate'] = completion_rate
                    
                    # Estimate ETA if session is still running
                    if status['status'] == 'RUNNING' and processed_files > 0:
                        start_time = datetime.fromisoformat(status['start_time'])
                        elapsed = (datetime.now() - start_time).total_seconds()
                        rate = processed_files / elapsed if elapsed > 0 else 0
                        remaining_files = total_files - processed_files
                        eta_seconds = remaining_files / rate if rate > 0 else 0
                        status['eta_seconds'] = eta_seconds
                        status['processing_rate'] = rate * 60  # files per minute
                
                return status
            return None
        except Exception as e:
            self.logger.error(f"Failed to get session status: {e}")
            return None
    
    def get_active_sessions(self) -> List[Dict[str, Any]]:
        """Get all currently active batch processing sessions."""
        try:
            sessions = self.anpr_db.get_active_sessions()
            # Enhance each session with additional metrics
            for session in sessions:
                session_id = session['session_id']
                enhanced_status = self.get_session_status(session_id)
                if enhanced_status:
                    session.update(enhanced_status)
            return sessions
        except Exception as e:
            self.logger.error(f"Failed to get active sessions: {e}")
            return []
    
    def get_session_results(self, session_id: str, limit: int = 100, 
                          offset: int = 0) -> List[Dict[str, Any]]:
        """Get results for a specific session."""
        try:
            return self.anpr_db.get_session_results(session_id, limit, offset)
        except Exception as e:
            self.logger.error(f"Failed to get session results: {e}")
            return []
    
    def get_batch_processing_metrics(self, start_date: datetime, 
                                   end_date: datetime) -> Dict[str, Any]:
        """Get processing metrics for a date range."""
        try:
            return self.anpr_db.get_processing_statistics(start_date, end_date)
        except Exception as e:
            self.logger.error(f"Failed to get processing metrics: {e}")
            return {}
    
    def get_processing_timeline(self, start_date: datetime, 
                              end_date: datetime) -> List[Dict[str, Any]]:
        """Get processing timeline data for analytics."""
        try:
            with self.db.get_connection() as conn:
                cursor = conn.execute("""
                    SELECT 
                        DATE(s.start_time) as date,
                        COUNT(DISTINCT s.session_id) as sessions_count,
                        SUM(s.processed_files) as files_processed,
                        SUM(s.success_files) as files_success,
                        SUM(s.error_files) as files_error,
                        AVG(
                            CASE WHEN s.end_time IS NOT NULL AND s.start_time IS NOT NULL 
                            THEN (julianday(s.end_time) - julianday(s.start_time)) * 24 * 60
                            ELSE NULL END
                        ) as avg_duration_minutes
                    FROM batch_processing_sessions s
                    WHERE s.start_time BETWEEN ? AND ?
                    GROUP BY DATE(s.start_time)
                    ORDER BY date DESC
                """, (start_date, end_date))
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            self.logger.error(f"Failed to get processing timeline: {e}")
            return []
    
    def get_performance_distribution(self, start_date: datetime, 
                                   end_date: datetime) -> List[Dict[str, Any]]:
        """Get processing time distribution for analytics."""
        try:
            with self.db.get_connection() as conn:
                cursor = conn.execute("""
                    SELECT 
                        r.processing_time,
                        r.folder_name,
                        r.status,
                        r.timestamp
                    FROM batch_processing_results r
                    JOIN batch_processing_sessions s ON r.session_id = s.session_id
                    WHERE s.start_time BETWEEN ? AND ? AND r.processing_time > 0
                    ORDER BY r.processing_time
                """, (start_date, end_date))
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            self.logger.error(f"Failed to get performance distribution: {e}")
            return []
    
    def get_directory_performance_stats(self, start_date: datetime, 
                                      end_date: datetime) -> List[Dict[str, Any]]:
        """Get performance statistics by directory."""
        try:
            stats = self.anpr_db.get_directory_performance(start_date, end_date)
            # Calculate success rate for each directory
            for stat in stats:
                total = stat['total_files']
                success = stat['success_count']
                stat['success_rate'] = success / total if total > 0 else 0
            return stats
        except Exception as e:
            self.logger.error(f"Failed to get directory performance stats: {e}")
            return []
    
    def log_performance_metric(self, session_id: str, metric_name: str, 
                             metric_value: float, metric_type: str = "gauge"):
        """Log a performance metric."""
        try:
            self.anpr_db.log_performance_metric(session_id, metric_name, metric_value, metric_type)
        except Exception as e:
            self.logger.warning(f"Failed to log performance metric: {e}")
    
    def log_gpu_utilization(self, session_id: str, gpu_metrics: List[Dict[str, Any]]):
        """Log GPU utilization metrics."""
        try:
            for gpu_metric in gpu_metrics:
                self.anpr_db.log_gpu_utilization(
                    session_id=session_id,
                    gpu_id=gpu_metric['gpu_id'],
                    utilization=gpu_metric['utilization_percent'],
                    memory_used=gpu_metric['memory_used_mb'],
                    memory_total=gpu_metric['memory_total_mb'],
                    temperature=gpu_metric.get('temperature_c')
                )
        except Exception as e:
            self.logger.warning(f"Failed to log GPU utilization: {e}")
    
    def cleanup_old_data(self, days_to_keep: int = 30):
        """Clean up old batch processing data."""
        try:
            self.anpr_db.cleanup_old_data(days_to_keep)
            self.logger.info(f"Cleaned up batch processing data older than {days_to_keep} days")
        except Exception as e:
            self.logger.error(f"Failed to clean up old data: {e}")
    
    def get_current_batch_session_status(self) -> Optional[Dict[str, Any]]:
        """Get status of the most recent active batch session."""
        active_sessions = self.get_active_sessions()
        if active_sessions:
            # Return the most recently started session
            return max(active_sessions, key=lambda x: x['start_time'])
        return None