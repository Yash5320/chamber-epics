# 🎛️ Vacuum Chamber EPICS Control & Monitoring System

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![EPICS](https://img.shields.io/badge/EPICS-Caproto%20v1.3.0-orange.svg)](https://caproto.github.io/caproto/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.66-FF4B4B.svg)](https://streamlit.io/)
[![Plotly](https://img.shields.io/badge/Plotly-7.1-3F4F75.svg)](https://plotly.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A distributed SCADA / Operator Interface (OPI) and hardware simulation stack built for high-vacuum thermal chambers. This system implements the **EPICS (Experimental Physics and Industrial Control System)** Channel Access protocol using **Caproto**, a discrete-time thermodynamic simulation, an autonomous closed-loop PID controller, a high-priority safety interlock daemon, and an interactive real-time dashboard built with **Streamlit** and **Plotly**.

---

## 📑 Table of Contents

- [System Architecture](#-system-architecture)
- [EPICS Process Variable (PV) Catalog](#-epics-process-variable-pv-catalog)
- [Core Components](#-core-components)
  - [1. Soft IOC & Chamber Physics Simulation (`ioc_server.py`)](#1-soft-ioc--chamber-physics-simulation-ioc_serverpy)
  - [2. Closed-Loop PID Temperature Controller (`pid_controller.py`)](#2-closed-loop-pid-temperature-controller-pid_controllerpy)
  - [3. Safety Interlock Daemon (`interlock_daemon.py`)](#3-safety-interlock-daemon-interlock_daemonpy)
  - [4. Operator Dashboard & Supervisor (`dashboard.py`)](#4-operator-dashboard--supervisor-dashboardpy)
- [Installation & Local Setup](#-installation--local-setup)
- [Running the System](#-running-the-system)
  - [Option A: Integrated Launcher (Recommended)](#option-a-integrated-launcher-recommended)
  - [Option B: Distributed / Multi-Terminal Mode](#option-b-distributed--multi-terminal-mode)
- [Safety Interlocks & Trip Logic](#-safety-interlocks--trip-logic)
- [Deployment Considerations](#-deployment-considerations)
- [License](#-license)

---

## 🏛️ System Architecture

The application is structured into decoupled, event-driven components communicating over standard **EPICS Channel Access (CA)** over TCP/UDP (`ports 5064 / 5065`):

```mermaid
flowchart TD
    subgraph EPICS["EPICS Network Layer (Channel Access / Loopback)"]
        IOC["ioc_server.py<br/>Caproto Soft IOC<br/>Thermodynamic & Vacuum Model"]
    end

    subgraph DAEMONS["Control & Protection Daemons"]
        PID["pid_controller.py<br/>PID Loop (5 Hz)<br/>Actuates CHILLER:VALVE"]
        INT["interlock_daemon.py<br/>Safety Guard (10 Hz)<br/>Failsafe Cutoff"]
    end

    subgraph HMI["Operator Interface"]
        UI["dashboard.py<br/>Streamlit & Plotly HMI<br/>Telemetry & Overrides"]
    end

    IOC -->|CAVITY:TEMP| PID
    PID -->|CHILLER:VALVE| IOC

    IOC -->|TEMP & VACUUM| INT
    INT -->|TRIP CUTOFF| IOC

    IOC -->|CA Read 1.0s| UI
    UI -->|Manual Overrides| IOC

    UI -.->|Subprocess Spawn| IOC
    UI -.->|Subprocess Spawn| PID
    UI -.->|Subprocess Spawn| INT
```

---

## 📋 EPICS Process Variable (PV) Catalog

| PV Name | Type | Access | Scan Rate | Description | Normal Range |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `CAVITY:TEMP` | `FLOAT` | Read-Only | 0.2 s (5 Hz) | Simulated chamber core temperature | 20.0 – 40.0 °C |
| `CAVITY:VACUUM` | `FLOAT` | Read-Only | 0.5 s (2 Hz) | High-vacuum ionization gauge reading | $1.0\times10^{-7}$ Torr |
| `CHILLER:VALVE` | `FLOAT` | Read / Write | Async | Coolant bypass valve opening percentage | 0.0 – 100.0 % |
| `HEATER:ENABLE` | `INT` | Read / Write | Async | Chamber resistive heating element state | `0` (OFF) or `1` (ON) |
| `INTERLOCK:STATUS` | `STRING` | Read / Write | Async | Hardware interlock register status | `"OK"` or `"TRIP: <reason>"` |

---

## ⚙️ Core Components

### 1. Soft IOC & Chamber Physics Simulation (`ioc_server.py`)
Implements an EPICS Input/Output Controller using `caproto.server.PVGroup`. It simulates non-linear chamber thermodynamics and vacuum fluctuations:

- **Thermal Model:**
  $$\Delta T = \left( \dot{Q}_{\text{heater}} - \dot{Q}_{\text{chiller}} - \dot{Q}_{\text{ambient}} \right) \cdot \Delta t + \mathcal{N}(0, \sigma^2)$$
  - **Heating:** $\dot{Q}_{\text{heater}} = 2.5\text{ °C/s}$ when `HEATER:ENABLE = 1`.
  - **Chiller Dissipation:** $\dot{Q}_{\text{chiller}} = \left(\frac{\text{Valve}}{100}\right) \cdot (T - 15.0) \cdot 0.15$.
  - **Ambient Heat Loss:** $\dot{Q}_{\text{ambient}} = (T - 22.0) \cdot 0.02$.
  - **Process Noise:** Gaussian noise with standard deviation $\sigma = 0.02\text{ °C}$.
- **Vacuum Gauge Simulation:** Nominal ultra-high vacuum level at $1.0 \times 10^{-7}\text{ Torr}$ with randomized micro-fluctuations.

### 2. Closed-Loop PID Temperature Controller (`pid_controller.py`)
Maintains `CAVITY:TEMP` at a steady **30.0 °C setpoint** by regulating `CHILLER:VALVE`:
- **Gains:** $K_p = 12.0$, $K_i = 0.8$, $K_d = 2.5$
- **Cycle Time:** $200\text{ ms}$ (5 Hz)
- **Actuation Range:** $0.0\text{ \%}$ (closed) to $100.0\text{ \%}$ (full bypass coolant flow).
- **Anti-Windup:** Integral accumulation and derivative calculations are executed continuously against a dynamic $\Delta t$.

### 3. Safety Interlock Daemon (`interlock_daemon.py`)
Hardware protection loop evaluating system telemetry every $100\text{ ms}$ (10 Hz). If trip criteria are met:
1. `HEATER:ENABLE` is immediately forced to `0`.
2. `INTERLOCK:STATUS` is transitioned into an active latched `TRIP: <reason>` state.
3. The system ignores heating requests until an operator explicitly issues an interlock reset while telemetry is within safe limits.

### 4. Operator Dashboard & Supervisor (`dashboard.py`)
A modern Streamlit web interface functioning as an accelerator control room OPI:
- **Supervisor Engine:** Automatically bootstraps the background IOC, PID, and Interlock daemons on launch using `@st.cache_resource`.
- **Live Visualizations:**
  - Dynamic Plotly arc gauges for Cavity Temperature and Chiller Valve position with colored warning/trip zones.
  - Telemetry metric panels for high-vacuum readings, heater states, and interlock health.
  - 60-second rolling trend plot displaying real-time temperature, setpoint (30 °C), and critical safety threshold (40 °C).
- **Control Interface:** Manual interlock reset trigger, heater toggle switch, and manual valve position override sliders.

---

## 🛠️ Installation & Local Setup

### Prerequisites
- **Python 3.10+** (tested through Python 3.12)
- Operating System: Linux, macOS, or Windows (WSL recommended)

### Setup Virtual Environment

```bash
# Clone the repository
git clone https://github.com/your-username/vacuum-chamber-epics.git
cd vacuum-chamber-epics

# Create and activate a virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install required dependencies
pip install -r requirements.txt
```

---

## 🚀 Running the System

### Option A: Integrated Launcher (Recommended)
`dashboard.py` contains a self-contained supervisor. Launching Streamlit starts the IOC server, the PID loop, and the interlock daemon automatically in the background:

```bash
streamlit run dashboard.py
```
Open your browser at `http://localhost:8501`.

---

### Option B: Distributed / Multi-Terminal Mode
If running across separate machines or debugging individual subsystems, comment out `start_epics_stack()` in `dashboard.py` and run each process in its own shell:

```bash
# Terminal 1: Run the Soft IOC Server
python ioc_server.py

# Terminal 2: Run the Interlock Daemon
python interlock_daemon.py

# Terminal 3: Run the PID Controller
python pid_controller.py

# Terminal 4: Launch the Operator Interface
streamlit run dashboard.py
```

---

## 🚨 Safety Interlocks & Trip Logic

The Interlock Daemon triggers under the following conditions:

| Parameter | Safety Threshold | Action Taken |
| :--- | :--- | :--- |
| **Over-Temperature** | `CAVITY:TEMP > 40.0 °C` | Immediate Heater Cutoff (`HEATER:ENABLE = 0`), trip latched |
| **Loss of Vacuum** | `CAVITY:VACUUM > 1.0e-5 Torr` | Immediate Heater Cutoff (`HEATER:ENABLE = 0`), trip latched |

### Clearing an Interlock Trip
1. Allow chamber temperature to drop below **40.0 °C** (chiller will actively cool).
2. Ensure vacuum levels have normalized below **$1.0 \times 10^{-5}\text{ Torr}$**.
3. Click the **Reset Interlock** button on the Operator Dashboard sidebar.
4. Manually re-enable the heater once status returns to `Interlock System: HEALTHY`.

---

## 🌐 Deployment Considerations

### Running on Streamlit Community Cloud
- Caproto binds to loopback interfaces (`127.0.0.1` / broadcast) within the same container. When hosted on Streamlit Cloud, all daemons spawned by `start_epics_stack()` run inside that single Linux container.
- Note that Streamlit Cloud will put inactive apps into sleep mode. When woken up, `@st.cache_resource` will cleanly re-initialize the EPICS stack.

### Running on Real Hardware / Production Subnets
To connect this interface to physical EPICS IOCs or hardware controllers:
1. Remove `start_epics_stack()` from `dashboard.py`.
2. Configure EPICS environment variables on the host:
   ```bash
   export EPICS_CA_ADDR_LIST="192.168.1.255"  # Your subnet broadcast
   export EPICS_CA_AUTO_ADDR_LIST="NO"
   ```
3. Update the PV names to match your production facility naming conventions (e.g., `VAC:CHAMBER:TC1`, `LLRF:CAV:TEMP`).

---

## 📄 License

This project is open-source under the [MIT License](LICENSE).
```
