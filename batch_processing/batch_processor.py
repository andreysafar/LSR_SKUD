import os
import subprocess
import argparse
import tempfile
import sys
import signal
import atexit
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
import multiprocessing
import time
import threading
import queue
import json
import logging
from multiprocessing import Manager
import torch

# Import the refactored worker class
from .neural_worker import ModernAnalysisWorker, init_modern_neural_worker, get_worker_instance
from config import Config, get_config
from config.anpr_config import ANPRBatchConfig
from db import get_db, ANPRDatabaseIntegration, BatchProcessingResult

# Global variable to hold the worker instance for each process
worker = None
# Global executors for cleanup
ffmpeg_executor = None
ffmpeg_gpu_executor = None
neural_executor = None

# Globals for GPU worker assignment
assigned_gpu_id = 0
gpu_counter = None
lock = None


class ModernBatchProcessor:
    """Modern batch processor with database integration and monitoring."""
    
    def __init__(self, config: Optional[Config] = None):
        self.config = config or get_config()
        self.logger = self._setup_logger()
        self.db = get_db(self.config.db_path)
        self.db_integration = ANPRDatabaseIntegration(self.db)
        self.session_id = None
        
        # Performance monitoring
        self.start_time = None
        self.processed_files = 0
        self.success_files = 0
        self.error_files = 0
        
        self.logger.info("Modern batch processor initialized")
    
    def _setup_logger(self) -> logging.Logger:
        """Setup logger for the batch processor."""
        logger = logging.getLogger(self.__class__.__name__)
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        return logger
    
    def process_videos_dual_pipeline(self, session_config: ANPRBatchConfig):
        """Enhanced dual pipeline processing with database integration."""
        # Create database session
        self.session_id = self.db_integration.create_batch_session(session_config)
        self.start_time = datetime.datetime.now()
        
        try:
            # Enhanced dual pipeline with database integration
            results = self._run_dual_pipeline(session_config)
            self._finalize_session(results, "COMPLETED")
            return results
        except Exception as e:
            error_msg = f"Batch processing failed: {str(e)}"
            self.logger.error(error_msg)
            self.db_integration.mark_session_failed(self.session_id, error_msg)
            raise
    
    def _run_dual_pipeline(self, config: ANPRBatchConfig) -> List[BatchProcessingResult]:
        """Run the dual pipeline with enhanced monitoring."""
        self.logger.info("Starting enhanced dual pipeline processing...")
        
        # Count total files first
        total_files = self._count_files(config)
        self.db_integration.update_session_totals(self.session_id, total_files)
        
        results = []
        
        # Preserve original dual-pipeline architecture but add database logging
        mp_context = multiprocessing.get_context("spawn")
        
        with ProcessPoolExecutor(max_workers=config.cpu_workers, mp_context=mp_context) as ffmpeg_executor, \
             ProcessPoolExecutor(max_workers=config.gpu_workers, 
                               initializer=init_modern_neural_worker, 
                               initargs=(self.config,), mp_context=mp_context) as neural_executor:
            
            # Enhanced processing loop with database integration
            ffmpeg_futures = []
            neural_futures = []
            
            # Process files using the original logic but with enhanced monitoring
            for task_info in self._generate_tasks(config):
                # Submit to FFmpeg pipeline
                if config.ffmpeg_gpu_workers > 0:
                    future = ffmpeg_executor.submit(ffmpeg_gpu_worker_task, task_info)
                else:
                    future = ffmpeg_executor.submit(ffmpeg_worker_task, task_info)
                ffmpeg_futures.append(future)
                
                # Process completed FFmpeg tasks
                self._process_completed_ffmpeg_tasks(
                    ffmpeg_futures, neural_executor, neural_futures
                )
                
                # Process completed neural tasks
                completed_results = self._process_completed_neural_tasks(neural_futures)
                results.extend(completed_results)
            
            # Process remaining tasks
            self._process_remaining_tasks(ffmpeg_futures, neural_executor, neural_futures)
            final_results = self._process_completed_neural_tasks(neural_futures)
            results.extend(final_results)
        
        return results
    
    def _count_files(self, config: ANPRBatchConfig) -> int:
        """Count total files to be processed."""
        total = 0
        for input_dir in config.input_directories:
            if os.path.exists(input_dir):
                for root, dirs, files in os.walk(input_dir):
                    dirs[:] = [d for d in dirs if not d.startswith('.')]
                    for file in files:
                        if file.endswith(config.video_extension):
                            full_path = os.path.join(root, file)
                            try:
                                if os.path.getsize(full_path) >= 1024 * 1024:  # 1MB minimum
                                    total += 1
                            except OSError:
                                pass
        return total
    
    def _generate_tasks(self, config: ANPRBatchConfig):
        """Generate processing tasks from configuration."""
        # This uses the same logic as the original process_videos_dual_pipeline
        # but yields tasks instead of processing them directly
        
        # Folder format cache
        folder_format_cache = {}
        
        for input_dir in config.input_directories:
            if not os.path.exists(input_dir):
                self.logger.warning(f"Directory not found: {input_dir}")
                continue
                
            folder = os.path.basename(input_dir)
            
            # Detect format for first file (caching optimization)
            if folder not in folder_format_cache:
                format_args = []
                for root, dirs, files in os.walk(input_dir):
                    dirs[:] = [d for d in dirs if not d.startswith('.')]
                    for file in files:
                        if file.endswith(config.video_extension):
                            full_path = os.path.join(root, file)
                            try:
                                if os.path.getsize(full_path) >= 1024 * 1024:
                                    format_args = detect_video_format(full_path)
                                    break
                            except OSError:
                                pass
                    if format_args:
                        break
                folder_format_cache[folder] = format_args
            
            # Generate tasks for this directory
            for task in self._generate_directory_tasks(input_dir, folder_format_cache[folder]):
                yield task
    
    def _generate_directory_tasks(self, input_dir: str, format_args: list):
        """Generate tasks for a specific directory."""
        file_list = []
        
        for root, dirs, files in os.walk(input_dir):
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            for file in files:
                if file.endswith(self.config.anpr_batch.video_extension):
                    full_path = os.path.join(root, file)
                    try:
                        if os.path.getsize(full_path) >= 1024 * 1024:  # 1MB
                            mtime = os.path.getmtime(full_path)
                            file_list.append((full_path, mtime))
                    except OSError:
                        pass
        
        # Sort by modification time (newest first)
        file_list.sort(key=lambda x: x[1], reverse=True)
        
        # Generate tasks
        for full_path, _ in file_list:
            relative_path = os.path.relpath(os.path.dirname(full_path), input_dir)
            path_parts = relative_path.split(os.sep)
            
            if path_parts and path_parts[0] != '.':
                folder = os.path.basename(input_dir)
                subfolder = path_parts[0]
            else:
                folder = os.path.basename(input_dir)
                subfolder = 'root'
            
            yield (full_path, folder, subfolder, format_args)
    
    def _process_completed_ffmpeg_tasks(self, ffmpeg_futures, neural_executor, neural_futures):
        """Process completed FFmpeg tasks and submit to neural pipeline."""
        completed = [f for f in ffmpeg_futures if f.done()]
        
        for future in completed:
            try:
                converted_info = future.result()
                if converted_info['success']:
                    neural_future = neural_executor.submit(modern_neural_worker_task, converted_info)
                    neural_futures.append(neural_future)
                else:
                    # Log failed conversion
                    self._log_processing_result(
                        BatchProcessingResult(
                            file_path=converted_info['original_video_path'],
                            folder_name="unknown",
                            subfolder_name="unknown", 
                            processing_time=0.0,
                            success=False,
                            error_message=converted_info.get('error', 'FFmpeg conversion failed')
                        )
                    )
                ffmpeg_futures.remove(future)
            except Exception as e:
                self.logger.error(f"Error processing FFmpeg result: {e}")
                ffmpeg_futures.remove(future)
    
    def _process_completed_neural_tasks(self, neural_futures) -> List[BatchProcessingResult]:
        """Process completed neural tasks and return results."""
        completed = [f for f in neural_futures if f.done()]
        results = []
        
        for future in completed:
            try:
                result = future.result()
                self._log_processing_result(result)
                results.append(result)
                neural_futures.remove(future)
            except Exception as e:
                self.logger.error(f"Error processing neural result: {e}")
                neural_futures.remove(future)
        
        return results
    
    def _process_remaining_tasks(self, ffmpeg_futures, neural_executor, neural_futures):
        """Process all remaining FFmpeg tasks."""
        for future in as_completed(ffmpeg_futures):
            try:
                converted_info = future.result()
                if converted_info['success']:
                    neural_future = neural_executor.submit(modern_neural_worker_task, converted_info)
                    neural_futures.append(neural_future)
            except Exception as e:
                self.logger.error(f"Error processing remaining FFmpeg result: {e}")
    
    def _log_processing_result(self, result: BatchProcessingResult):
        """Log processing result to database."""
        try:
            self.db_integration.log_batch_result(self.session_id, result)
            
            if result.success:
                self.success_files += 1
                status = "✓"
            else:
                self.error_files += 1 
                status = "✗"
            
            self.processed_files += 1
            
            # Log progress
            progress = f"[{self.processed_files}/?]"
            video_name = os.path.basename(result.file_path)
            self.logger.info(f"{status} {progress} {video_name}")
            
        except Exception as e:
            self.logger.error(f"Failed to log processing result: {e}")
    
    def _finalize_session(self, results: List[BatchProcessingResult], status: str):
        """Finalize the processing session."""
        try:
            self.db_integration.mark_session_completed(self.session_id, status)
            
            elapsed_time = (datetime.datetime.now() - self.start_time).total_seconds()
            
            self.logger.info(f"Session completed: {self.session_id}")
            self.logger.info(f"Total files processed: {self.processed_files}")
            self.logger.info(f"Successful: {self.success_files}")
            self.logger.info(f"Failed: {self.error_files}")
            self.logger.info(f"Total time: {elapsed_time:.2f}s")
            
        except Exception as e:
            self.logger.error(f"Failed to finalize session: {e}")


def modern_neural_worker_task(converted_info: Dict[str, Any]) -> BatchProcessingResult:
    """Modern neural worker task that returns BatchProcessingResult."""
    try:
        worker = get_worker_instance()
        result = worker.process_video(
            converted_info['converted_video_path'],
            converted_info['folder'],
            converted_info['subfolder'],
            converted_info['original_video_path']
        )
        return result
    except Exception as e:
        return BatchProcessingResult(
            file_path=converted_info.get('original_video_path', 'unknown'),
            folder_name=converted_info.get('folder', 'unknown'),
            subfolder_name=converted_info.get('subfolder', 'unknown'),
            processing_time=0.0,
            success=False,
            error_message=str(e)
        )
    finally:
        # Clean up temporary file
        temp_path = converted_info.get('converted_video_path')
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


# PID file path
PID_FILE = "process_videos.pid"
LOG_FILE = "process_videos.log"

def setup_logging():
    """Настройка логирования в файл"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(LOG_FILE),
            logging.StreamHandler() if not is_daemon_mode() else logging.NullHandler()
        ]
    )
    return logging.getLogger(__name__)

def is_daemon_mode():
    """Проверка, запущен ли в daemon режиме"""
    return hasattr(sys.stdin, 'isatty') and not sys.stdin.isatty()

def write_pid_file():
    """Записать PID в файл"""
    with open(PID_FILE, 'w') as f:
        f.write(str(os.getpid()))

def read_pid_file():
    """Прочитать PID из файла"""
    try:
        with open(PID_FILE, 'r') as f:
            return int(f.read().strip())
    except (FileNotFoundError, ValueError):
        return None

def remove_pid_file():
    """Удалить PID файл"""
    try:
        os.remove(PID_FILE)
    except FileNotFoundError:
        pass

def is_process_running(pid):
    """Проверить, запущен ли процесс с данным PID"""
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False

def stop_daemon():
    """Остановить daemon процесс"""
    pid = read_pid_file()
    if not pid:
        print("PID файл не найден. Процесс не запущен или уже остановлен.")
        return False
    
    if not is_process_running(pid):
        print(f"Процесс с PID {pid} не найден. Удаляю PID файл.")
        remove_pid_file()
        return False
    
    try:
        # Отправляем SIGTERM для graceful shutdown
        os.kill(pid, signal.SIGTERM)
        print(f"Отправлен сигнал остановки процессу {pid}")
        
        # Ждём до 30 секунд завершения
        for i in range(30):
            if not is_process_running(pid):
                print("Процесс успешно остановлен.")
                # Удаляем PID файл только после подтверждения остановки
                remove_pid_file()
                return True
            time.sleep(1)
        
        # Если не остановился - принудительно
        print("Процесс не остановился добровольно. Принудительная остановка...")
        try:
            os.kill(pid, signal.SIGKILL)
            time.sleep(2)
            # Проверяем еще раз после SIGKILL
            if not is_process_running(pid):
                print("Процесс принудительно остановлен.")
                remove_pid_file()
                return True
            else:
                print("Не удалось остановить процесс даже принудительно.")
                return False
        except OSError:
            # Процесс уже не существует
            print("Процесс принудительно остановлен.")
            remove_pid_file()
            return True
        
    except OSError as e:
        print(f"Ошибка при остановке процесса: {e}")
        # Только если процесс не найден, удаляем PID файл
        if e.errno == 3:  # No such process
            remove_pid_file()
        return False

def get_status():
    """Получить статус daemon процесса"""
    pid = read_pid_file()
    if not pid:
        return "stopped", None
    
    if is_process_running(pid):
        return "running", pid
    else:
        remove_pid_file()
        return "stopped", None

def daemonize():
    """Превратить процесс в daemon"""
    # Сохраняем текущую рабочую директорию
    current_dir = os.getcwd()
    
    try:
        # Первый fork
        pid = os.fork()
        if pid > 0:
            sys.exit(0)  # Родительский процесс завершается
    except OSError as e:
        print(f"Ошибка первого fork: {e}")
        sys.exit(1)
    
    # Отсоединяемся от управляющего терминала
    os.setsid()
    os.umask(0)
    
    try:
        # Второй fork
        pid = os.fork()
        if pid > 0:
            sys.exit(0)  # Первый дочерний процесс завершается
    except OSError as e:
        print(f"Ошибка второго fork: {e}")
        sys.exit(1)
    
    # Возвращаемся в исходную директорию
    os.chdir(current_dir)
    
    # Перенаправляем стандартные потоки
    sys.stdout.flush()
    sys.stderr.flush()
    
    si = open(os.devnull, 'r')
    so = open(LOG_FILE, 'a+')
    se = open(LOG_FILE, 'a+')
    
    os.dup2(si.fileno(), sys.stdin.fileno())
    os.dup2(so.fileno(), sys.stdout.fileno())
    os.dup2(se.fileno(), sys.stderr.fileno())

def cleanup_processes():
    """Cleanup function to ensure all worker processes are terminated"""
    global ffmpeg_executor, ffmpeg_gpu_executor, neural_executor
    print("Cleaning up worker processes...")
    if ffmpeg_executor:
        ffmpeg_executor.shutdown(wait=False, cancel_futures=True)
    if ffmpeg_gpu_executor:
        ffmpeg_gpu_executor.shutdown(wait=False, cancel_futures=True)
    if neural_executor:
        neural_executor.shutdown(wait=False, cancel_futures=True)
    # Force kill any remaining processes
    for proc in multiprocessing.active_children():
        proc.terminate()
        proc.join(timeout=1)
        if proc.is_alive():
            proc.kill()
    # НЕ удаляем PID файл здесь! Он должен удаляться только после подтверждения остановки в stop_daemon()

def signal_handler(signum, frame):
    """Handle Ctrl+C and other termination signals"""
    print(f"\nReceived signal {signum}, shutting down...")
    cleanup_processes()
    sys.exit(0)

# Register cleanup functions
atexit.register(cleanup_processes)
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def init_neural_worker():
    """
    Initializer for each neural worker process. Creates a single AnalysisWorker instance.
    """
    global worker
    pid = os.getpid()
    print(f"[GPU-PID:{pid}] Initializing neural worker...")
    t0 = time.time()
    worker = AnalysisWorker()
    t1 = time.time()
    print(f"[GPU-PID:{pid}] Neural worker initialized in {t1-t0:.1f} sec")
    if t1-t0 > 30:
        print(f"[GPU-PID:{pid}] WARNING: Neural worker initialization took unusually long!")

def get_gpu_count():
    """Safely get the number of available CUDA devices."""
    try:
        if not torch.cuda.is_available():
            return 0
        return torch.cuda.device_count()
    except Exception as e:
        print(f"Could not query GPU count: {e}")
        return 0

def init_ffmpeg_gpu_worker(l, gc):
    """Initializer for each FFmpeg GPU worker process to assign a GPU."""
    global assigned_gpu_id, gpu_counter, lock
    lock = l
    gpu_counter = gc
    
    if lock is None or gpu_counter is None:
        assigned_gpu_id = -1
        print(f"[FFMPEG-GPU-PID:{os.getpid()}] ERROR: Worker initializer not ready.")
        return

    with lock:
        num_gpus = get_gpu_count()
        if num_gpus == 0:
            assigned_gpu_id = -1 # Should not happen if this initializer is called
            return

        # Assign GPU in a round-robin fashion
        assigned_gpu_id = gpu_counter.value
        gpu_counter.value = (gpu_counter.value + 1) % num_gpus
        
        pid = os.getpid()
        print(f"[FFMPEG-GPU-PID:{pid}] assigned to GPU {assigned_gpu_id}")


def ffmpeg_gpu_worker_task(task_info):
    """
    FFmpeg worker task for GPU - uses NVDEC/NVENC for hardware acceleration.
    """
    global assigned_gpu_id
    video_path, folder, subfolder, format_args = task_info
    pid = os.getpid()

    if assigned_gpu_id == -1:
        print(f"[FFMPEG-GPU-PID:{pid}] No GPU available. Skipping task.")
        return {'success': False, 'original_video_path': video_path, 'error': 'No GPU available'}

    print(f"[FFMPEG-GPU-PID:{pid}] Start FFmpeg on GPU {assigned_gpu_id}: {os.path.basename(video_path)}")
    t_start = time.time()
    temp_mp4_path = None
    
    try:
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as temp_file:
            temp_mp4_path = temp_file.name
        
        # The hardware decoder is too strict for the proprietary container format.
        # We will use software decoding (which is more robust) by passing the format_args,
        # and hardware encoding via h264_nvenc.
        # The -hwaccel context is still needed to select the correct GPU for the encoder.
        ffmpeg_cmd = ["ffmpeg", "-y", "-hwaccel", "cuda", "-hwaccel_device", str(assigned_gpu_id)]
        
        # Add format hint for the software decoder
        ffmpeg_cmd.extend(format_args)
        
        ffmpeg_cmd.extend([
            "-i", video_path,
            "-c:v", "h264_nvenc",
            "-preset", "default",
            "-vf", "fps=5",
            "-threads", "4",
            "-hide_banner", "-loglevel", "error",
            temp_mp4_path
        ])
        
        result = subprocess.run(ffmpeg_cmd, check=True, capture_output=True, text=True)
        t_end = time.time()
        print(f"[FFMPEG-GPU-PID:{pid}] FFmpeg on GPU finished {os.path.basename(video_path)} in {t_end-t_start:.1f} sec")
        
        return {
            'success': True,
            'original_video_path': video_path,
            'converted_video_path': temp_mp4_path,
            'folder': folder,
            'subfolder': subfolder,
            'conversion_time': t_end - t_start
        }

    except subprocess.CalledProcessError as e:
        error_message = e.stderr or e.stdout
        print(f"[FFMPEG-GPU-PID:{pid}] FFmpeg GPU error for {os.path.basename(video_path)}: {error_message}")
        if temp_mp4_path and os.path.exists(temp_mp4_path):
            os.remove(temp_mp4_path)
        return {
            'success': False,
            'original_video_path': video_path,
            'error': error_message
        }
    except Exception as e:
        print(f"[FFMPEG-GPU-PID:{pid}] Unexpected GPU error for {os.path.basename(video_path)}: {e}")
        if temp_mp4_path and os.path.exists(temp_mp4_path):
            os.remove(temp_mp4_path)
        return {
            'success': False,
            'original_video_path': video_path,
            'error': str(e)
        }

def detect_video_format(video_path):
    """
    Use mediainfo to detect the video format and return appropriate ffmpeg input arguments
    """
    try:
        result = subprocess.run(['mediainfo', '--Output=Video;%Format%', video_path], 
                              capture_output=True, text=True, check=True)
        format_info = result.stdout.strip().lower()
        
        if 'hevc' in format_info or 'h.265' in format_info:
            return ['-f', 'hevc']
        elif 'avc' in format_info or 'h.264' in format_info:
            return ['-f', 'h264']
        else:
            # Default fallback
            return []
    except Exception as e:
        print(f"Warning: Could not detect video format for {video_path}: {e}")
        return []

def ffmpeg_worker_task(task_info):
    """
    FFmpeg worker task - только конвертация видео (CPU)
    """
    video_path, folder, subfolder, format_args = task_info
    pid = os.getpid()
    
    print(f"[CPU-PID:{pid}] Start FFmpeg: {os.path.basename(video_path)}")
    t_start = time.time()
    temp_mp4_path = None
    
    try:
        # ffmpeg conversion
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as temp_file:
            temp_mp4_path = temp_file.name
            
        ffmpeg_command = ["ffmpeg", "-y"] + format_args + [
            "-i", video_path,
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "28",
            "-vf", "fps=5",
            "-threads", "4",
            "-hide_banner", "-loglevel", "error",
            temp_mp4_path
        ]
        
        subprocess.run(ffmpeg_command, check=True, capture_output=True, text=True)
        t_end = time.time()
        print(f"[CPU-PID:{pid}] FFmpeg finished {os.path.basename(video_path)} in {t_end-t_start:.1f} sec")
        
        # Возвращаем информацию для neural worker
        return {
            'success': True,
            'original_video_path': video_path,
            'converted_video_path': temp_mp4_path,
            'folder': folder,
            'subfolder': subfolder,
            'conversion_time': t_end - t_start
        }

    except subprocess.CalledProcessError as e:
        print(f"[CPU-PID:{pid}] FFmpeg error for {os.path.basename(video_path)}: {e}")
        if temp_mp4_path and os.path.exists(temp_mp4_path):
            os.remove(temp_mp4_path)
        return {
            'success': False,
            'original_video_path': video_path,
            'error': str(e)
        }
    except Exception as e:
        print(f"[CPU-PID:{pid}] Unexpected error for {os.path.basename(video_path)}: {e}")
        if temp_mp4_path and os.path.exists(temp_mp4_path):
            os.remove(temp_mp4_path)
        return {
            'success': False,
            'original_video_path': video_path,
            'error': str(e)
        }

def neural_worker_task(converted_info):
    """
    Neural worker task - только анализ видео (GPU)
    """
    global worker
    if worker is None:
        init_neural_worker()
    assert worker is not None, "Neural worker not initialized"
    
    pid = os.getpid()
    video_path = converted_info['converted_video_path']
    original_path = converted_info['original_video_path']
    folder = converted_info['folder']
    subfolder = converted_info['subfolder']
    
    print(f"[GPU-PID:{pid}] Start analysis: {os.path.basename(original_path)}")
    t_start = time.time()
    
    try:
        # Analysis
        success = worker.process_video(video_path, folder, subfolder, original_video_path=original_path)
        t_end = time.time()
        print(f"[GPU-PID:{pid}] Analysis finished {os.path.basename(original_path)} in {t_end-t_start:.1f} sec")
        if t_end-t_start > 15:
            print(f"[GPU-PID:{pid}] WARNING: Analysis took unusually long!")
        
        return original_path, success
        
    except Exception as e:
        print(f"[GPU-PID:{pid}] Analysis error for {os.path.basename(original_path)}: {e}")
        return original_path, False
    finally:
        # Удаляем временный файл
        if os.path.exists(video_path):
            os.remove(video_path)

def process_videos_dual_pipeline(input_dirs, ext, cpu_workers, gpu_workers, ffmpeg_gpu_workers, start_time=None, end_time=None):
    """Enhanced dual pipeline processing with modern architecture integration."""
    try:
        # Create modern batch configuration
        batch_config = ANPRBatchConfig(
            input_directories=input_dirs,
            video_extension=ext,
            cpu_workers=cpu_workers,
            gpu_workers=gpu_workers,
            ffmpeg_gpu_workers=ffmpeg_gpu_workers
        )
        
        # Use modern batch processor
        processor = ModernBatchProcessor()
        results = processor.process_videos_dual_pipeline(batch_config)
        
        return len([r for r in results if r.success])
        
    except Exception as e:
        logger = setup_logging()
        logger.error(f"Modern batch processing failed, falling back to legacy: {e}")
        
        # Fallback to legacy implementation
        return _legacy_process_videos_dual_pipeline(
            input_dirs, ext, cpu_workers, gpu_workers, ffmpeg_gpu_workers, start_time, end_time
        )


def _legacy_process_videos_dual_pipeline(input_dirs, ext, cpu_workers, gpu_workers, ffmpeg_gpu_workers, start_time=None, end_time=None):
    """Legacy dual pipeline processing function (preserved for fallback)."""
    logger = setup_logging()
    global gpu_counter, lock

    if cpu_workers > 16:
        logger.warning(f"{cpu_workers} CPU workers is a lot. Usually 4-8 is optimal.")
    if gpu_workers > 8:
        logger.warning(f"{gpu_workers} GPU workers is a lot. For RTX A5000 usually 2-4 is optimal.")

    # Проверяем все входные папки
    valid_dirs = []
    for input_dir in input_dirs:
        if not os.path.isdir(input_dir):
            logger.error(f"Directory not found at {input_dir}")
        else:
            valid_dirs.append(input_dir)
    
    if not valid_dirs:
        logger.error("No valid input directories found")
        return

    logger.info(f"Starting dual-pipeline processing with {cpu_workers} CPU workers, {ffmpeg_gpu_workers} FFmpeg GPU workers and {gpu_workers} GPU workers...")
    logger.info(f"Processing directories: {', '.join(valid_dirs)}")
    
    # Парсим start_time и end_time если заданы
    start_timestamp = None
    end_timestamp = None
    if start_time:
        try:
            import datetime
            start_timestamp = datetime.datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S").timestamp()
            logger.info(f"Processing files from {start_time} and older")
        except ValueError:
            logger.error(f"Invalid start-time format: {start_time}. Use YYYY-MM-DD HH:MM:SS")
            return
            
    if end_time:
        try:
            import datetime
            end_timestamp = datetime.datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S").timestamp()
            logger.info(f"Processing files until {end_time}")
        except ValueError:
            logger.error(f"Invalid end-time format: {end_time}. Use YYYY-MM-DD HH:MM:SS")
            return

    # Быстрая инициализация - проверяем только первый файл из каждой папки
    folder_format_cache = {}
    logger.info("Quick initialization - detecting video formats...")
    for input_dir in valid_dirs:
        folder = os.path.basename(input_dir)
        # Ищем первый подходящий файл для определения формата
        for root, dirs, files in os.walk(input_dir):
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            for file in files:
                if file.endswith(ext):
                    full_path = os.path.join(root, file)
                    try:
                        if os.path.getsize(full_path) >= 1024 * 1024:  # 1MB
                            format_args = detect_video_format(full_path)
                            folder_format_cache[folder] = format_args
                            logger.info(f"Detected format for {folder}: {format_args}")
                            break
                    except OSError:
                        pass
            if folder in folder_format_cache:
                break
        # Fallback если не нашли подходящий файл
        if folder not in folder_format_cache:
            folder_format_cache[folder] = []
            logger.warning(f"Could not detect format for {folder}, using default")
    
    # Создаем пулы процессов
    mp_context = multiprocessing.get_context("spawn")
    global ffmpeg_executor, ffmpeg_gpu_executor, neural_executor
    
    ffmpeg_executor = ProcessPoolExecutor(max_workers=cpu_workers, mp_context=mp_context)
    neural_executor = ProcessPoolExecutor(max_workers=gpu_workers, initializer=init_neural_worker, mp_context=mp_context)
    
    ffmpeg_gpu_executor = None
    if ffmpeg_gpu_workers > 0 and get_gpu_count() > 0:
        logger.info(f"Creating FFmpeg GPU worker pool with {ffmpeg_gpu_workers} workers.")
        manager = Manager()
        gpu_counter_manager = manager.Value('i', 0)
        lock_manager = manager.Lock()
        ffmpeg_gpu_executor = ProcessPoolExecutor(
            max_workers=ffmpeg_gpu_workers, 
            initializer=init_ffmpeg_gpu_worker, 
            initargs=(lock_manager, gpu_counter_manager),
            mp_context=mp_context
        )
    elif ffmpeg_gpu_workers > 0:
        logger.warning("FFmpeg GPU workers requested, but no GPUs were found. Using CPU workers only.")


    try:
        # Очередь для передачи данных между пайплайнами
        conversion_queue = queue.Queue(maxsize=gpu_workers * 2)  # Буфер для 2x GPU workers
        
        # Функция для обработки файлов из одной папки
        def process_directory_files(input_dir):
            """Генератор задач для одной папки - сортированный от новых к старым"""
            # Собираем все файлы с информацией для сортировки
            file_list = []
            for root, dirs, files in os.walk(input_dir):
                dirs[:] = [d for d in dirs if not d.startswith('.')]
                for file in files:
                    if file.endswith(ext):
                        full_path = os.path.join(root, file)
                        try:
                            # Фильтруем маленькие файлы и получаем время модификации
                            if os.path.getsize(full_path) >= 1024 * 1024:  # 1MB
                                mtime = os.path.getmtime(full_path)
                                # Фильтруем по времени если задан start_timestamp и/или end_timestamp
                                in_start_range = start_timestamp is None or mtime <= start_timestamp
                                in_end_range = end_timestamp is None or mtime >= end_timestamp
                                if in_start_range and in_end_range:
                                    file_list.append((full_path, mtime))
                        except OSError:
                            pass  # Пропускаем файлы с ошибками
            
            # Сортируем по времени модификации (новые сначала)
            file_list.sort(key=lambda x: x[1], reverse=True)
            
            # Генерируем задачи
            for full_path, _ in file_list:
                relative_path = os.path.relpath(os.path.dirname(full_path), input_dir)
                path_parts = relative_path.split(os.sep)
                
                # Определяем folder и subfolder правильно
                if path_parts and path_parts[0] != '.':
                    # Если есть подпапки относительно input_dir
                    folder = os.path.basename(input_dir)  # CAM_14 из /mnt/iss_media/CAM_14
                    subfolder = path_parts[0]  # 2025-06-16T07+0300
                else:
                    # Файлы лежат прямо в input_dir
                    folder = os.path.basename(input_dir)  # CAM_14
                    subfolder = 'root'
                
                # Используем предварительно определенный формат
                format_args = folder_format_cache.get(folder, [])
                
                yield (full_path, folder, subfolder, format_args)
        
        # Подсчитываем файлы для обработки
        ffmpeg_futures = []
        neural_futures = []
        processed_count = 0
        total_files = 0
        
        logger.info("Counting files for processing...")
        for input_dir in valid_dirs:
            # Создаем временный генератор для подсчета
            for _ in process_directory_files(input_dir):
                total_files += 1
        
        logger.info(f"Found {total_files} files to process across {len(valid_dirs)} directories")
        
        # Создаем итератор по всем файлам из всех папок
        def all_files_iterator():
            """Итератор по всем файлам из всех папок с чередованием"""
            import itertools
            # Создаем итераторы для каждой папки
            dir_iterators = [process_directory_files(input_dir) for input_dir in valid_dirs]
            # Чередуем файлы из разных папок для равномерной нагрузки
            for task_info in itertools.chain(*itertools.zip_longest(*dir_iterators)):
                if task_info is not None:  # zip_longest может дать None для коротких итераторов
                    yield task_info
        
        # Сканируем файлы и запускаем FFmpeg pipeline
        task_idx = 0
        for task_info in all_files_iterator():
            # Распределяем задачи между CPU и GPU FFmpeg воркерами
            if ffmpeg_gpu_executor is not None and (task_idx % 2 != 0):
                future = ffmpeg_gpu_executor.submit(ffmpeg_gpu_worker_task, task_info)
            else:
                future = ffmpeg_executor.submit(ffmpeg_worker_task, task_info)
            ffmpeg_futures.append(future)
            task_idx += 1
            
            # Управляем размером очереди FFmpeg
            # Общее количество FFmpeg воркеров
            total_ffmpeg_workers = cpu_workers
            if ffmpeg_gpu_executor:
                total_ffmpeg_workers += ffmpeg_gpu_workers

            while len(ffmpeg_futures) >= total_ffmpeg_workers * 2:
                # Проверяем завершенные FFmpeg задачи
                try:
                    # Ждем не более 2 минут, чтобы избежать вечной блокировки
                    for ffmpeg_future in as_completed(ffmpeg_futures, timeout=120.0):
                        try:
                            converted_info = ffmpeg_future.result()
                            if converted_info['success']:
                                # Добавляем в neural pipeline
                                neural_futures.append(neural_executor.submit(neural_worker_task, converted_info))
                            else:
                                error_msg = converted_info.get('error', 'Unknown FFmpeg error').strip().replace('\n', ' ').replace('\r', '')
                                logger.info(f"✗ FFmpeg failed: {os.path.basename(converted_info.get('original_video_path', ''))}. Reason: {error_msg}")
                                processed_count += 1
                        except Exception as e:
                            logger.error(f"Error processing FFmpeg result: {e}")
                        finally:
                            # Удаляем завершенную задачу и выходим для проверки других очередей
                            ffmpeg_futures.remove(ffmpeg_future)
                            break
                except TimeoutError:
                    logger.warning("Timeout (120s) waiting for FFmpeg task. Checking neural tasks...")
                
                # Проверяем завершенные Neural задачи
                completed_neural = []
                for neural_future in neural_futures:
                    if neural_future.done():
                        completed_neural.append(neural_future)
                
                for neural_future in completed_neural:
                    try:
                        video_path, success = neural_future.result()
                        processed_count += 1
                        status = "✓" if success else "✗"
                        progress = f"[{processed_count}/{total_files}]"
                        video_name = os.path.basename(video_path)
                        logger.info(f"{status} {progress} {video_name}")
                        neural_futures.remove(neural_future)
                    except Exception as e:
                        logger.error(f"Error processing Neural result: {e}")
                        neural_futures.remove(neural_future)
        
        # Дожидаемся всех оставшихся FFmpeg задач
        for ffmpeg_future in as_completed(ffmpeg_futures):
            try:
                converted_info = ffmpeg_future.result()
                if converted_info['success']:
                    # Добавляем в neural pipeline
                    neural_futures.append(neural_executor.submit(neural_worker_task, converted_info))
                else:
                    logger.info(f"✗ FFmpeg failed: {os.path.basename(converted_info['original_video_path'])}")
                    processed_count += 1
            except Exception as e:
                logger.error(f"Error processing FFmpeg result: {e}")
        
        # Дожидаемся всех Neural задач
        for neural_future in as_completed(neural_futures):
            try:
                video_path, success = neural_future.result()
                processed_count += 1
                status = "✓" if success else "✗"
                progress = f"[{processed_count}/{total_files}]"
                video_name = os.path.basename(video_path)
                logger.info(f"{status} {progress} {video_name}")
            except Exception as e:
                logger.error(f"Error processing Neural result: {e}")
                
        logger.info(f"All videos processed. Total: {processed_count}/{total_files}")
        
    finally:
        cleanup_processes()

def main():
    parser = argparse.ArgumentParser(description="Batch process proprietary video files for ANPR with separate CPU/GPU pipelines.")
    parser.add_argument("command", nargs='?', choices=['start', 'stop', 'restart', 'status'], 
                       help="Команда управления daemon: start/stop/restart/status")
    parser.add_argument("input_dirs", nargs='*', help="The root directories to scan for video files (can specify multiple).")
    parser.add_argument("--ext", default=".issvd", help="The file extension of videos to process. Default is .issvd")
    parser.add_argument("--cpu-workers", type=int, default=4, help="Number of CPU workers for FFmpeg conversion. Default is 4.")
    parser.add_argument("--gpu-workers", type=int, default=4, help="Number of GPU workers for neural analysis. Default is 4.")
    parser.add_argument("--ffmpeg-gpu-workers", type=int, default=0, help="Number of GPU workers for FFmpeg conversion (requires NVENC-enabled GPU). Default is 0.")
    parser.add_argument("--start-time", type=str, help="Process files modified before this time (e.g., '2025-07-15 00:00:00'). Sets the NEWEST file to process.")
    parser.add_argument("--end-time", type=str, help="Process files modified after this time (e.g., '2025-07-12 00:00:00'). Sets the OLDEST file to process.")
    parser.add_argument("--daemon", action="store_true", help="Запустить в daemon режиме")
    args = parser.parse_args()

    # Обработка команд управления daemon
    if args.command == 'status':
        status, pid = get_status()
        if status == "running":
            print(f"Процесс запущен (PID: {pid})")
            print(f"Лог файл: {os.path.abspath(LOG_FILE)}")
        else:
            print("Процесс остановлен")
        return
        
    elif args.command == 'stop':
        if stop_daemon():
            print("Процесс остановлен успешно")
        return

    elif args.command == 'restart':
        print("Перезапуск процесса...")
        stop_daemon()
        time.sleep(2)
        # Продолжаем к запуску

    elif args.command == 'start' or args.command is None:
        # Проверяем, не запущен ли уже
        status, pid = get_status()
        if status == "running":
            print(f"Процесс уже запущен (PID: {pid})")
            return

    # Для команды start или если команда не указана, нужны input_dirs
    if not args.input_dirs:
        parser.error("input_dirs обязательны для запуска обработки. Можно указать несколько папок через пробел.")

    # Запуск в daemon режиме
    if args.daemon or args.command == 'start':
        print(f"Запуск в daemon режиме...")
        print(f"Обработка папок: {', '.join(args.input_dirs)}")
        print(f"PID файл: {os.path.abspath(PID_FILE)}")
        print(f"Лог файл: {os.path.abspath(LOG_FILE)}")
        
        daemonize()
        write_pid_file()
        
        # Настраиваем обработчики сигналов для daemon
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
        
        process_videos_dual_pipeline(args.input_dirs, args.ext, args.cpu_workers, args.gpu_workers, args.ffmpeg_gpu_workers, args.start_time, args.end_time)
    else:
        # Обычный режим
        print(f"Обработка папок: {', '.join(args.input_dirs)}")
        process_videos_dual_pipeline(args.input_dirs, args.ext, args.cpu_workers, args.gpu_workers, args.ffmpeg_gpu_workers, args.start_time, args.end_time)

if __name__ == "__main__":
    main() 