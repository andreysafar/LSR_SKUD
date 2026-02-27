# Gate Control System - License Plate Recognition & Access Control

## Overview
Telegram bot system integrating Parsec access control with AI-powered license plate recognition for automated gate control. Includes a Streamlit monitoring dashboard.

## Architecture

### Core Components
- **Streamlit Dashboard** (`app.py`, `pages/`) — Monitoring UI with camera status, recognition events, pass management, training status, and settings
- **Telegram Bot** (`bot/`) — User-facing bot for phone authentication, pass creation (vehicle + access group), and admin review chat
- **Parsec API Client** (`parsec/`) — SOAP API integration with Parsec access control system
- **Recognition Pipeline** (`recognition/`) — Three-stage: vehicle detection (YOLOv8) → plate detection (custom YOLO) → OCR (EasyOCR)
- **Gate Controller** (`gate/`) — Matches recognized plates against active passes, triggers gate opening via Parsec
- **Training System** (`training/`) — Collects human-labeled data, exports for retraining, Docker Compose for GPU training server

### File Structure
```
app.py                    # Streamlit main dashboard
main.py                   # Standalone runner (bot + recognition threads)
config.py                 # Unified configuration from env vars
pages/
  1_📷_Cameras.py         # Camera management page
  2_🔍_Recognition.py     # Recognition events viewer
  3_🎫_Passes.py          # Pass management page
  4_🧠_Training.py        # Training pipeline status
  5_⚙️_Settings.py       # System settings page
  6_🚪_Gate_Events.py    # Gate events log
bot/
  telegram_bot.py         # Main Telegram bot class
  handlers/
    auth.py               # Phone number authentication
    passes.py             # Pass creation & management
    admin.py              # Admin review chat (human-in-the-loop)
parsec/
  api.py                  # Parsec SOAP API client
recognition/
  pipeline.py             # Three-stage recognition orchestrator
  vehicle_detector.py     # Stage 1: YOLOv8 vehicle detection
  plate_detector.py       # Stage 2: License plate detection
  ocr_engine.py           # Stage 3: EasyOCR text recognition
  camera_manager.py       # RTSP camera stream manager
gate/
  controller.py           # Gate control logic
training/
  collector.py            # Training data collection
  manager.py              # Training session management
  train.py                # Training script (runs in Docker)
  Dockerfile              # GPU training container
  docker-compose.yml      # Training deployment
db/
  database.py             # SQLite database with full schema
data/                     # Runtime data directory
models/                   # Model weights directory
```

### Key Environment Variables
- `TELEGRAM_BOT_TOKEN` — Telegram bot token
- `PARSEC_DOMAIN`, `PARSEC_PORT` — Parsec server connection
- `PARSEC_BOT_USERNAME`, `PARSEC_BOT_PASSWORD` — Bot operator credentials
- `PARSEC_ADMIN_USERNAME`, `PARSEC_ADMIN_PASSWORD` — Admin credentials
- `TECH_CHAT_ID` — Telegram chat for admin review/training
- `CAMERA_URLS` — Comma-separated RTSP camera URLs
- `GPU_ENABLED`, `DEVICE` — GPU/CPU configuration

### Dependencies
- streamlit, python-telegram-bot, pyyaml, pydantic
- (On GPU server: ultralytics, easyocr, opencv-python, torch)

### Training Pipeline
Per-camera model weights are trained separately. Human-in-the-loop via Telegram admin chat where admins confirm/correct three stages: vehicle detection, plate detection, OCR. When enough labeled samples collected (default 50), training data is exported. Run `docker-compose up` in `training/` directory on GPU server to retrain.
