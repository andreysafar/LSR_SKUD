"""Integration tests for ANPR functionality in LSR_SKUD."""

import pytest
import tempfile
import os
import sqlite3
import json
import time
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
from contextlib import contextmanager

# Import the modules to test
from config import Config
from config.anpr_config import ANPRBatchConfig, ANPRDaemonConfig
from db import Database, get_db, ANPRDatabaseIntegration, BatchProcessingResult
from batch_processing.neural_worker import ModernAnalysisWorker
from batch_processing.batch_processor import ModernBatchProcessor
from monitoring.batch_metrics import PerformanceMonitor
from analytics.batch_analytics import BatchAnalytics


class TestConfigIntegration:
    """Test configuration system integration."""
    
    def test_config_from_env(self):
        """Test configuration loading from environment variables."""
        with patch.dict(os.environ, {
            'ANPR_CPU_WORKERS': '8',
            'ANPR_GPU_WORKERS': '4', 
            'ANPR_CONFIDENCE_THRESHOLD': '0.3',
            'TORCHSCRIPT_ENABLED': 'true',
            'HALF_PRECISION': 'false'
        }):
            config = Config.from_env()
            
            assert config.anpr_batch is not None
            assert config.anpr_batch.cpu_workers == 8
            assert config.anpr_batch.gpu_workers == 4
            assert config.anpr_batch.confidence_threshold == 0.3
            assert config.torchscript_enabled is True
            assert config.half_precision is False
    
    def test_anpr_batch_config_validation(self):
        """Test ANPR batch configuration validation."""
        config = ANPRBatchConfig(
            cpu_workers=0,  # Invalid
            confidence_threshold=1.5,  # Invalid
            frame_skip=0  # Invalid
        )
        
        errors = config.validate()
        
        assert 'cpu_workers' in errors
        assert 'confidence_threshold' in errors
        assert 'frame_skip' in errors
    
    def test_anpr_batch_config_serialization(self):
        """Test configuration serialization/deserialization."""
        original_config = ANPRBatchConfig(
            input_directories=['/test/dir1', '/test/dir2'],
            cpu_workers=6,
            gpu_workers=2
        )
        
        # Test to_dict
        config_dict = original_config.to_dict()
        assert config_dict['cpu_workers'] == 6
        assert config_dict['input_directories'] == ['/test/dir1', '/test/dir2']
        
        # Test from_dict
        restored_config = ANPRBatchConfig.from_dict(config_dict)
        assert restored_config.cpu_workers == 6
        assert restored_config.input_directories == ['/test/dir1', '/test/dir2']


class TestDatabaseIntegration:
    """Test database integration functionality."""
    
    @pytest.fixture
    def temp_db(self):
        """Create temporary database for testing."""
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        temp_file.close()
        
        db = Database(temp_file.name)
        yield db
        
        # Cleanup
        os.unlink(temp_file.name)
    
    @pytest.fixture
    def db_integration(self, temp_db):
        """Create ANPRDatabaseIntegration instance."""
        return ANPRDatabaseIntegration(temp_db)
    
    def test_database_schema_creation(self, db_integration):
        """Test that ANPR database schema is created correctly."""
        # Tables should be created during initialization
        with db_integration.db.get_connection() as conn:
            # Check that tables exist
            cursor = conn.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name LIKE 'batch_%'
            """)
            tables = [row['name'] for row in cursor.fetchall()]
            
            expected_tables = [
                'batch_processing_sessions',
                'batch_processing_results', 
                'batch_processing_metrics',
                'gpu_utilization_log'
            ]
            
            for table in expected_tables:
                assert table in tables
    
    def test_batch_session_lifecycle(self, db_integration):
        """Test complete batch session lifecycle."""
        # Create session
        config = ANPRBatchConfig(
            input_directories=['/test/dir'],
            cpu_workers=4,
            gpu_workers=2
        )
        
        session_id = db_integration.create_batch_session(config)
        assert session_id is not None
        assert len(session_id) == 36  # UUID length
        
        # Update totals
        db_integration.update_session_totals(session_id, 100)
        
        # Log some results
        result1 = BatchProcessingResult(
            file_path='/test/file1.mp4',
            folder_name='CAM_14',
            subfolder_name='2025-01-01',
            processing_time=2.5,
            success=True,
            plate_text='ABC123',
            confidence=0.95
        )
        
        result2 = BatchProcessingResult(
            file_path='/test/file2.mp4',
            folder_name='CAM_14', 
            subfolder_name='2025-01-01',
            processing_time=3.1,
            success=False,
            error_message='Processing failed'
        )
        
        db_integration.log_batch_result(session_id, result1)
        db_integration.log_batch_result(session_id, result2)
        
        # Complete session
        db_integration.mark_session_completed(session_id, "COMPLETED")
        
        # Verify session data
        session_status = db_integration.get_session_status(session_id)
        assert session_status is not None
        assert session_status['status'] == 'COMPLETED'
        assert session_status['total_files'] == 100
        assert session_status['processed_files'] == 2
        assert session_status['success_files'] == 1
        assert session_status['error_files'] == 1
        
        # Verify results
        results = db_integration.get_session_results(session_id)
        assert len(results) == 2
        
        success_result = next(r for r in results if r['status'] == 'SUCCESS')
        assert success_result['plate_text'] == 'ABC123'
        assert success_result['confidence'] == 0.95
        
        error_result = next(r for r in results if r['status'] == 'FAILED')
        assert error_result['error_message'] == 'Processing failed'
    
    def test_processing_metrics_aggregation(self, db_integration):
        """Test processing metrics aggregation."""
        # Create test session with results
        config = ANPRBatchConfig(input_directories=['/test'])
        session_id = db_integration.create_batch_session(config)
        
        # Add multiple results with different timestamps
        for i in range(10):
            result = BatchProcessingResult(
                file_path=f'/test/file{i}.mp4',
                folder_name='TEST_CAM',
                subfolder_name='2025-01-01',
                processing_time=2.0 + i * 0.1,
                success=i < 8  # 8 successes, 2 failures
            )
            db_integration.log_batch_result(session_id, result)
        
        db_integration.mark_session_completed(session_id, "COMPLETED")
        
        # Test metrics aggregation
        start_date = datetime.now() - timedelta(days=1)
        end_date = datetime.now() + timedelta(days=1)
        
        metrics = db_integration.get_batch_processing_metrics(start_date, end_date)
        
        assert metrics['total_sessions'] == 1
        assert metrics['total_files_processed'] == 10
        assert metrics['total_success_files'] == 8
        assert metrics['total_error_files'] == 2
        assert metrics['avg_processing_time'] > 2.0


class TestBatchProcessorIntegration:
    """Test batch processor integration."""
    
    @pytest.fixture
    def temp_config(self):
        """Create temporary configuration for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config = Config(
                db_path=os.path.join(temp_dir, 'test.db'),
                models_dir=temp_dir,
                anpr_batch=ANPRBatchConfig(
                    input_directories=[temp_dir],
                    cpu_workers=1,
                    gpu_workers=1,
                    output_images_dir=temp_dir
                )
            )
            yield config
    
    @patch('batch_processing.neural_worker.torch')
    @patch('batch_processing.neural_worker.YOLO')
    @patch('batch_processing.neural_worker.easyocr')
    def test_modern_analysis_worker_initialization(self, mock_easyocr, mock_yolo, mock_torch, temp_config):
        """Test modern analysis worker initialization."""
        mock_torch.cuda.is_available.return_value = True
        mock_yolo.return_value = Mock()
        mock_easyocr.Reader.return_value = Mock()
        
        worker = ModernAnalysisWorker(temp_config)
        
        assert worker.config == temp_config
        assert worker.device == "cuda"
        assert worker.vehicle_model is not None
        assert worker.plate_model is not None
        assert worker.reader is not None
    
    def test_modern_batch_processor_initialization(self, temp_config):
        """Test modern batch processor initialization."""
        processor = ModernBatchProcessor(temp_config)
        
        assert processor.config == temp_config
        assert processor.db_integration is not None
        assert processor.session_id is None
        assert processor.processed_files == 0


class TestMonitoringIntegration:
    """Test monitoring system integration."""
    
    @pytest.fixture
    def temp_db_integration(self):
        """Create temporary database integration for testing."""
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        temp_file.close()
        
        db = Database(temp_file.name)
        db_integration = ANPRDatabaseIntegration(db)
        
        yield db_integration
        
        os.unlink(temp_file.name)
    
    def test_performance_monitor_lifecycle(self, temp_db_integration):
        """Test performance monitor complete lifecycle."""
        monitor = PerformanceMonitor(temp_db_integration, sample_interval=0.1)
        
        session_id = "test-session"
        
        # Test monitoring start
        monitor.start_monitoring(session_id)
        assert monitor.is_monitoring is True
        assert session_id in monitor.processing_metrics
        
        # Wait for a few samples
        time.sleep(0.3)
        
        # Test metrics update
        monitor.update_processing_metrics(session_id, 2.5, success=True, file_size=1024*1024)
        monitor.set_total_files(session_id, 100)
        
        # Get current metrics
        current_metrics = monitor.get_current_metrics(session_id)
        assert current_metrics is not None
        assert current_metrics['session_id'] == session_id
        assert 'system' in current_metrics
        assert 'processing' in current_metrics
        
        # Test callback system
        callback_data = []
        def test_callback(data):
            callback_data.append(data)
        
        monitor.add_callback(test_callback)
        time.sleep(0.2)  # Wait for callback to be triggered
        
        assert len(callback_data) > 0
        assert callback_data[-1]['session_id'] == session_id
        
        # Stop monitoring
        monitor.stop_monitoring(session_id)
        assert monitor.is_monitoring is False
    
    def test_metrics_history_collection(self, temp_db_integration):
        """Test metrics history collection."""
        monitor = PerformanceMonitor(temp_db_integration, sample_interval=0.1)
        
        session_id = "history-test"
        monitor.start_monitoring(session_id)
        
        # Let it collect some samples
        time.sleep(0.5)
        
        # Get metrics history
        history = monitor.get_metrics_history(session_id, minutes=1)
        
        assert len(history) > 0
        assert all('timestamp' in entry for entry in history)
        assert all('system' in entry for entry in history)
        
        monitor.stop_monitoring(session_id)


class TestAnalyticsIntegration:
    """Test analytics system integration."""
    
    @pytest.fixture
    def populated_db_integration(self):
        """Create database with sample data for analytics testing."""
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        temp_file.close()
        
        db = Database(temp_file.name)
        db_integration = ANPRDatabaseIntegration(db)
        
        # Create sample data
        config = ANPRBatchConfig(input_directories=['/test'])
        session_id = db_integration.create_batch_session(config)
        
        # Add sample results over multiple days
        base_time = datetime.now() - timedelta(days=5)
        
        for day in range(5):
            for i in range(20):  # 20 files per day
                result = BatchProcessingResult(
                    file_path=f'/test/day{day}/file{i}.mp4',
                    folder_name=f'CAM_{day % 3 + 1}',  # 3 different cameras
                    subfolder_name=f'2025-01-{day+1:02d}',
                    processing_time=1.5 + (i % 5) * 0.2,  # Varied processing times
                    success=(i % 10) < 9  # 90% success rate
                )
                
                # Manually set timestamp for test data
                with db_integration.db.get_connection() as conn:
                    # Insert with custom timestamp
                    timestamp = base_time + timedelta(days=day, hours=i)
                    conn.execute("""
                        INSERT INTO batch_processing_results 
                        (session_id, file_path, folder_name, subfolder_name, 
                         processing_time, timestamp, status)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        session_id, result.file_path, result.folder_name,
                        result.subfolder_name, result.processing_time,
                        timestamp, 'SUCCESS' if result.success else 'FAILED'
                    ))
        
        db_integration.mark_session_completed(session_id, "COMPLETED")
        
        yield db_integration
        
        os.unlink(temp_file.name)
    
    @patch('analytics.batch_analytics.get_db')
    def test_analytics_data_retrieval(self, mock_get_db, populated_db_integration):
        """Test analytics data retrieval functionality."""
        mock_get_db.return_value = populated_db_integration.db
        
        analytics = BatchAnalytics()
        
        # Test metrics retrieval
        start_date = datetime.now() - timedelta(days=7)
        end_date = datetime.now()
        
        metrics = analytics.db_integration.get_batch_processing_metrics(start_date, end_date)
        
        assert metrics['total_sessions'] >= 1
        assert metrics['total_files_processed'] == 100  # 5 days * 20 files
        assert metrics['total_success_files'] == 90     # 90% success rate
        assert metrics['total_error_files'] == 10       # 10% error rate
        
        # Test timeline data
        timeline_data = analytics.db_integration.get_processing_timeline(start_date, end_date)
        assert len(timeline_data) >= 1
        
        # Test directory performance
        dir_stats = analytics.db_integration.get_directory_performance_stats(start_date, end_date)
        assert len(dir_stats) == 3  # 3 different cameras
        
        # Verify camera distribution
        cam_names = [stat['folder_name'] for stat in dir_stats]
        assert 'CAM_1' in cam_names
        assert 'CAM_2' in cam_names
        assert 'CAM_3' in cam_names


class TestEndToEndIntegration:
    """End-to-end integration tests."""
    
    @pytest.mark.slow
    @patch('batch_processing.neural_worker.cv2')
    @patch('batch_processing.neural_worker.YOLO')
    @patch('batch_processing.neural_worker.easyocr')
    @patch('batch_processing.batch_processor.ProcessPoolExecutor')
    def test_complete_batch_processing_flow(self, mock_executor, mock_easyocr, mock_yolo, mock_cv2):
        """Test complete batch processing workflow (mocked)."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Setup mocks
            mock_yolo.return_value = Mock()
            mock_easyocr.Reader.return_value = Mock()
            mock_cv2.VideoCapture.return_value.isOpened.return_value = True
            mock_cv2.VideoCapture.return_value.read.side_effect = [(False, None)]  # No frames
            
            # Mock executor to run tasks synchronously
            def mock_executor_context(*args, **kwargs):
                return MockExecutor()
            
            mock_executor.return_value.__enter__ = lambda x: MockExecutor()
            mock_executor.return_value.__exit__ = lambda *args: None
            
            # Create test configuration
            config = Config(
                db_path=os.path.join(temp_dir, 'test.db'),
                models_dir=temp_dir,
                anpr_batch=ANPRBatchConfig(
                    input_directories=[temp_dir],
                    cpu_workers=1,
                    gpu_workers=1,
                    output_images_dir=temp_dir
                )
            )
            
            # Create test video file
            test_video = os.path.join(temp_dir, 'test.issvd')
            with open(test_video, 'wb') as f:
                f.write(b'fake_video_data' * 1024 * 1024)  # 1MB+ file
            
            # Run batch processing
            processor = ModernBatchProcessor(config)
            
            # This would normally process the video file
            # In the test, we're mainly verifying the setup works
            assert processor.config == config
            assert processor.db_integration is not None


class MockExecutor:
    """Mock executor for testing."""
    
    def submit(self, fn, *args, **kwargs):
        """Run task synchronously and return mock future."""
        mock_future = Mock()
        try:
            result = fn(*args, **kwargs)
            mock_future.result.return_value = result
            mock_future.done.return_value = True
        except Exception as e:
            mock_future.result.side_effect = e
            mock_future.done.return_value = True
        
        return mock_future
    
    def shutdown(self, *args, **kwargs):
        """Mock shutdown."""
        pass


if __name__ == '__main__':
    pytest.main([__file__, '-v'])