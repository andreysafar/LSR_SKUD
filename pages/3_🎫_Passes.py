import streamlit as st
from datetime import datetime, timedelta
from db.database import get_db

st.set_page_config(page_title="Passes", page_icon="🎫", layout="wide")

st.markdown("""
<style>
    .pass-card {
        background: white;
        border-radius: 12px;
        padding: 1.2rem;
        box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        margin-bottom: 1rem;
        border-left: 4px solid;
    }
    .pass-vehicle { border-left-color: #3498DB; }
    .pass-access { border-left-color: #27AE60; }
    .pass-expired { border-left-color: #95a5a6; opacity: 0.6; }
</style>
""", unsafe_allow_html=True)

db = get_db()

st.title("🎫 Pass Management")

st.subheader("Create Vehicle Pass")
with st.form("create_vehicle_pass"):
    col1, col2, col3 = st.columns(3)
    with col1:
        plate = st.text_input("License Plate", placeholder="А123ВС77")
    with col2:
        duration = st.selectbox("Duration", [
            ("Until end of day", "day_end"),
            ("3 hours", "3hours"),
            ("24 hours", "24hours"),
            ("1 week", "week"),
        ], format_func=lambda x: x[0])
    with col3:
        user_id_input = st.number_input("User ID (Telegram)", min_value=0, step=1)

    create_submitted = st.form_submit_button("Create Pass", type="primary")
    if create_submitted and plate and user_id_input:
        from bot.handlers.passes import normalize_plate_input
        plate_clean = normalize_plate_input(plate)
        now = datetime.now()
        dur = duration[1]
        if dur == "day_end":
            vf = now.strftime("%Y-%m-%d %H:%M:%S")
            vt = now.replace(hour=23, minute=59, second=59).strftime("%Y-%m-%d %H:%M:%S")
        elif dur == "3hours":
            vf = now.strftime("%Y-%m-%d %H:%M:%S")
            vt = (now + timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S")
        elif dur == "24hours":
            vf = now.strftime("%Y-%m-%d %H:%M:%S")
            vt = (now + timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
        else:
            vf = now.strftime("%Y-%m-%d %H:%M:%S")
            vt = (now + timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")

        db.create_pass(
            user_id=int(user_id_input),
            pass_type="vehicle",
            plate_number=plate_clean,
            valid_from=vf,
            valid_to=vt,
        )
        st.success(f"Vehicle pass created for {plate_clean}")
        st.rerun()

st.markdown("---")
st.subheader("Active Passes")

passes = db.get_active_passes()
if not passes:
    st.info("No active passes.")
else:
    for p in passes:
        ptype = "vehicle" if p["pass_type"] == "vehicle" else "access"
        card_class = f"pass-{ptype}"
        icon = "🚗" if ptype == "vehicle" else "🔑"
        plate_info = f"<strong>{p.get('plate_number', '')}</strong>" if p.get("plate_number") else ""
        group_info = p.get("access_group_name", "") if p.get("access_group_name") else ""

        with st.container():
            col1, col2, col3, col4 = st.columns([1, 3, 2, 1])
            with col1:
                st.markdown(f"### {icon}")
                st.caption(f"#{p['id']}")
            with col2:
                st.markdown(f"**{p.get('plate_number', '')} {group_info}**")
                st.caption(f"Type: {p['pass_type']} | User: {p['user_id']}")
            with col3:
                st.caption(f"From: {p['valid_from']}")
                st.caption(f"To: {p['valid_to']}")
            with col4:
                if st.button("Cancel", key=f"cancel_{p['id']}"):
                    db.deactivate_pass(p["id"])
                    st.rerun()

st.markdown("---")
st.subheader("Pass Lookup")

lookup_plate = st.text_input("Check plate number", placeholder="А123ВС77")
if lookup_plate:
    from bot.handlers.passes import normalize_plate_input
    plate_clean = normalize_plate_input(lookup_plate)
    found = db.find_active_pass_by_plate(plate_clean)
    if found:
        st.success(f"Active pass found: #{found['id']} — Valid until {found['valid_to']}")
    else:
        st.warning(f"No active pass found for {plate_clean}")
