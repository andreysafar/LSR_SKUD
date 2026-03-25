import os
import sys
import asyncio
import threading
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

for d in ("data", "data/snapshots", "data/training", "models"):
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        pass

_bot_instance = None
_bot_loop = None


def run_telegram_bot():
    logger.info("run_telegram_bot() called")
    global _bot_instance, _bot_loop
    from bot.telegram_bot import TelegramBot
    _bot_instance = TelegramBot()
    _bot_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_bot_loop)
    try:
        _bot_loop.run_until_complete(_bot_instance.start())
        _bot_loop.run_forever()
    except Exception as e:
        logger.error(f"Telegram bot error: {e}")
    finally:
        _bot_loop.close()


def run_recognition_pipeline():
    logger.info("run_recognition_pipeline() called")
    logger.info("Starting recognition pipeline...")
    from config import get_config
    from recognition.pipeline import RecognitionPipeline
    from db.database import get_db

    config = get_config()
    db = get_db(config.db_path)

    # If GPU requested but not available (e.g. in Docker without nvidia runtime), skip pipeline
    if config.gpu_enabled or (config.device and "cuda" in config.device.lower()):
        try:
            import torch
            if not torch.cuda.is_available():
                logger.warning(
                    "GPU requested (GPU_ENABLED=true/DEVICE=cuda) but CUDA not available in this process. "
                    "Recognition pipeline will NOT start. Bot will keep running. "
                    "To fix: run container with NVIDIA runtime (nvidia-container-toolkit on host)."
                )
                return
        except Exception as e:
            logger.warning("Could not check CUDA availability: %s. Skipping recognition pipeline.", e)
            return

    cameras = db.get_cameras(enabled_only=True)
    logger.info(f"Found {len(cameras)} enabled cameras")
    if not cameras:
        logger.info("No cameras configured, recognition pipeline idle")
        return

    pipeline_config = {
        "models_dir": config.models_dir,
        "snapshots_dir": config.snapshots_dir,
        "device": config.device,
        "gpu_enabled": config.gpu_enabled,
        "confidence_vehicle": config.confidence_vehicle,
        "confidence_plate": config.confidence_plate,
        "confidence_ocr": config.confidence_ocr,
        "recognition_interval": config.recognition_interval,
    }

    pipeline = RecognitionPipeline(pipeline_config)

    for cam in cameras:
        pipeline.add_camera(
            cam["camera_id"],
            cam["stream_url"],
            cam["name"],
            cam.get("mask_path", ""),
        )

    def on_recognition(result):
        if _bot_instance:
            _bot_instance.on_recognition_result(result)
        else:
            event_id = db.save_recognition_event(
                camera_id=result.camera_id,
                **result.to_dict()
            )
            logger.info(f"Recognition event {event_id} saved (bot not ready)")

    pipeline.set_result_callback(on_recognition)
    pipeline.start()

    while True:
        import time
        time.sleep(30)  # Update every 30 seconds

        # Sync camera statuses to database
        cam_status = pipeline.camera_manager.get_camera_status()
        for cam_id, status_info in cam_status.items():
            db_status = "online" if status_info["status"] == "online" else "offline"
            db.update_camera_status(cam_id, db_status)

        cameras = db.get_cameras(enabled_only=True)
        current_ids = set(pipeline.camera_manager.cameras.keys())
        db_ids = {c["camera_id"] for c in cameras}
        for new_id in db_ids - current_ids:
            cam = next(c for c in cameras if c["camera_id"] == new_id)
            pipeline.add_camera(cam["camera_id"], cam["stream_url"], cam["name"])
            logger.info(f"Dynamically added camera: {new_id}")


if __name__ == "__main__":
    logger.info("Main block starting")
    bot_thread = threading.Thread(target=run_telegram_bot, daemon=True)
    logger.info("Starting bot thread")
    bot_thread.start()
    logger.info("Bot thread started")

    import time
    time.sleep(2)

    logger.info("Creating recognition thread...")
    recognition_thread = threading.Thread(target=run_recognition_pipeline, daemon=True)
    recognition_thread.start()
    logger.info("Recognition thread started")

    logger.info("All services started")
    try:
        bot_thread.join()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
