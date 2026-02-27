#!/usr/bin/env python3
import os
import sys
import json
import glob
import shutil
import logging
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

DATA_DIR = os.environ.get("TRAINING_DATA_DIR", "/app/data")
MODELS_DIR = os.environ.get("MODELS_DIR", "/app/models")
EPOCHS = int(os.environ.get("TRAINING_EPOCHS", "50"))
BATCH_SIZE = int(os.environ.get("TRAINING_BATCH_SIZE", "16"))
IMG_SIZE = int(os.environ.get("TRAINING_IMG_SIZE", "640"))
DEFAULT_VEHICLE_MODEL = os.environ.get("DEFAULT_VEHICLE_MODEL", "yolo26n.pt")


def find_training_manifests():
    pattern = os.path.join(DATA_DIR, "export", "*", "*", "manifest.json")
    return glob.glob(pattern)


def train_vehicle_detector(camera_id: str, manifest: dict):
    logger.info(f"Training vehicle detector for camera {camera_id}")
    try:
        from ultralytics import YOLO

        base_weights = os.path.join(MODELS_DIR, f"{camera_id}_vehicle.pt")
        if not os.path.exists(base_weights):
            base_weights = os.path.join(MODELS_DIR, DEFAULT_VEHICLE_MODEL)
        if not os.path.exists(base_weights):
            base_weights = DEFAULT_VEHICLE_MODEL

        model = YOLO(base_weights)

        dataset_dir = os.path.join(DATA_DIR, "datasets", camera_id, "vehicle")
        os.makedirs(os.path.join(dataset_dir, "images", "train"), exist_ok=True)
        os.makedirs(os.path.join(dataset_dir, "images", "val"), exist_ok=True)
        os.makedirs(os.path.join(dataset_dir, "labels", "train"), exist_ok=True)
        os.makedirs(os.path.join(dataset_dir, "labels", "val"), exist_ok=True)

        samples = manifest["samples"]
        val_split = max(1, int(len(samples) * 0.2))
        train_samples = samples[:-val_split]
        val_samples = samples[-val_split:]

        for split_name, split_samples in [("train", train_samples), ("val", val_samples)]:
            for sample in split_samples:
                img_path = sample["image_path"]
                is_positive = sample.get("is_positive", 0)
                bbox = sample.get("bbox")
                if os.path.exists(img_path):
                    dest = os.path.join(dataset_dir, "images", split_name, os.path.basename(img_path))
                    shutil.copy2(img_path, dest)
                    label_file = os.path.join(dataset_dir, "labels", split_name,
                                               os.path.splitext(os.path.basename(img_path))[0] + ".txt")
                    with open(label_file, "w") as f:
                        if is_positive and bbox:
                            f.write(f"0 {bbox[0]} {bbox[1]} {bbox[2]} {bbox[3]}\n")
                        elif is_positive:
                            f.write("0 0.5 0.5 0.8 0.8\n")

        yaml_content = f"""train: {os.path.join(dataset_dir, 'images', 'train')}
val: {os.path.join(dataset_dir, 'images', 'val')}
nc: 1
names: ['vehicle']
"""
        yaml_path = os.path.join(dataset_dir, "dataset.yaml")
        with open(yaml_path, "w") as f:
            f.write(yaml_content)

        results = model.train(
            data=yaml_path,
            epochs=EPOCHS,
            batch=BATCH_SIZE,
            imgsz=IMG_SIZE,
            device=0,
            project=os.path.join(MODELS_DIR, "runs"),
            name=f"{camera_id}_vehicle",
            exist_ok=True,
        )

        val_results = model.val(data=yaml_path, imgsz=IMG_SIZE)
        metrics = {
            "map50": float(getattr(val_results.box, 'map50', 0)),
            "map50_95": float(getattr(val_results.box, 'map', 0)),
            "precision": float(getattr(val_results.box, 'mp', 0)),
            "recall": float(getattr(val_results.box, 'mr', 0)),
        }
        logger.info(f"Vehicle validation metrics: {metrics}")

        metrics_path = os.path.join(MODELS_DIR, "runs", f"{camera_id}_vehicle", "val_metrics.json")
        with open(metrics_path, "w") as f:
            json.dump(metrics, f, indent=2)

        best_weights = os.path.join(MODELS_DIR, "runs", f"{camera_id}_vehicle", "weights", "best.pt")
        if os.path.exists(best_weights):
            output_path = os.path.join(MODELS_DIR, f"{camera_id}_vehicle.pt")
            shutil.copy2(best_weights, output_path)
            logger.info(f"Vehicle detector weights saved: {output_path}")
            return True, metrics

    except Exception as e:
        logger.error(f"Vehicle training failed for {camera_id}: {e}")
    return False, {}


def train_plate_detector(camera_id: str, manifest: dict):
    logger.info(f"Training plate detector for camera {camera_id}")
    try:
        from ultralytics import YOLO

        base_weights = os.path.join(MODELS_DIR, f"{camera_id}_plate.pt")
        if not os.path.exists(base_weights):
            base_weights = os.path.join(MODELS_DIR, "license_plate_detector.pt")
        if not os.path.exists(base_weights):
            logger.warning("No base plate detector weights found, using yolo26n.pt")
            base_weights = DEFAULT_VEHICLE_MODEL

        model = YOLO(base_weights)

        dataset_dir = os.path.join(DATA_DIR, "datasets", camera_id, "plate")
        os.makedirs(os.path.join(dataset_dir, "images", "train"), exist_ok=True)
        os.makedirs(os.path.join(dataset_dir, "images", "val"), exist_ok=True)
        os.makedirs(os.path.join(dataset_dir, "labels", "train"), exist_ok=True)
        os.makedirs(os.path.join(dataset_dir, "labels", "val"), exist_ok=True)

        samples = manifest["samples"]
        val_split = max(1, int(len(samples) * 0.2))
        train_samples = samples[:-val_split]
        val_samples = samples[-val_split:]

        for split_name, split_samples in [("train", train_samples), ("val", val_samples)]:
            for sample in split_samples:
                img_path = sample["image_path"]
                is_positive = sample.get("is_positive", 0)
                bbox = sample.get("bbox")
                if os.path.exists(img_path):
                    dest = os.path.join(dataset_dir, "images", split_name, os.path.basename(img_path))
                    shutil.copy2(img_path, dest)
                    label_file = os.path.join(dataset_dir, "labels", split_name,
                                               os.path.splitext(os.path.basename(img_path))[0] + ".txt")
                    with open(label_file, "w") as f:
                        if is_positive and bbox:
                            f.write(f"0 {bbox[0]} {bbox[1]} {bbox[2]} {bbox[3]}\n")
                        elif is_positive:
                            f.write("0 0.5 0.5 0.4 0.2\n")

        yaml_content = f"""train: {os.path.join(dataset_dir, 'images', 'train')}
val: {os.path.join(dataset_dir, 'images', 'val')}
nc: 1
names: ['plate']
"""
        yaml_path = os.path.join(dataset_dir, "dataset.yaml")
        with open(yaml_path, "w") as f:
            f.write(yaml_content)

        results = model.train(
            data=yaml_path,
            epochs=EPOCHS,
            batch=BATCH_SIZE,
            imgsz=IMG_SIZE,
            device=0,
            project=os.path.join(MODELS_DIR, "runs"),
            name=f"{camera_id}_plate",
            exist_ok=True,
        )

        val_results = model.val(data=yaml_path, imgsz=IMG_SIZE)
        metrics = {
            "map50": float(getattr(val_results.box, 'map50', 0)),
            "map50_95": float(getattr(val_results.box, 'map', 0)),
            "precision": float(getattr(val_results.box, 'mp', 0)),
            "recall": float(getattr(val_results.box, 'mr', 0)),
        }
        logger.info(f"Plate validation metrics: {metrics}")

        metrics_path = os.path.join(MODELS_DIR, "runs", f"{camera_id}_plate", "val_metrics.json")
        with open(metrics_path, "w") as f:
            json.dump(metrics, f, indent=2)

        best_weights = os.path.join(MODELS_DIR, "runs", f"{camera_id}_plate", "weights", "best.pt")
        if os.path.exists(best_weights):
            output_path = os.path.join(MODELS_DIR, f"{camera_id}_plate.pt")
            shutil.copy2(best_weights, output_path)
            logger.info(f"Plate detector weights saved: {output_path}")
            return True, metrics

    except Exception as e:
        logger.error(f"Plate training failed for {camera_id}: {e}")
    return False, {}


def main():
    logger.info("=" * 60)
    logger.info("Starting training session")
    logger.info(f"Data dir: {DATA_DIR}")
    logger.info(f"Models dir: {MODELS_DIR}")
    logger.info(f"Epochs: {EPOCHS}, Batch: {BATCH_SIZE}, ImgSize: {IMG_SIZE}")
    logger.info(f"Default model: {DEFAULT_VEHICLE_MODEL}")
    logger.info("=" * 60)

    manifests = find_training_manifests()
    if not manifests:
        logger.info("No training data found. Exiting.")
        return

    logger.info(f"Found {len(manifests)} training manifests")

    results_summary = []
    for manifest_path in manifests:
        with open(manifest_path) as f:
            manifest = json.load(f)

        camera_id = manifest["camera_id"]
        stage = manifest["stage"]
        logger.info(f"Processing: camera={camera_id}, stage={stage}, samples={manifest['samples_count']}")

        if stage == "vehicle":
            success, metrics = train_vehicle_detector(camera_id, manifest)
        elif stage == "plate":
            success, metrics = train_plate_detector(camera_id, manifest)
        elif stage == "ocr":
            logger.info("OCR training is handled separately (EasyOCR fine-tuning)")
            success = True
            metrics = {}
        else:
            logger.warning(f"Unknown stage: {stage}")
            success = False
            metrics = {}

        results_summary.append({
            "camera_id": camera_id,
            "stage": stage,
            "success": success,
            "metrics": metrics,
        })

        if success:
            archive_dir = os.path.join(DATA_DIR, "archive")
            os.makedirs(archive_dir, exist_ok=True)
            archive_name = f"{camera_id}_{stage}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            shutil.move(os.path.dirname(manifest_path),
                        os.path.join(archive_dir, archive_name))
            logger.info(f"Training data archived: {archive_name}")

    summary_path = os.path.join(MODELS_DIR, "training_summary.json")
    with open(summary_path, "w") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "results": results_summary,
        }, f, indent=2)

    logger.info("Training session complete")
    for r in results_summary:
        status = "OK" if r["success"] else "FAIL"
        logger.info(f"  {r['camera_id']}/{r['stage']}: {status} {r.get('metrics', {})}")


if __name__ == "__main__":
    main()
