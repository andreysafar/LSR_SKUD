#!/usr/bin/env python3
"""
Debug script to run bot locally (for testing/debugging).
Usage: DEVICE=cuda GPU_ENABLED=true python3 run_bot_debug.py
"""
import os
import sys
import logging

# Set up logging before importing anything else
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s [%(name)s:%(lineno)d] %(message)s",
)
logger = logging.getLogger(__name__)

# Create necessary directories
for d in ("data", "data/snapshots", "data/training", "models", "batch_processing/logs"):
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        pass

logger.info("=" * 80)
logger.info("LSR_SKUD Bot Debug Runner")
logger.info("=" * 80)

# Check GPU
try:
    import torch
    logger.info(f"PyTorch Version: {torch.__version__}")
    logger.info(f"CUDA Available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        logger.info(f"GPU Count: {torch.cuda.device_count()}")
        for i in range(torch.cuda.device_count()):
            logger.info(f"  GPU {i}: {torch.cuda.get_device_name(i)}")
except Exception as e:
    logger.warning(f"PyTorch check failed: {e}")

# Check config
try:
    logger.info("\nLoading configuration...")
    from config import get_config
    config = get_config()
    logger.info(f"✓ Config loaded")
    logger.info(f"  - Device: {config.device}")
    logger.info(f"  - GPU Enabled: {config.gpu_enabled}")
    logger.info(f"  - Telegram Token: {'configured' if config.telegram_bot_token else 'NOT SET'}")
    logger.info(f"  - Tech Chat ID: {config.tech_chat_id}")
except Exception as e:
    logger.error(f"✗ Config load failed: {e}", exc_info=True)
    sys.exit(1)

# Check database
try:
    logger.info("\nInitializing database...")
    from db.database import get_db
    db = get_db(config.db_path)
    stats = db.get_stats()
    logger.info(f"✓ Database initialized")
    logger.info(f"  - Users: {stats.get('total_users', 0)}")
    logger.info(f"  - Cameras: {stats.get('cameras_total', 0)}")
except Exception as e:
    logger.error(f"✗ Database init failed: {e}", exc_info=True)
    sys.exit(1)

# Initialize bot
try:
    logger.info("\nInitializing Telegram Bot...")
    from bot.telegram_bot import TelegramBot
    bot = TelegramBot()
    logger.info(f"✓ Bot instance created")
except Exception as e:
    logger.error(f"✗ Bot init failed: {e}", exc_info=True)
    sys.exit(1)

# Initialize recognition pipeline
try:
    logger.info("\nInitializing Recognition Pipeline...")
    from recognition.pipeline import RecognitionPipeline
    
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
    logger.info(f"✓ Pipeline initialized")
    logger.info(f"  - Device: {config.device}")
    logger.info(f"  - GPU: {config.gpu_enabled}")
except Exception as e:
    logger.error(f"✗ Pipeline init failed: {e}", exc_info=True)
    sys.exit(1)

logger.info("\n" + "=" * 80)
logger.info("✓ All systems initialized successfully!")
logger.info("=" * 80)

logger.info("\n📋 System Status:")
logger.info(f"  - Telegram Bot: {'READY' if config.telegram_bot_token else 'NOT CONFIGURED'}")
logger.info(f"  - GPU: {'ENABLED' if config.gpu_enabled else 'DISABLED'}")
logger.info(f"  - Database: READY")
logger.info(f"  - Recognition Pipeline: READY")

# Now run the actual bot in main thread
try:
    logger.info("\n🚀 Starting services...")
    import asyncio
    import threading
    import time
    
    def run_telegram_bot():
        logger.info("Starting Telegram Bot in thread...")
        _bot_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_bot_loop)
        try:
            _bot_loop.run_until_complete(bot.start())
            _bot_loop.run_forever()
        except Exception as e:
            logger.error(f"Bot error: {e}", exc_info=True)
        finally:
            _bot_loop.close()
    
    def run_recognition_pipeline():
        logger.info("Starting Recognition Pipeline in thread...")
        cameras = db.get_cameras(enabled_only=True)
        logger.info(f"Found {len(cameras)} cameras")
        
        for cam in cameras:
            pipeline.add_camera(
                cam["camera_id"],
                cam["stream_url"],
                cam["name"],
                cam.get("mask_path", ""),
            )
            logger.info(f"  Added camera: {cam['name']} ({cam['camera_id']})")
        
        def on_recognition(result):
            logger.debug(f"Recognition result: {result.camera_id} -> {result.normalized_plate}")
            if bot._bot:
                asyncio.run_coroutine_threadsafe(
                    bot.send_review_to_admin(
                        db.save_recognition_event(
                            camera_id=result.camera_id,
                            **result.to_dict()
                        ),
                        result.camera_id,
                        result.to_dict()
                    ),
                    bot._bot_loop if hasattr(bot, '_bot_loop') and bot._bot_loop else asyncio.get_event_loop(),
                )
        
        pipeline.set_result_callback(on_recognition)
        pipeline.start()
        
        while True:
            time.sleep(30)
    
    # Start services in threads
    bot_thread = threading.Thread(target=run_telegram_bot, daemon=True)
    bot_thread.start()
    logger.info("✓ Telegram Bot thread started")
    
    time.sleep(2)
    
    recognition_thread = threading.Thread(target=run_recognition_pipeline, daemon=True)
    recognition_thread.start()
    logger.info("✓ Recognition Pipeline thread started")
    
    logger.info("\n✅ All services running!")
    logger.info("Press Ctrl+C to stop\n")
    
    # Keep main thread alive
    bot_thread.join()
    
except KeyboardInterrupt:
    logger.info("\n\n🛑 Shutting down gracefully...")
except Exception as e:
    logger.error(f"Fatal error: {e}", exc_info=True)
    sys.exit(1)
