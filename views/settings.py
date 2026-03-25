import streamlit as st
import os

from db.database import get_db
from config import get_config


def show_settings():
    """System settings page."""
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
        if config.parsec_domain:
            from parsec.api import ParsecAPI
            api = ParsecAPI(host=config.parsec_domain, port=config.parsec_port)
            if api.check_connection():
                st.success("✅ Parsec server reachable")
            else:
                st.error("❌ Parsec server not reachable")
        else:
            st.warning("⚠️ Parsec domain not configured")

    st.markdown("---")
    st.subheader("🤖 Telegram Bot")
    col1, col2 = st.columns(2)
    with col1:
        st.text_input(
            "Bot Token",
            value="***configured***" if config.telegram_bot_token else "Not set",
            disabled=True,
        )
        st.text_input("Tech Chat ID", value=str(config.tech_chat_id), disabled=True)
    with col2:
        st.text_input("Admin Chat ID", value=str(config.admin_chat_id), disabled=True)

    st.markdown("---")
    st.subheader("🔧 Recognition Settings")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.number_input(
            "Vehicle Confidence Threshold",
            value=config.confidence_vehicle,
            min_value=0.0, max_value=1.0, step=0.05, disabled=True,
        )
    with col2:
        st.number_input(
            "Plate Confidence Threshold",
            value=config.confidence_plate,
            min_value=0.0, max_value=1.0, step=0.05, disabled=True,
        )
    with col3:
        st.number_input(
            "OCR Confidence Threshold",
            value=config.confidence_ocr,
            min_value=0.0, max_value=1.0, step=0.05, disabled=True,
        )

    st.number_input(
        "Recognition Interval (seconds)",
        value=config.recognition_interval,
        min_value=0.1, max_value=10.0, step=0.1, disabled=True,
    )
    st.checkbox("GPU Enabled", value=config.gpu_enabled, disabled=True)
    st.text_input("Device", value=config.device, disabled=True)

    st.markdown("---")
    st.subheader("🧠 Training Settings")
    st.number_input(
        "Min Training Samples",
        value=config.min_training_samples,
        min_value=10, max_value=500, step=10, disabled=True,
    )
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
    st.markdown("Configuration is managed through environment variables.")
    st.code(
        "TELEGRAM_BOT_TOKEN=your_bot_token\n"
        "PARSEC_DOMAIN=192.168.1.100\n"
        "PARSEC_PORT=10101\n"
        "ADMIN_CHAT_ID=telegram_admin_group_id\n"
        "CAMERA_URLS=rtsp://cam1/stream,rtsp://cam2/stream\n"
        "GPU_ENABLED=false\n"
        "DEVICE=cpu",
        language="bash",
    )
