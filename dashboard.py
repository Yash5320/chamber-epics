import streamlit as st
import plotly.graph_objects as go
from caproto.sync.client import read, write
import pandas as pd
import time
from datetime import datetime
from collections import deque
import subprocess
import sys
import atexit

st.set_page_config(page_title="Chamber Operator Dashboard", layout="wide")

class EpicsStackManager:
    """Manages background EPICS processes and allows safely toggling the PID controller."""
    def __init__(self):
        self.ioc_proc = subprocess.Popen([sys.executable, "ioc_server.py"])
        time.sleep(2.0)  # Wait for IOC socket to bind
        self.pid_proc = subprocess.Popen([sys.executable, "pid_controller.py"])
        self.interlock_proc = subprocess.Popen([sys.executable, "interlock_daemon.py"])

    def is_pid_running(self):
        return self.pid_proc is not None and self.pid_proc.poll() is None

    def stop_pid(self):
        if self.pid_proc is not None:
            if self.pid_proc.poll() is None:
                self.pid_proc.terminate()
                try:
                    self.pid_proc.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    self.pid_proc.kill()
                    self.pid_proc.wait()
            self.pid_proc = None

    def start_pid(self):
        if not self.is_pid_running():
            self.pid_proc = subprocess.Popen([sys.executable, "pid_controller.py"])

    def cleanup(self):
        for proc in [self.pid_proc, self.interlock_proc, self.ioc_proc]:
            if proc is not None and proc.poll() is None:
                try:
                    proc.terminate()
                except Exception:
                    pass

# @st.cache_resource guarantees this executes only ONCE on boot
@st.cache_resource
def get_epics_stack():
    mgr = EpicsStackManager()
    atexit.register(mgr.cleanup)
    return mgr

stack = get_epics_stack()

# Synchronize session state with actual process state on initial load
if "pid_enabled" not in st.session_state:
    st.session_state.pid_enabled = stack.is_pid_running()

# Callback triggered ONLY by user interaction (not by periodic reruns)
def on_pid_toggle():
    if st.session_state.pid_enabled:
        stack.start_pid()
    else:
        stack.stop_pid()

pid_running = stack.is_pid_running()

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

    if st.button("Reset Interlock", width="stretch"):
        try:
            write('INTERLOCK:STATUS', 'OK')
            st.toast("Interlock cleared! Status set to OK.")
        except Exception as e:
            st.error(f"Write failed: {e}")

    st.divider()

    st.subheader("🔥 Heater Control")
    heater_toggle = st.toggle("Heater Power (HEATER:ENABLE)", value=(current_heater == 1.0))
    if st.button("Apply Heater State", width="stretch"):
        try:
            write('HEATER:ENABLE', 1 if heater_toggle else 0)
            st.toast(f"Heater set to: {1 if heater_toggle else 0}")
        except Exception as e:
            st.error(f"Write failed: {e}")

    st.divider()

    st.subheader("🤖 PID & Chiller Valve")

    # Stable toggle linked to session state and callback
    st.toggle(
        "PID Controller (Auto Mode)",
        key="pid_enabled",
        on_change=on_pid_toggle,
        help="Turn off to simulate PID controller failure and unlock manual valve control."
    )

    if pid_running:
        st.info("🔒 PID active: manual valve control is locked.")
        valve_display_value = float(current_valve if current_valve is not None else 0.0)
        st.session_state["manual_valve_pos"] = valve_display_value
    else:
        st.warning("⚠️ PID offline: manual valve override is UNLOCKED.")
        if "manual_valve_pos" not in st.session_state:
            st.session_state["manual_valve_pos"] = float(current_valve if current_valve is not None else 0.0)
        valve_display_value = st.session_state["manual_valve_pos"]

    # Valve slider is active ONLY when PID is stopped
    new_valve = st.slider(
        "Chiller Valve (%)",
        min_value=0.0,
        max_value=100.0,
        value=valve_display_value,
        step=0.5,
        disabled=pid_running,
        help="Only adjustable when PID Controller is switched off."
    )

    if not pid_running:
        st.session_state["manual_valve_pos"] = new_valve

    if st.button("Set Chiller Valve", disabled=pid_running, width="stretch"):
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
    st.plotly_chart(fig_temp, width="stretch")

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
    st.plotly_chart(fig_valve, width="stretch")

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
    st.metric(
        label="PID Controller",
        value="ACTIVE" if pid_running else "STOPPED",
        delta="ONLINE" if pid_running else "FAILURE SIM",
        delta_color="normal" if pid_running else "inverse"
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
    st.plotly_chart(fig_line, width="stretch")
else:
    st.info("Accumulating telemetry data...")

time.sleep(1.0)
st.rerun()