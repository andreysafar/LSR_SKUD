#!/usr/bin/env python3
"""
Pre-download model weights for LSR_SKUD (YOLO + EasyOCR).
- yolov8n.pt: batch processing vehicle detector
- yolo26n.pt: live recognition vehicle detector (or fallback from yolov8n.pt)
- EasyOCR: OCR models (en) into models/
Run from project root: python scripts/download_weights.py
"""
import os
import sys
import urllib.request
import ssl

# Project root = parent of scripts/
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS_DIR = os.path.join(PROJECT_ROOT, "models")
os.makedirs(MODELS_DIR, exist_ok=True)


def download_yolo_weights():
    """Download YOLOv8n if missing (batch vehicle detector)."""
    path = os.path.join(MODELS_DIR, "yolov8n.pt")
    if os.path.exists(path) and os.path.getsize(path) > 1_000_000:
        print(f"[OK] yolov8n.pt already present ({os.path.getsize(path) // 1024 // 1024} MB)")
        return
    url = "https://github.com/ultralytics/assets/releases/download/v0.0.0/yolov8n.pt"
    print(f"Downloading yolov8n.pt from {url} ...")
    try:
        ssl_ctx = ssl.create_default_context()
        urllib.request.urlretrieve(url, path)
        print(f"[OK] Saved to {path}")
    except Exception as e:
        # Fallback: let Ultralytics download on first YOLO() call
        print(f"[WARN] Direct download failed: {e}. Will use Ultralytics cache on first run.")
        try:
            sys.path.insert(0, PROJECT_ROOT)
            os.environ["YOLO_VERBOSE"] = "False"
            from ultralytics import YOLO
            m = YOLO("yolov8n.pt")
            # Ultralytics caches to hub dir; copy to our models if we can find it
            import torch
            hub_dir = torch.hub.get_dir()
            for root, _, files in os.walk(hub_dir):
                for f in files:
                    if f == "yolov8n.pt":
                        src = os.path.join(root, f)
                        import shutil
                        shutil.copy2(src, path)
                        print(f"[OK] Copied from cache to {path}")
                        return
        except Exception as e2:
            print(f"[WARN] Ultralytics fallback failed: {e2}")


def download_yolo26n_weights():
    """Download yolo26n.pt if missing (live recognition default vehicle detector)."""
    path = os.path.join(MODELS_DIR, "yolo26n.pt")
    if os.path.exists(path) and os.path.getsize(path) > 1_000_000:
        print(f"[OK] yolo26n.pt already present ({os.path.getsize(path) // 1024 // 1024} MB)")
        return
    # 1) Direct download from Ultralytics assets (same URL Ultralytics uses)
    url = "https://github.com/ultralytics/assets/releases/download/v8.4.0/yolo26n.pt"
    print("Downloading yolo26n.pt (live recognition vehicle model) ...")
    try:
        ssl_ctx = ssl.create_default_context()
        urllib.request.urlretrieve(url, path)
        if os.path.exists(path) and os.path.getsize(path) > 1_000_000:
            print(f"[OK] yolo26n.pt downloaded from GitHub ({os.path.getsize(path) // 1024 // 1024} MB)")
            return
    except Exception as e:
        print(f"[WARN] Direct download failed: {e}")
    # 2) Try Ultralytics (may cache to custom dir); copy to our models if found
    try:
        sys.path.insert(0, PROJECT_ROOT)
        os.environ["YOLO_VERBOSE"] = "False"
        from ultralytics import YOLO
        m = YOLO("yolo26n.pt")
        import pathlib
        for base in [
            pathlib.Path.home() / ".config" / "Ultralytics",
            pathlib.Path.home() / ".ultralytics",
            pathlib.Path(__file__).resolve().parent.parent / "models",
        ]:
            if base.exists():
                for f in base.rglob("yolo26n.pt"):
                    import shutil
                    shutil.copy2(str(f), path)
                    print(f"[OK] yolo26n.pt copied from cache to {path}")
                    return
        import torch
        for root, _, files in os.walk(torch.hub.get_dir()):
            if "yolo26n.pt" in files:
                import shutil
                shutil.copy2(os.path.join(root, "yolo26n.pt"), path)
                print(f"[OK] yolo26n.pt copied from hub to {path}")
                return
    except Exception as e:
        print(f"[WARN] Ultralytics load/copy failed: {e}")
    # 3) Fallback: use yolov8n.pt only if yolo26n.pt is still missing
    if os.path.exists(path) and os.path.getsize(path) > 1_000_000:
        return
    yolov8_path = os.path.join(MODELS_DIR, "yolov8n.pt")
    if os.path.exists(yolov8_path):
        import shutil
        shutil.copy2(yolov8_path, path)
        print(f"[OK] yolo26n.pt not available; using yolov8n.pt as fallback (copied to yolo26n.pt)")
    else:
        print("[WARN] yolo26n.pt missing and yolov8n.pt not available. Install deps and run again or copy weights to models/.")


def download_easyocr_weights():
    """Pre-download EasyOCR models into project models dir."""
    # EasyOCR stores in model_storage_directory; first run downloads
    print("Pre-downloading EasyOCR models (en) ...")
    try:
        sys.path.insert(0, PROJECT_ROOT)
        import easyocr
        import torch
        reader = easyocr.Reader(
            ["en"],
            model_storage_directory=MODELS_DIR,
            download_enabled=True,
            gpu=torch.cuda.is_available(),
        )
        print("[OK] EasyOCR models ready in", MODELS_DIR)
    except Exception as e:
        print(f"[WARN] EasyOCR pre-download failed: {e}. Will download on first inference.")


def main():
    print("Weights directory:", MODELS_DIR)
    download_yolo_weights()
    download_yolo26n_weights()
    download_easyocr_weights()
    print("Done.")


if __name__ == "__main__":
    main()
