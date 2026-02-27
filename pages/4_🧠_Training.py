import streamlit as st
import os
import json
from db.database import get_db

st.set_page_config(page_title="Training", page_icon="🧠", layout="wide")

st.markdown("""
<style>
    .training-card {
        background: white;
        border-radius: 12px;
        padding: 1.2rem;
        box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        margin-bottom: 1rem;
    }
    .stage-header {
        font-size: 1.1rem;
        font-weight: 600;
        color: #2C3E50;
        text-transform: capitalize;
    }
    .ready-badge {
        display: inline-block;
        padding: 0.2rem 0.8rem;
        border-radius: 12px;
        font-size: 0.8rem;
        font-weight: 600;
    }
    .ready-yes { background: #d5f5e3; color: #27AE60; }
    .ready-no { background: #fef9e7; color: #F39C12; }
</style>
""", unsafe_allow_html=True)

db = get_db()

st.title("🧠 Training Management")
st.markdown("Monitor and manage the three-stage recognition training pipeline.")

st.markdown("---")
st.subheader("📊 Training Samples by Camera")

cameras = db.get_cameras()
min_samples = 50

if not cameras:
    st.info("No cameras configured. Add cameras first to collect training data.")
else:
    for cam in cameras:
        cam_id = cam["camera_id"]
        st.markdown(f"#### 📷 {cam['name']} ({cam_id})")

        cols = st.columns(3)
        for i, stage in enumerate(["vehicle", "plate", "ocr"]):
            with cols[i]:
                unused = db.get_training_samples_count(cam_id, stage, unused_only=True)
                total = db.get_training_samples_count(cam_id, stage, unused_only=False)
                ready = unused >= min_samples
                badge_class = "ready-yes" if ready else "ready-no"
                badge_text = "READY" if ready else f"{min_samples - unused} more needed"

                st.markdown(f"""
                <div class="training-card">
                    <div class="stage-header">{stage}</div>
                    <div style="font-size: 2rem; font-weight: 700; color: #2C3E50;">{unused}</div>
                    <div style="color: #7f8c8d; font-size: 0.85rem;">unused samples (total: {total})</div>
                    <div class="ready-badge {badge_class}" style="margin-top: 0.5rem;">{badge_text}</div>
                </div>
                """, unsafe_allow_html=True)

                progress = min(unused / min_samples, 1.0) if min_samples > 0 else 0
                st.progress(progress)

        st.markdown("---")

st.subheader("📜 Training Sessions")

sessions = db.get_training_sessions(limit=20)
if not sessions:
    st.info("No training sessions yet. Sessions are created when enough samples are collected.")
else:
    for s in sessions:
        status_icon = {
            "pending": "⏳",
            "running": "🔄",
            "completed": "✅",
            "failed": "❌",
        }.get(s.get("status", ""), "❓")

        col1, col2, col3, col4 = st.columns([1, 2, 2, 1])
        with col1:
            st.markdown(f"### {status_icon}")
        with col2:
            st.markdown(f"**Camera:** {s['camera_id']}")
            st.markdown(f"**Stage:** {s['stage']}")
        with col3:
            st.caption(f"Samples: {s.get('samples_count', 0)}")
            st.caption(f"Started: {s.get('started_at', '—')}")
            if s.get("completed_at"):
                st.caption(f"Completed: {s['completed_at']}")
        with col4:
            st.markdown(f"**{s.get('status', '—').upper()}**")
            if s.get("weights_path"):
                st.caption(f"Weights: {s['weights_path']}")

st.markdown("---")
st.subheader("🐳 Training Docker Setup")
st.markdown("""
The training pipeline runs on a separate GPU server using Docker Compose.
When enough labeled samples are collected per camera, the system exports 
training data and creates a training session.

**To run training on the GPU server:**
```bash
cd training
docker-compose up
```

This will:
1. Build the training container with CUDA support
2. Mount the training data and model directories
3. Train per-camera weights for each stage
4. Save improved weights back to the models directory
""")

training_dir = "training"
dc_path = os.path.join(training_dir, "docker-compose.yml")
if os.path.exists(dc_path):
    with open(dc_path) as f:
        st.code(f.read(), language="yaml")

st.subheader("📂 Exported Training Data")
export_dir = "data/training/export"
if os.path.exists(export_dir):
    for cam_dir in sorted(os.listdir(export_dir)):
        cam_path = os.path.join(export_dir, cam_dir)
        if os.path.isdir(cam_path):
            st.markdown(f"**{cam_dir}:**")
            for stage_dir in sorted(os.listdir(cam_path)):
                manifest_path = os.path.join(cam_path, stage_dir, "manifest.json")
                if os.path.exists(manifest_path):
                    with open(manifest_path) as f:
                        manifest = json.load(f)
                    st.caption(
                        f"  {stage_dir}: {manifest.get('samples_count', 0)} samples "
                        f"(exported: {manifest.get('exported_at', '—')})"
                    )
else:
    st.info("No exported training data yet.")
