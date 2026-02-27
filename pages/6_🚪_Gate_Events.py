import streamlit as st
from db.database import get_db

st.set_page_config(page_title="Gate Events", page_icon="🚪", layout="wide")

st.markdown("""
<style>
    .gate-success {
        background: #d5f5e3;
        border-radius: 8px;
        padding: 1rem;
        margin-bottom: 0.5rem;
        border-left: 4px solid #27AE60;
    }
    .gate-fail {
        background: #fadbd8;
        border-radius: 8px;
        padding: 1rem;
        margin-bottom: 0.5rem;
        border-left: 4px solid #E74C3C;
    }
    .plate-display {
        font-family: 'Inter', monospace;
        font-size: 1.4rem;
        font-weight: 700;
        color: #2C3E50;
        background: #ECF0F1;
        padding: 0.3rem 0.8rem;
        border-radius: 6px;
        display: inline-block;
    }
</style>
""", unsafe_allow_html=True)

db = get_db()

st.title("🚪 Gate Events")
st.markdown("Track all gate open/close events and pass matches.")

col1, col2 = st.columns([2, 1])
with col1:
    cameras = db.get_cameras()
    cam_options = ["All cameras"] + [f"{c['name']} ({c['camera_id']})" for c in cameras]
    cam_filter = st.selectbox("Filter by camera", cam_options)
with col2:
    limit = st.selectbox("Show events", [25, 50, 100, 200], index=1)

cam_id = None
if cam_filter != "All cameras" and cameras:
    for c in cameras:
        if c["camera_id"] in cam_filter:
            cam_id = c["camera_id"]
            break

events = db.get_gate_events(limit=limit, camera_id=cam_id)

st.markdown(f"**{len(events)}** gate events")
st.markdown("---")

if not events:
    st.info("No gate events recorded yet. Events appear when the recognition pipeline matches a plate to an active pass.")
else:
    success_count = sum(1 for e in events if e.get("success"))
    fail_count = len(events) - success_count

    m1, m2, m3 = st.columns(3)
    m1.metric("Total Events", len(events))
    m2.metric("Successful Opens", success_count)
    m3.metric("Failed/Denied", fail_count)

    st.markdown("---")

    for ev in events:
        success = ev.get("success", 0)
        card_class = "gate-success" if success else "gate-fail"
        icon = "✅" if success else "❌"

        st.markdown(f"""
        <div class="{card_class}">
            {icon} <span class="plate-display">{ev.get('plate_number', '—')}</span>
            <span style="margin-left: 1rem; color: #555;">
                📷 {ev.get('camera_id', '—')} |
                ⏰ {ev.get('timestamp', '—')} |
                Action: {ev.get('action', '—')}
                {f" | Pass #{ev['pass_id']}" if ev.get('pass_id') else ""}
            </span>
            {f"<br><small style='color: #777; margin-left: 2rem;'>{ev.get('details', '')}</small>" if ev.get('details') else ""}
        </div>
        """, unsafe_allow_html=True)
