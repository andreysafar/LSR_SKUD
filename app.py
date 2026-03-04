import streamlit as st
import os
import sys
from datetime import datetime, timedelta

# Ensure directories exist (ignore permission errors on mounted volumes)
for d in ("data", "data/snapshots", "data/training", "models", "batch_processing"):
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        pass

from db.database import get_db
from pages.batch_processing import show_batch_processing
from analytics.batch_analytics import show_batch_analytics

st.set_page_config(
    page_title="LSR SKUD - Gate Control System",
    page_icon="🚗",
    layout="wide",
    initial_sidebar_state="expanded",
)

CUSTOM_CSS = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    .main-header {
        font-family: 'Inter', sans-serif;
        color: #2C3E50;
        font-size: 2rem;
        font-weight: 700;
        margin-bottom: 0.5rem;
    }
    .sub-header {
        font-family: 'Inter', sans-serif;
        color: #7f8c8d;
        font-size: 1rem;
        margin-bottom: 2rem;
    }
    .metric-card {
        background: white;
        border-radius: 12px;
        padding: 1.2rem;
        box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        border-left: 4px solid;
        margin-bottom: 1rem;
    }
    .metric-card.blue { border-left-color: #3498DB; }
    .metric-card.green { border-left-color: #27AE60; }
    .metric-card.orange { border-left-color: #F39C12; }
    .metric-card.red { border-left-color: #E74C3C; }
    .metric-value {
        font-family: 'Inter', sans-serif;
        font-size: 2rem;
        font-weight: 700;
        color: #2C3E50;
    }
    .metric-label {
        font-family: 'Inter', sans-serif;
        font-size: 0.85rem;
        color: #7f8c8d;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .status-online { color: #27AE60; font-weight: 600; }
    .status-offline { color: #E74C3C; font-weight: 600; }
    .status-error { color: #F39C12; font-weight: 600; }
    .event-card {
        background: white;
        border-radius: 8px;
        padding: 1rem;
        margin-bottom: 0.5rem;
        box-shadow: 0 1px 4px rgba(0,0,0,0.06);
    }
    .plate-number {
        font-family: 'Inter', monospace;
        font-size: 1.3rem;
        font-weight: 700;
        color: #2C3E50;
        background: #ECF0F1;
        padding: 0.3rem 0.8rem;
        border-radius: 6px;
        display: inline-block;
    }
    .sidebar .sidebar-content {
        background-color: #2C3E50;
    }
    div[data-testid="stSidebar"] {
        background-color: #2C3E50;
    }
    div[data-testid="stSidebar"] .stMarkdown p,
    div[data-testid="stSidebar"] .stMarkdown h1,
    div[data-testid="stSidebar"] .stMarkdown h2,
    div[data-testid="stSidebar"] .stMarkdown h3 {
        color: white;
    }
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

def main():
    """Main application with navigation."""
    # Sidebar navigation
    st.sidebar.title("🚗 LSR SKUD")
    st.sidebar.markdown("### Navigation")
    
    page = st.sidebar.selectbox("Choose a page", [
        "🏠 Dashboard",
        "📹 Live Recognition", 
        "🔄 Batch Processing",
        "👥 User Management",
        "🎯 Training",
        "📊 Analytics",
        "⚙️ Settings"
    ])
    
    # Add system status in sidebar
    st.sidebar.markdown("---")
    st.sidebar.markdown("### System Status")
    
    try:
        db = get_db()
        stats = db.get_stats()
        st.sidebar.success(f"✅ Database Connected")
        st.sidebar.info(f"📊 {stats['total_users']} Users | {stats['active_passes']} Active Passes")
    except Exception as e:
        st.sidebar.error("❌ Database Error")
        st.sidebar.caption(str(e))
    
    # Route to appropriate page
    if page == "🏠 Dashboard":
        show_dashboard()
    elif page == "📹 Live Recognition":
        show_live_recognition()
    elif page == "🔄 Batch Processing":
        show_batch_processing()
    elif page == "👥 User Management":
        show_user_management()
    elif page == "🎯 Training":
        show_training()
    elif page == "📊 Analytics":
        show_analytics()
    elif page == "⚙️ Settings":
        show_settings()


def show_dashboard():
    """Show main dashboard (original content)."""
    db = get_db()
    stats = db.get_stats()

    st.markdown('<div class="main-header">🚗 Gate Control System</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">License Plate Recognition & Access Control Dashboard</div>', unsafe_allow_html=True)

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.markdown(f"""
    <div class="metric-card blue">
        <div class="metric-label">Registered Users</div>
        <div class="metric-value">{stats['total_users']}</div>
    </div>
    """, unsafe_allow_html=True)

with col2:
    st.markdown(f"""
    <div class="metric-card green">
        <div class="metric-label">Active Passes</div>
        <div class="metric-value">{stats['active_passes']}</div>
    </div>
    """, unsafe_allow_html=True)

with col3:
    st.markdown(f"""
    <div class="metric-card orange">
        <div class="metric-label">Cameras Online</div>
        <div class="metric-value">{stats['cameras_online']} / {stats['cameras_total']}</div>
    </div>
    """, unsafe_allow_html=True)

with col4:
    st.markdown(f"""
    <div class="metric-card red">
        <div class="metric-label">Pending Reviews</div>
        <div class="metric-value">{stats['pending_reviews']}</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("---")

col_left, col_right = st.columns([3, 2])

with col_left:
    st.markdown("### 📊 Today's Activity")

    sub1, sub2, sub3 = st.columns(3)
    with sub1:
        st.metric("Recognitions", stats['recognitions_today'])
    with sub2:
        st.metric("Gates Opened", stats['gates_opened_today'])
    with sub3:
        st.metric("Vehicle Passes", stats['vehicle_passes'])

    st.markdown("### 🔍 Recent Recognition Events")
    events = db.get_recognition_events(limit=10)
    if events:
        for ev in events:
            plate = ev.get("final_plate") or ev.get("ocr_text") or "—"
            cam = ev.get("camera_id", "—")
            ts = ev.get("timestamp", "—")
            conf = ev.get("ocr_confidence", 0) or 0
            reviewed = "✅" if ev.get("admin_reviewed") else "⏳"
            gate = "🔓" if ev.get("gate_opened") else ""

            st.markdown(f"""
            <div class="event-card">
                <span class="plate-number">{plate}</span>
                <span style="margin-left: 1rem; color: #7f8c8d;">📷 {cam} | {ts} | Conf: {conf:.0%} {reviewed} {gate}</span>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("No recognition events yet. Events will appear when cameras start processing.")

with col_right:
    st.markdown("### 📷 Camera Status")
    cameras = db.get_cameras()
    if cameras:
        for cam in cameras:
            status_class = {
                "online": "status-online",
                "offline": "status-offline",
                "error": "status-error",
            }.get(cam["status"], "status-offline")
            status_icon = {"online": "🟢", "offline": "🔴", "error": "🟡"}.get(cam["status"], "⚪")
            st.markdown(f"""
            <div class="event-card">
                {status_icon} <strong>{cam['name']}</strong>
                <span class="{status_class}"> ({cam['status']})</span><br>
                <small style="color: #7f8c8d;">ID: {cam['camera_id']} | Last: {cam.get('last_frame_at', 'Never')}</small>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("No cameras configured. Add cameras in the Settings page.")

    st.markdown("### 🧠 Training Status")
    training_samples = stats.get("training_samples", {})
    for stage, count in training_samples.items():
        min_req = 50
        progress = min(count / min_req, 1.0) if min_req > 0 else 0
        color = "#27AE60" if count >= min_req else "#F39C12" if count > min_req * 0.5 else "#E74C3C"
        st.markdown(f"""
        <div style="margin-bottom: 0.5rem;">
            <span style="font-weight: 600; color: #2C3E50; text-transform: capitalize;">{stage}</span>
            <span style="float: right; color: {color}; font-weight: 600;">{count}/{min_req}</span>
        </div>
        """, unsafe_allow_html=True)
        st.progress(progress)

st.markdown("---")

st.markdown("### 🚪 Recent Gate Events")
gate_events = db.get_gate_events(limit=5)
if gate_events:
    for ge in gate_events:
        success_icon = "✅" if ge.get("success") else "❌"
        st.markdown(f"""
        <div class="event-card">
            {success_icon} <span class="plate-number">{ge.get('plate_number', '—')}</span>
            <span style="margin-left: 1rem; color: #7f8c8d;">
                📷 {ge.get('camera_id', '—')} | {ge.get('timestamp', '—')} | {ge.get('action', '—')}
            </span>
        </div>
        """, unsafe_allow_html=True)
else:
    st.info("No gate events yet.")


def show_live_recognition():
    """Show live recognition page."""
    st.title("📹 Live Recognition")
    st.info("Live recognition interface - Coming soon")
    st.markdown("""
    This page will show:
    - Real-time camera feeds
    - Live recognition results
    - Camera configuration
    - Recognition pipeline controls
    """)


def show_user_management():
    """Show user management page."""
    st.title("👥 User Management")
    st.info("User management interface - Coming soon")
    st.markdown("""
    This page will show:
    - User registration and editing
    - Pass management
    - User permissions
    - Access logs
    """)


def show_training():
    """Show training page."""
    st.title("🎯 Training")
    st.info("Model training interface - Coming soon")
    st.markdown("""
    This page will show:
    - Training data management
    - Model training controls
    - Training progress
    - Model performance metrics
    """)


def show_analytics():
    """Show analytics page."""
    show_batch_analytics()


def show_settings():
    """Show settings page."""
    st.title("⚙️ Settings")
    st.info("System settings - Coming soon")
    st.markdown("""
    This page will show:
    - Camera configuration
    - System preferences
    - Integration settings
    - Maintenance tools
    """)


if __name__ == "__main__":
    main()
