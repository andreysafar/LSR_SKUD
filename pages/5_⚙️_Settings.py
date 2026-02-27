import streamlit as st
import os
import json

from db.database import get_db
from config import get_config

st.set_page_config(page_title="Settings", page_icon="⚙️", layout="wide")

db = get_db()
config = get_config()

st.title("⚙️ System Settings")

st.subheader("🔌 Parsec Connection")
col1, col2 = st.columns(2)
with col1:
    st.text_input("Parsec Domain", value=config.parsec_domain, disabled=True)
    st.text_input("Parsec Port", value=str(config.parsec_port), disabled=True)
    st.text_input("Bot Username", value=config.parsec_bot_username, disabled=True)
with col2:
    st.text_input("Admin Username", value=config.parsec_admin_username, disabled=True)
    parsec_status = "Unknown"
    if config.parsec_domain:
        from parsec.api import ParsecAPI
        api = ParsecAPI(config.parsec_domain, config.parsec_port)
        if api.check_connection():
            parsec_status = "Connected"
            st.success("✅ Parsec server reachable")
        else:
            parsec_status = "Not reachable"
            st.error("❌ Parsec server not reachable")
    else:
        st.warning("⚠️ Parsec domain not configured")

st.markdown("---")
st.subheader("🤖 Telegram Bot")
col1, col2 = st.columns(2)
with col1:
    bot_token_status = "Configured" if config.telegram_bot_token else "Not set"
    st.text_input("Bot Token", value="***configured***" if config.telegram_bot_token else "Not set", disabled=True)
    st.text_input("Tech Chat ID", value=str(config.tech_chat_id), disabled=True)
with col2:
    st.text_input("Admin Chat ID", value=str(config.admin_chat_id), disabled=True)

st.markdown("---")
st.subheader("🔧 Recognition Settings")
col1, col2, col3 = st.columns(3)
with col1:
    st.number_input("Vehicle Confidence Threshold", value=config.confidence_vehicle,
                     min_value=0.0, max_value=1.0, step=0.05, disabled=True)
with col2:
    st.number_input("Plate Confidence Threshold", value=config.confidence_plate,
                     min_value=0.0, max_value=1.0, step=0.05, disabled=True)
with col3:
    st.number_input("OCR Confidence Threshold", value=config.confidence_ocr,
                     min_value=0.0, max_value=1.0, step=0.05, disabled=True)

st.number_input("Recognition Interval (seconds)", value=config.recognition_interval,
                 min_value=0.1, max_value=10.0, step=0.1, disabled=True)
st.checkbox("GPU Enabled", value=config.gpu_enabled, disabled=True)
st.text_input("Device", value=config.device, disabled=True)

st.markdown("---")
st.subheader("🧠 Training Settings")
st.number_input("Min Training Samples", value=config.min_training_samples,
                 min_value=10, max_value=500, step=10, disabled=True)
st.text_input("Training Data Directory", value=config.training_data_dir, disabled=True)
st.text_input("Models Directory", value=config.models_dir, disabled=True)

st.markdown("---")
st.subheader("📊 System Info")
stats = db.get_stats()

col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Total Users", stats["total_users"])
    st.metric("Active Passes", stats["active_passes"])
with col2:
    st.metric("Cameras Total", stats["cameras_total"])
    st.metric("Cameras Online", stats["cameras_online"])
with col3:
    st.metric("Recognitions Today", stats["recognitions_today"])
    st.metric("Gates Opened Today", stats["gates_opened_today"])

st.markdown("---")
st.subheader("🔑 Environment Variables")
st.markdown("Configuration is managed through environment variables. Set them in the Secrets tab.")
st.code("""
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_API_ID=your_api_id
TELEGRAM_API_HASH=your_api_hash

PARSEC_DOMAIN=192.168.1.100
PARSEC_PORT=10101
PARSEC_BOT_USERNAME=bot_operator
PARSEC_BOT_PASSWORD=bot_password
PARSEC_ADMIN_USERNAME=admin
PARSEC_ADMIN_PASSWORD=admin_password

ADMIN_CHAT_ID=telegram_admin_group_id
TECH_CHAT_ID=telegram_tech_chat_id

CAMERA_URLS=rtsp://cam1/stream,rtsp://cam2/stream
CAMERA_0_NAME=Main Entrance
CAMERA_0_GATE_ID=device_id_1
CAMERA_1_NAME=Side Gate
CAMERA_1_GATE_ID=device_id_2

GPU_ENABLED=false
DEVICE=cpu
CONFIDENCE_VEHICLE=0.5
CONFIDENCE_PLATE=0.5
CONFIDENCE_OCR=0.4
RECOGNITION_INTERVAL=0.5
MIN_TRAINING_SAMPLES=50
""", language="bash")
