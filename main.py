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

os.makedirs("data", exist_ok=True)
os.makedirs("data/snapshots", exist_ok=True)
os.makedirs("data/training", exist_ok=True)
os.makedirs("models", exist_ok=True)

_bot_instance = None
_bot_loop = None


def run_telegram_bot():
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
    from config import get_config
    from recognition.pipeline import RecognitionPipeline
    from db.database import get_db

    config = get_config()
    db = get_db(config.db_path)

    cameras = db.get_cameras(enabled_only=True)
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
        time.sleep(60)
        cameras = db.get_cameras(enabled_only=True)
        current_ids = set(pipeline.camera_manager.cameras.keys())
        db_ids = {c["camera_id"] for c in cameras}
        for new_id in db_ids - current_ids:
            cam = next(c for c in cameras if c["camera_id"] == new_id)
            pipeline.add_camera(cam["camera_id"], cam["stream_url"], cam["name"])
            logger.info(f"Dynamically added camera: {new_id}")


if __name__ == "__main__":
    bot_thread = threading.Thread(target=run_telegram_bot, daemon=True)
    bot_thread.start()

    import time
    time.sleep(2)

    recognition_thread = threading.Thread(target=run_recognition_pipeline, daemon=True)
    recognition_thread.start()

    logger.info("All services started")
    try:
        bot_thread.join()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
