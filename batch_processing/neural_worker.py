import argparse
import os
import csv
import datetime

# Disable ultralytics online checks to speed up import
os.environ['YOLO_VERBOSE'] = 'False'
os.environ['ULTRALYTICS_OFFLINE'] = 'True'

from ultralytics import YOLO
import cv2
import time
import easyocr
from concurrent.futures import ThreadPoolExecutor
import torch

class AnalysisWorker:
    def __init__(self):
        """
        Initializes the models and OCR reader. This is done once per worker process.
        """
        print("Initializing worker...")
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"Worker using device: {self.device}")

        # Ensure weight directory exists
        current_directory = os.getcwd()
        self.weight_directory = os.path.join(current_directory, 'models')
        os.makedirs(self.weight_directory, exist_ok=True)
        
        self.vehicle_model = self._load_yolo_model(
            os.path.join(self.weight_directory, 'yolov8n.pt'), 
            os.path.join(self.weight_directory, 'yolov8n.torchscript')
        )
        self.plate_model = self._load_yolo_model(
            os.path.join(self.weight_directory, 'license_plate_detector.pt'), 
            os.path.join(self.weight_directory, 'license_plate_detector.torchscript')
        )
        self.reader = self._load_ocr_reader()
        
        self.vehicles = [2, 3, 5, 7]
        self.csv_file_path = "plates.csv"

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

    def process_video(self, video_path, folder_name, subfolder_name, original_video_path=None):
        print(f"Analyzing video: {video_path}")
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            print(f"Error: Could not open video file at {video_path}")
            return False

        # Получаем время создания/модификации оригинального файла
        source_path = original_video_path if original_video_path else video_path
        try:
            file_mtime = os.path.getmtime(source_path)
            file_datetime = datetime.datetime.fromtimestamp(file_mtime)
            base_timestamp_str = file_datetime.strftime("%Y%m%d_%H%M%S")
            csv_timestamp_str = file_datetime.strftime("%Y-%m-%d %H:%M:%S")
        except Exception as e:
            print(f"Warning: Could not get file timestamp for {source_path}: {e}")
            # Fallback to current time
            now = datetime.datetime.now()
            base_timestamp_str = now.strftime("%Y%m%d_%H%M%S")
            csv_timestamp_str = now.strftime("%Y-%m-%d %H:%M:%S")

        frame_skip = 10
        frame_count = 0
        
        detected_plates = 0
        
        # This inner ThreadPoolExecutor is not ideal, but let's keep it for now
        # to minimize changes. A better approach would be to process frames sequentially
        # or use a more sophisticated async pattern if I/O is the bottleneck here.
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
                    futures = []
                    for vehicle_box in vehicle_boxes:
                        x1, y1, x2, y2 = map(int, vehicle_box)
                        vehicle_plate = frame[y1:y2, x1:x2]
                        futures.append(executor.submit(self.process_vehicle_plate, vehicle_plate))

                    for future in futures:
                        plate_text, plate_box, vehicle_crop = future.result()
                        if plate_text and plate_box:
                            save_dir = "detected_vehicles"
                            os.makedirs(save_dir, exist_ok=True)
                            
                            # Используем время файла + номер кадра для уникальности
                            sanitized_plate = "".join(c for c in plate_text if c.isalnum()) or "NOPLATE"
                            image_filename = f"{base_timestamp_str}_frame{frame_count}_{sanitized_plate}.jpg"
                            image_path = os.path.join(save_dir, image_filename)
                            
                            cv2.imwrite(image_path, vehicle_crop)
                            self.save_plate_to_csv(plate_text, image_path, folder_name, subfolder_name, csv_timestamp_str)
                            detected_plates += 1
        
        cap.release()
        print(f"Finished analyzing {video_path}. Found {detected_plates} plates.")
        return True


# This part is removed as the script is now a library
# if __name__ == "__main__":
#     parser = argparse.ArgumentParser(description="Vehicle and License Plate Detection")
#     parser.add_argument("video_path", help="Path to the video file")
#     parser.add_argument("--folder", default="N/A", help="Folder name for CSV logging")
#     parser.add_argument("--subfolder", default="N/A", help="Subfolder name for CSV logging")
#     args = parser.parse_args()
#
#     # For standalone testing, you could create a worker and call process_video
#     # worker = AnalysisWorker()
#     # worker.process_video(args.video_path, args.folder, args.subfolder)