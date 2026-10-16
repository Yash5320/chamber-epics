import streamlit as st
import plotly.graph_objects as go
from caproto.sync.client import read, write
import pandas as pd
import time
from datetime import datetime
from collections import deque

st.set_page_config(page_title="Chamber Operator Dashboard", layout="wide")
import subprocess
import sys

# @st.cache_resource guarantees this executes only ONCE on boot, 
# not on every 1-second UI refresh
@st.cache_resource
def start_epics_stack():
    ioc_proc = subprocess.Popen([sys.executable, "ioc_server.py"])
    time.sleep(2.0)  # Wait for IOC socket to bind
    pid_proc = subprocess.Popen([sys.executable, "pid_controller.py"])
    interlock_proc = subprocess.Popen([sys.executable, "interlock_daemon.py"])
    return ioc_proc, pid_proc, interlock_proc

# Boot up the full EPICS machine
start_epics_stack()

if "history" not in st.session_state:
    st.session_state.history = deque(maxlen=60)

def get_pv_float(pv_name):
    try:
        return float(read(pv_name, timeout=0.5).data[0])
    except Exception:
        return None

def get_pv_str(pv_name):
    try:
        data = read(pv_name, timeout=0.5).data
        return bytes(data).decode('utf-8').strip('\x00 ')
    except Exception:
        return "DISCONNECTED"

current_temp = get_pv_float('CAVITY:TEMP')
current_vac = get_pv_float('CAVITY:VACUUM')
current_valve = get_pv_float('CHILLER:VALVE')
current_heater = get_pv_float('HEATER:ENABLE')
current_interlock = get_pv_str('INTERLOCK:STATUS')

now = datetime.now()
if current_temp is not None:
    st.session_state.history.append({"time": now, "temp": current_temp})

st.title("🎛️ Chamber Operator Dashboard")

with st.sidebar:
    st.header("⚙️ Manual Overrides")

    is_tripped = current_interlock != "OK"
    if is_tripped:
        st.error(f"⚠️ {current_interlock}")
    else:
        st.success("Interlock System: HEALTHY")

    if st.button("Reset Interlock", use_container_width=True):
        try:
            write('INTERLOCK:STATUS', 'OK')
            st.toast("Interlock cleared! Status set to OK.")
        except Exception as e:
            st.error(f"Write failed: {e}")

    st.divider()

    heater_toggle = st.toggle("Heater Power (HEATER:ENABLE)", value=(current_heater == 1.0))
    if st.button("Apply Heater State", use_container_width=True):
        try:
            write('HEATER:ENABLE', 1 if heater_toggle else 0)
            st.toast(f"Heater set to: {1 if heater_toggle else 0}")
        except Exception as e:
            st.error(f"Write failed: {e}")

    new_valve = st.slider("Chiller Valve (%)", 0.0, 100.0, float(current_valve or 0.0), 0.5)
    if st.button("Set Chiller Valve", use_container_width=True):
        try:
            write('CHILLER:VALVE', float(new_valve))
            st.toast(f"Valve set to: {new_valve}%")
        except Exception as e:
            st.error(f"Write failed: {e}")

col1, col2, col3, col4 = st.columns(4)

with col1:
    fig_temp = go.Figure(go.Indicator(
        mode="gauge+number",
        value=current_temp if current_temp is not None else 0.0,
        title={'text': "Cavity Temp (°C)"},
        gauge={
            'axis': {'range': [15, 45]},
            'bar': {'color': "#1f77b4"},
            'steps': [
                {'range': [15, 28], 'color': "#e8f4f8"},
                {'range': [28, 32], 'color': "#d4edda"},
                {'range': [32, 40], 'color': "#fff3cd"},
                {'range': [40, 45], 'color': "#f8d7da"},
            ],
            'threshold': {'line': {'color': "red", 'width': 4}, 'thickness': 0.75, 'value': 40.0}
        }
    ))
    fig_temp.update_layout(height=240, margin=dict(l=20, r=20, t=30, b=10))
    st.plotly_chart(fig_temp, use_container_width=True)

with col2:
    fig_valve = go.Figure(go.Indicator(
        mode="gauge+number",
        value=current_valve if current_valve is not None else 0.0,
        title={'text': "Chiller Valve (%)"},
        gauge={
            'axis': {'range': [0, 100]},
            'bar': {'color': "#2ca02c"},
            'steps': [
                {'range': [0, 50], 'color': "#f0f0f0"},
                {'range': [50, 100], 'color': "#e0e0e0"}
            ]
        }
    ))
    fig_valve.update_layout(height=240, margin=dict(l=20, r=20, t=30, b=10))
    st.plotly_chart(fig_valve, use_container_width=True)

with col3:
    st.metric(
        label="Cavity Vacuum",
        value=f"{current_vac:.2e} Torr" if current_vac is not None else "N/A"
    )
    st.metric(
        label="Heater State",
        value="ENABLED (1)" if current_heater == 1.0 else "DISABLED (0)"
    )

with col4:
    st.metric(
        label="Interlock Status",
        value=current_interlock,
        delta="NORMAL" if current_interlock == "OK" else "TRIPPED",
        delta_color="normal" if current_interlock == "OK" else "inverse"
    )

st.subheader("📈 Real-Time Temperature History (Last 60 Seconds)")

if len(st.session_state.history) > 1:
    df = pd.DataFrame(st.session_state.history)
    fig_line = go.Figure()

    fig_line.add_trace(go.Scatter(
        x=df['time'], y=df['temp'],
        mode='lines+markers',
        name='CAVITY:TEMP',
        line=dict(color='#1f77b4', width=2)
    ))

    fig_line.add_hline(y=30.0, line_dash="dash", line_color="green", annotation_text="Setpoint (30°C)")
    fig_line.add_hline(y=40.0, line_dash="dot", line_color="red", annotation_text="Trip Limit (40°C)")

    fig_line.update_layout(
        xaxis_title="Time",
        yaxis_title="Temperature (°C)",
        yaxis=dict(range=[20, 45]),
        height=350,
        margin=dict(l=20, r=20, t=20, b=20)
    )
    st.plotly_chart(fig_line, use_container_width=True)
else:
    st.info("Accumulating telemetry data...")

time.sleep(1.0)
st.rerun()
