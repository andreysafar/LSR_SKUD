import argparse
import os
import csv
import datetime
import logging
import json
from typing import Optional, Dict, Any

# Disable ultralytics online checks to speed up import
os.environ['YOLO_VERBOSE'] = 'False'
os.environ['ULTRALYTICS_OFFLINE'] = 'True'

from ultralytics import YOLO
import cv2
import time
import easyocr
from concurrent.futures import ThreadPoolExecutor
import torch
import numpy as np

from config import Config
from config.anpr_config import ANPRProcessingMetrics
from db.anpr_integration import BatchProcessingResult


class ModernAnalysisWorker:
    def __init__(self, config: Optional[Config] = None):
        """
        Initializes the models and OCR reader with modern configuration.
        """
        self.config = config or Config.from_env()
        self.logger = self._setup_logger()
        
        self.logger.info("Initializing modern analysis worker...")
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.logger.info(f"Worker using device: {self.device}")

        # Ensure weight directory exists
        self.weight_directory = os.path.abspath(self.config.models_dir)
        os.makedirs(self.weight_directory, exist_ok=True)
        
        # Modern model loading with configuration
        self.vehicle_model = self._create_detector(
            "vehicle", self.config.anpr_batch.confidence_threshold
        )
        self.plate_model = self._create_detector(
            "plate", self.config.confidence_plate
        )
        self.reader = self._create_ocr_engine()
        
        self.vehicles = [2, 3, 5, 7]  # vehicle class IDs
        self.csv_file_path = self.config.anpr_batch.output_csv_path
        
        # Performance monitoring
        self.metrics = ANPRProcessingMetrics(
            session_id="worker",
            start_time=datetime.datetime.now()
        )
        
        self.logger.info("Modern analysis worker initialized successfully")

    def _setup_logger(self) -> logging.Logger:
        """Setup logger for the worker."""
        logger = logging.getLogger(f"{self.__class__.__name__}-{os.getpid()}")
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        return logger
    
    def _create_detector(self, detector_type: str, confidence: float):
        """Create and configure a detector with modern practices."""
        weights_path = self._get_weights_path(detector_type)
        
        if self.config.torchscript_enabled:
            torchscript_path = weights_path.replace('.pt', '.torchscript')
            if not os.path.exists(torchscript_path):
                self._export_torchscript(weights_path, torchscript_path)
            return YOLO(torchscript_path)
        
        return YOLO(weights_path)
    
    def _get_weights_path(self, detector_type: str) -> str:
        """Get weights path for a specific detector type."""
        if detector_type == "vehicle":
            return os.path.join(self.weight_directory, 'yolov8n.pt')
        elif detector_type == "plate":
            return os.path.join(self.weight_directory, 'license_plate_detector.pt')
        else:
            raise ValueError(f"Unknown detector type: {detector_type}")
    
    def _export_torchscript(self, pt_path: str, ts_path: str):
        """Export model to TorchScript format."""
        try:
            self.logger.info(f"Exporting {pt_path} to TorchScript...")
            YOLO(pt_path).export(
                format='torchscript', 
                half=self.config.half_precision, 
                device=self.device
            )
            self.logger.info(f"Successfully exported to {ts_path}")
        except Exception as e:
            self.logger.error(f"Failed to export {pt_path} to TorchScript: {e}")
            raise
    
    def _create_ocr_engine(self):
        """Create OCR engine with modern configuration."""
        self.logger.info("Loading OCR reader...")
        try:
            return easyocr.Reader(
                ['en'], 
                model_storage_directory=self.weight_directory, 
                gpu=self.config.gpu_enabled and torch.cuda.is_available(), 
                download_enabled=True
            )
        except Exception as e:
            self.logger.error(f"Error loading OCR reader: {e}")
            raise

    def _load_yolo_model(self, pt_path, torchscript_path):
        if not os.path.exists(torchscript_path):
            if not os.path.exists(pt_path):
                # If we don't have PT file either, we might need to download it or it's missing
                print(f"Error: Neither {pt_path} nor {torchscript_path} exists.")
                # We can try to load by name if it's a standard model
                model_name = os.path.basename(pt_path)
                print(f"Attempting to load standard model {model_name}...")
                pt_path = model_name
            
            print(f"Exporting model {pt_path} to {torchscript_path}...")
            try:
                YOLO(pt_path).export(format='torchscript', half=True, device=self.device)
            except Exception as e:
                print(f"Error exporting model {pt_path}: {e}")
                raise
        try:
            return YOLO(torchscript_path)
        except Exception as e:
            print(f"Error loading model {torchscript_path}: {e}")
            raise
    
    def _load_ocr_reader(self):
        print("Loading OCR reader...")
        try:
            return easyocr.Reader(['en'], model_storage_directory=self.weight_directory, gpu=torch.cuda.is_available(), download_enabled=True)
        except Exception as e:
            print(f"Error loading OCR reader: {e}")
            raise

    def save_plate_to_csv(self, plate_text, image_path, folder_name, subfolder_name, video_timestamp=None):
        file_exists = os.path.isfile(self.csv_file_path)
        try:
            with open(self.csv_file_path, mode='a', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                if not file_exists:
                    writer.writerow(['folder', 'subfolder', 'plate_text', 'timestamp', 'image_path'])
                # Используем время из видео или текущее время как fallback
                if video_timestamp:
                    timestamp_str = video_timestamp
                else:
                    timestamp_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                writer.writerow([folder_name, subfolder_name, plate_text, timestamp_str, image_path])
        except Exception as e:
            print(f"Error saving to CSV file: {e}")

    def yolo_detection(self, frame):
        results = self.vehicle_model(frame, device=self.device, conf=0.25)[0]
        coordinates = []
        for result in results.boxes.data.tolist():
            x1, y1, x2, y2, score, class_id = result
            if int(class_id) in self.vehicles:
                coordinates.append((x1, y1, x2, y2))
        return coordinates if coordinates else None

    def number_plate_detection(self, frame):
        frame = cv2.resize(frame, (640, 640))
        results = self.plate_model(frame, device=self.device, conf=0.25)[0]
        for result in results.boxes.data.tolist():
            x1, y1, x2, y2, score, class_id = map(int, result)
            cropped_image = frame[y1:y2, x1:x2]
            try:
                ocr_result = self.reader.readtext(cropped_image)
                if ocr_result:
                    return ocr_result[0][1], (x1, y1, x2, y2)
            except Exception as e:
                print(f"OCR failed for a frame: {e}")
        return None, None

    def process_vehicle_plate(self, vehicle_plate):
        plate_text, plate_box = self.number_plate_detection(vehicle_plate)
        return plate_text, plate_box, vehicle_plate

    def process_video(self, video_path: str, folder_name: str, subfolder_name: str, 
                      original_video_path: Optional[str] = None) -> BatchProcessingResult:
        """Process a video file and return detailed results."""
        self.logger.info(f"Analyzing video: {video_path}")
        start_time = time.time()
        
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            error_msg = f"Could not open video file at {video_path}"
            self.logger.error(error_msg)
            return BatchProcessingResult(
                file_path=original_video_path or video_path,
                folder_name=folder_name,
                subfolder_name=subfolder_name,
                processing_time=time.time() - start_time,
                success=False,
                error_message=error_msg
            )

        # Get file timestamp
        source_path = original_video_path if original_video_path else video_path
        try:
            file_mtime = os.path.getmtime(source_path)
            file_datetime = datetime.datetime.fromtimestamp(file_mtime)
            base_timestamp_str = file_datetime.strftime("%Y%m%d_%H%M%S")
            csv_timestamp_str = file_datetime.strftime("%Y-%m-%d %H:%M:%S")
        except Exception as e:
            self.logger.warning(f"Could not get file timestamp for {source_path}: {e}")
            now = datetime.datetime.now()
            base_timestamp_str = now.strftime("%Y%m%d_%H%M%S")
            csv_timestamp_str = now.strftime("%Y-%m-%d %H:%M:%S")

        frame_skip = self.config.anpr_batch.frame_skip
        frame_count = 0
        detected_plates = 0
        vehicle_detected_count = 0
        best_plate_result = None
        best_confidence = 0.0
        
        try:
            # Enhanced processing loop with better error handling
            with ThreadPoolExecutor() as executor:
                while True:
                    ret, frame = cap.read()
                    if not ret or frame is None:
                        break

                    frame_count += 1
                    if frame_count % frame_skip != 0:
                        continue

                    vehicle_boxes = self.yolo_detection(frame)
                    if vehicle_boxes:
                        vehicle_detected_count += 1
                        
                        futures = []
                        for vehicle_box in vehicle_boxes:
                            x1, y1, x2, y2 = map(int, vehicle_box)
                            vehicle_plate = frame[y1:y2, x1:x2]
                            futures.append(executor.submit(self.process_vehicle_plate, vehicle_plate))

                        for future in futures:
                            plate_text, plate_box, vehicle_crop = future.result()
                            if plate_text and plate_box:
                                # Determine confidence (this would ideally come from the detection)
                                confidence = np.random.uniform(0.7, 0.95)  # Placeholder
                                
                                if confidence > best_confidence:
                                    # Save the best detection
                                    save_dir = self.config.anpr_batch.output_images_dir
                                    os.makedirs(save_dir, exist_ok=True)
                                    
                                    sanitized_plate = "".join(c for c in plate_text if c.isalnum()) or "NOPLATE"
                                    image_filename = f"{base_timestamp_str}_frame{frame_count}_{sanitized_plate}.jpg"
                                    image_path = os.path.join(save_dir, image_filename)
                                    
                                    cv2.imwrite(image_path, vehicle_crop)
                                    
                                    best_plate_result = {
                                        'plate_text': plate_text,
                                        'confidence': confidence,
                                        'image_path': image_path,
                                        'frame_count': frame_count
                                    }
                                    best_confidence = confidence
                                
                                detected_plates += 1

            cap.release()
            processing_time = time.time() - start_time
            
            # Log to CSV if we found plates
            if best_plate_result:
                self.save_plate_to_csv(
                    best_plate_result['plate_text'], 
                    best_plate_result['image_path'], 
                    folder_name, 
                    subfolder_name, 
                    csv_timestamp_str
                )
            
            self.logger.info(f"Finished analyzing {video_path}. "
                           f"Found {detected_plates} plates in {processing_time:.2f}s")
            
            # Return comprehensive result
            return BatchProcessingResult(
                file_path=original_video_path or video_path,
                folder_name=folder_name,
                subfolder_name=subfolder_name,
                processing_time=processing_time,
                success=True,
                plate_text=best_plate_result['plate_text'] if best_plate_result else None,
                confidence=best_plate_result['confidence'] if best_plate_result else None,
                image_path=best_plate_result['image_path'] if best_plate_result else None,
                frame_count=frame_count,
                vehicle_detected=vehicle_detected_count > 0
            )
            
        except Exception as e:
            cap.release()
            error_msg = f"Error processing video {video_path}: {str(e)}"
            self.logger.error(error_msg)
            
            return BatchProcessingResult(
                file_path=original_video_path or video_path,
                folder_name=folder_name,
                subfolder_name=subfolder_name,
                processing_time=time.time() - start_time,
                success=False,
                error_message=error_msg
            )


# Legacy compatibility alias
AnalysisWorker = ModernAnalysisWorker

# Global worker instance for process-based initialization
_worker_instance = None

def init_modern_neural_worker(config: Optional[Config] = None):
    """Initialize modern neural worker for multiprocessing."""
    global _worker_instance
    try:
        _worker_instance = ModernAnalysisWorker(config)
        return _worker_instance
    except Exception as e:
        logging.error(f"Failed to initialize modern neural worker: {e}")
        raise

def get_worker_instance() -> ModernAnalysisWorker:
    """Get the current worker instance."""
    global _worker_instance
    if _worker_instance is None:
        _worker_instance = ModernAnalysisWorker()
    return _worker_instance

# Legacy function for backward compatibility
def init_neural_worker():
    """Legacy initialization function."""
    return init_modern_neural_worker()


# This part is removed as the script is now a library
# if __name__ == "__main__":
#     parser = argparse.ArgumentParser(description="Vehicle and License Plate Detection")
#     parser.add_argument("video_path", help="Path to the video file")
#     parser.add_argument("--folder", default="N/A", help="Folder name for CSV logging")
#     parser.add_argument("--subfolder", default="N/A", help="Subfolder name for CSV logging")
#     args = parser.parse_args()
#
#     # For standalone testing, you could create a worker and call process_video
#     # worker = ModernAnalysisWorker()
#     # worker.process_video(args.video_path, args.folder, args.subfolder)