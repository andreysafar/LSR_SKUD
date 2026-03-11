import streamlit as st
import os

from db.database import get_db

RECOGNITION_CSS = """
<style>
    .plate-big {
        font-family: 'Inter', monospace;
        font-size: 1.5rem;
        font-weight: 700;
        color: #2C3E50;
        background: #ECF0F1;
        padding: 0.4rem 1rem;
        border-radius: 8px;
        display: inline-block;
        margin: 0.5rem 0;
    }
    .conf-badge {
        display: inline-block;
        padding: 0.2rem 0.6rem;
        border-radius: 12px;
        font-size: 0.8rem;
        font-weight: 600;
        margin: 0.2rem;
    }
    .conf-high { background: #d5f5e3; color: #27AE60; }
    .conf-mid { background: #fef9e7; color: #F39C12; }
    .conf-low { background: #fadbd8; color: #E74C3C; }
</style>
"""


def _conf_class(val: float) -> str:
    if val >= 0.8:
        return "conf-high"
    if val >= 0.5:
        return "conf-mid"
    return "conf-low"


def show_recognition():
    """Recognition events page."""
    st.markdown(RECOGNITION_CSS, unsafe_allow_html=True)

    db = get_db()

    st.title("🔍 Recognition Events")

    col_f1, col_f2, col_f3 = st.columns([2, 2, 1])
    with col_f1:
        cameras = db.get_cameras()
        cam_options = ["All cameras"] + [f"{c['name']} ({c['camera_id']})" for c in cameras]
        cam_filter = st.selectbox("Camera", cam_options)
    with col_f2:
        plate_search = st.text_input("Search plate", placeholder="А123ВС77")
    with col_f3:
        limit = st.selectbox("Show", [20, 50, 100, 200], index=1)

    cam_id = None
    if cam_filter != "All cameras" and cameras:
        for c in cameras:
            if c["camera_id"] in cam_filter:
                cam_id = c["camera_id"]
                break

    events = db.get_recognition_events(
        camera_id=cam_id,
        limit=limit,
        plate_filter=plate_search if plate_search else None,
    )

    st.markdown(f"**{len(events)}** events found")
    st.markdown("---")

    if not events:
        st.info("No recognition events found.")
        return

    for ev in events:
        with st.container():
            cols = st.columns([1, 2, 2, 1])

            with cols[0]:
                if ev.get("frame_path") and os.path.exists(ev["frame_path"]):
                    st.image(ev["frame_path"], caption="Frame", use_container_width=True)
                else:
                    st.markdown("📷 No image")
                if ev.get("plate_image_path") and os.path.exists(ev["plate_image_path"]):
                    st.image(ev["plate_image_path"], caption="Plate", use_container_width=True)

            with cols[1]:
                plate = ev.get("final_plate") or ev.get("ocr_text") or "—"
                st.markdown(f'<div class="plate-big">{plate}</div>', unsafe_allow_html=True)
                st.markdown(f"**Camera:** {ev.get('camera_id', '—')}")
                st.markdown(f"**Time:** {ev.get('timestamp', '—')}")
                st.markdown(f"**Vehicle Class:** {ev.get('vehicle_class', '—')}")

            with cols[2]:
                v_conf = ev.get("vehicle_confidence", 0) or 0
                p_conf = ev.get("plate_confidence", 0) or 0
                o_conf = ev.get("ocr_confidence", 0) or 0
                st.markdown(
                    f'<span class="conf-badge {_conf_class(v_conf)}">Vehicle: {v_conf:.0%}</span>'
                    f'<span class="conf-badge {_conf_class(p_conf)}">Plate: {p_conf:.0%}</span>'
                    f'<span class="conf-badge {_conf_class(o_conf)}">OCR: {o_conf:.0%}</span>',
                    unsafe_allow_html=True,
                )
                if ev.get("ocr_corrected"):
                    st.markdown(f"**Corrected:** {ev['ocr_corrected']}")

            with cols[3]:
                reviewed = ev.get("admin_reviewed", 0)
                gate = ev.get("gate_opened", 0)
                matched = ev.get("matched_pass_id")
                if gate:
                    st.markdown("🔓 **Gate Opened**")
                if matched:
                    st.markdown(f"🎫 Pass #{matched}")
                if reviewed:
                    st.markdown("✅ Reviewed")
                else:
                    st.markdown("⏳ Pending Review")

            st.markdown("---")
