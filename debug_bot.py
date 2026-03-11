#!/usr/bin/env python3
"""
Debug script to test bot and recognition pipeline initialization.
Run with: GPU_ENABLED=true DEVICE=cuda python3 debug_bot.py
"""
import os
import sys
import logging
import asyncio

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

def test_imports():
    """Test all critical imports."""
    logger.info("=" * 60)
    logger.info("Testing imports...")
    logger.info("=" * 60)
    
    try:
        from config import get_config
        config = get_config()
        logger.info(f"✓ Config loaded: GPU={config.gpu_enabled}, Device={config.device}")
        logger.info(f"  Telegram token configured: {bool(config.telegram_bot_token)}")
        logger.info(f"  Tech chat ID: {config.tech_chat_id}")
        logger.info(f"  Parsec domain: {config.parsec_domain}")
        return config
    except Exception as e:
        logger.error(f"✗ Config import failed: {e}", exc_info=True)
        raise

def test_database(config):
    """Test database connection."""
    logger.info("=" * 60)
    logger.info("Testing database...")
    logger.info("=" * 60)
    
    try:
        from db.database import get_db
        db = get_db(config.db_path)
        stats = db.get_stats()
        logger.info(f"✓ Database connected")
        logger.info(f"  Total users: {stats.get('total_users', 0)}")
        logger.info(f"  Active passes: {stats.get('active_passes', 0)}")
        logger.info(f"  Cameras online: {stats.get('cameras_online', 0)}/{stats.get('cameras_total', 0)}")
        return db
    except Exception as e:
        logger.error(f"✗ Database connection failed: {e}", exc_info=True)
        raise

def test_bot_initialization(config):
    """Test bot initialization (without starting it)."""
    logger.info("=" * 60)
    logger.info("Testing bot initialization...")
    logger.info("=" * 60)
    
    try:
        from bot.telegram_bot import TelegramBot
        bot = TelegramBot()
        logger.info(f"✓ TelegramBot instance created")
        logger.info(f"  Bot token configured: {bool(config.telegram_bot_token)}")
        logger.info(f"  Auth handler: {bot.auth_handler is not None}")
        logger.info(f"  Pass handler: {bot.pass_handler is not None}")
        logger.info(f"  Admin handler: {bot.admin_handler is not None}")
        logger.info(f"  Gate controller: {bot.gate_controller is not None}")
        return bot
    except Exception as e:
        logger.error(f"✗ Bot initialization failed: {e}", exc_info=True)
        raise

def test_recognition_pipeline(config):
    """Test recognition pipeline initialization."""
    logger.info("=" * 60)
    logger.info("Testing recognition pipeline...")
    logger.info("=" * 60)
    
    try:
        from recognition.pipeline import RecognitionPipeline
        from db.database import get_db
        
        db = get_db(config.db_path)
        cameras = db.get_cameras(enabled_only=True)
        logger.info(f"✓ Found {len(cameras)} enabled cameras")
        
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
        logger.info(f"✓ RecognitionPipeline initialized")
        logger.info(f"  Device: {config.device}")
        logger.info(f"  GPU enabled: {config.gpu_enabled}")
        logger.info(f"  Models dir: {config.models_dir}")
        
        if cameras:
            for cam in cameras:
                logger.info(f"  Camera: {cam['name']} ({cam['camera_id']})")
        
        return pipeline
    except Exception as e:
        logger.error(f"✗ Recognition pipeline initialization failed: {e}", exc_info=True)
        raise

def main():
    """Run all debug tests."""
    logger.info("\n" + "=" * 60)
    logger.info("LSR_SKUD DEBUG - Bot & Pipeline Diagnostics")
    logger.info("=" * 60 + "\n")
    
    try:
        config = test_imports()
        db = test_database(config)
        bot = test_bot_initialization(config)
        pipeline = test_recognition_pipeline(config)
        
        logger.info("\n" + "=" * 60)
        logger.info("✓ All tests passed! System is ready.")
        logger.info("=" * 60)
        logger.info("\nNext steps:")
        logger.info("1. Run 'python3 main.py' to start bot and recognition pipeline")
        logger.info("2. Run 'streamlit run app.py' for web dashboard")
        logger.info("3. Check logs for any warnings or issues")
        
        return 0
        
    except Exception as e:
        logger.error("\n" + "=" * 60)
        logger.error("✗ Debug tests failed!")
        logger.error("=" * 60)
        return 1

if __name__ == "__main__":
    sys.exit(main())
