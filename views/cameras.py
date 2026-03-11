import streamlit as st
import os
from datetime import datetime

from db.database import get_db

CAMERAS_CSS = """
<style>
    .cam-card {
        background: white;
        border-radius: 12px;
        padding: 1.5rem;
        box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        margin-bottom: 1rem;
    }
    .cam-header {
        font-family: 'Inter', sans-serif;
        font-size: 1.2rem;
        font-weight: 600;
        color: #2C3E50;
        margin-bottom: 0.5rem;
    }
    .cam-detail {
        font-size: 0.85rem;
        color: #7f8c8d;
        margin-bottom: 0.3rem;
    }
</style>
"""


def show_cameras():
    """Camera management page."""
    st.markdown(CAMERAS_CSS, unsafe_allow_html=True)

    db = get_db()

    st.title("📷 Camera Management")
    st.markdown("Monitor camera streams and manage camera configurations.")

    st.markdown("---")
    st.subheader("Add Camera")
    with st.form("add_camera_form"):
        col1, col2 = st.columns(2)
        with col1:
            cam_id = st.text_input("Camera ID", placeholder="cam_entrance_1")
            cam_name = st.text_input("Camera Name", placeholder="Main Entrance Camera")
        with col2:
            stream_url = st.text_input("Stream URL (RTSP)", placeholder="rtsp://192.168.1.100/stream1")
            gate_device_id = st.text_input("Gate Device ID (Parsec)", placeholder="device_id_123")

        mask_path = st.text_input("Mask Image Path (optional)", placeholder="masks/cam_1_mask.png")
        submitted = st.form_submit_button("Add Camera", type="primary")

        if submitted and cam_id and cam_name and stream_url:
            db.save_camera(cam_id, cam_name, stream_url, gate_device_id, mask_path)
            st.success(f"Camera '{cam_name}' added successfully!")
            st.rerun()

    st.markdown("---")
    st.subheader("Configured Cameras")

    cameras = db.get_cameras()

    if not cameras:
        st.info("No cameras configured yet. Use the form above to add cameras.")
        return

    for cam in cameras:
        status_color = {
            "online": "#27AE60", "offline": "#E74C3C", "error": "#F39C12"
        }.get(cam["status"], "#95a5a6")
        status_icon = {"online": "🟢", "offline": "🔴", "error": "🟡"}.get(cam["status"], "⚪")

        with st.container():
            st.markdown(f"""
            <div class="cam-card">
                <div class="cam-header">{status_icon} {cam['name']}</div>
                <div class="cam-detail">ID: {cam['camera_id']}</div>
                <div class="cam-detail">Stream: {cam['stream_url']}</div>
                <div class="cam-detail">Gate Device: {cam.get('gate_device_id', 'Not set')}</div>
                <div class="cam-detail">Status: <span style="color: {status_color}; font-weight: 600;">{cam['status'].upper()}</span></div>
                <div class="cam-detail">Last Frame: {cam.get('last_frame_at', 'Never')}</div>
            </div>
            """, unsafe_allow_html=True)

            col_a, col_b, col_c = st.columns([1, 1, 4])
            with col_a:
                enabled = cam.get("enabled", 1)
                toggle_label = "Disable" if enabled else "Enable"
                if st.button(toggle_label, key=f"toggle_{cam['camera_id']}"):
                    with db.get_connection() as conn:
                        conn.execute(
                            "UPDATE cameras SET enabled = ? WHERE camera_id = ?",
                            (0 if enabled else 1, cam["camera_id"]),
                        )
                    st.rerun()
            with col_b:
                if st.button("🗑 Remove", key=f"remove_{cam['camera_id']}"):
                    with db.get_connection() as conn:
                        conn.execute("DELETE FROM cameras WHERE camera_id = ?", (cam["camera_id"],))
                    st.success(f"Camera '{cam['name']}' removed.")
                    st.rerun()

    st.markdown("---")
    st.subheader("Camera Grid Preview")
    st.info("Live camera previews require active RTSP streams.")

    cols = st.columns(min(len(cameras), 3))
    for i, cam in enumerate(cameras):
        with cols[i % 3]:
            st.markdown(f"**{cam['name']}**")
            snapshot_pattern = f"{cam['camera_id']}_"
            snapshots_dir = "data/snapshots"
            if os.path.exists(snapshots_dir):
                snapshots = sorted(
                    [f for f in os.listdir(snapshots_dir)
                     if f.startswith(snapshot_pattern) and not f.endswith("_plate.jpg")],
                    reverse=True,
                )
                if snapshots:
                    latest = os.path.join(snapshots_dir, snapshots[0])
                    st.image(latest, caption="Latest snapshot", use_container_width=True)
                else:
                    st.markdown(
                        f'<div style="background:#2C3E50;color:white;padding:3rem;text-align:center;border-radius:8px;">'
                        f'📷 No snapshots<br><small>{cam["camera_id"]}</small></div>',
                        unsafe_allow_html=True,
                    )
            else:
                st.markdown(
                    f'<div style="background:#2C3E50;color:white;padding:3rem;text-align:center;border-radius:8px;">'
                    f'📷 Waiting for data<br><small>{cam["camera_id"]}</small></div>',
                    unsafe_allow_html=True,
                )
