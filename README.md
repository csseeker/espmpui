# `espmui`: Modern Reactive Web Dashboard for MicroPython

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![MicroPython](https://img.shields.io/badge/MicroPython-v1.20%2B-green.svg)](https://micropython.org/)
[![Zero External Dependencies](https://img.shields.io/badge/Dependencies-Zero-brightgreen.svg)]()
[![Bundle Size](https://img.shields.io/badge/Bundle%20Size-~13.4%20KB-blueviolet.svg)]()
[![Tests](https://img.shields.io/badge/Tests-62%20Passing-success.svg)]()

`espmui` is a lightweight, full-featured web dashboard and device management library for **MicroPython** microcontrollers (ESP32, ESP32-S2/S3, ESP32-C3/C6, and Raspberry Pi Pico W).

It provides a declarative Python API to build reactive on-device controls, live telemetry meters, Wi-Fi provisioning captive portals, persistent configuration forms, and drag-and-drop web OTA updaters — paired with a compact, pre-gzipped single-page frontend (~13.4 KB) served directly from flash and synchronized over WebSockets with **zero external dependencies**.

<p align="center">
  <img src="docs/images/dashboard_sensors.png" alt="espmui Sensors Dashboard" width="100%">
</p>

<details>
  <summary><b>📷 More Screenshots (Memory & Diagnostics tabs)</b></summary>
  <br>

  #### Memory & GC Tracking
  <img src="docs/images/dashboard_memory.png" alt="Memory & Heap Telemetry" width="100%">

  #### Live Telemetry & Terminal Stream
  <img src="docs/images/dashboard_diagnostics.png" alt="Diagnostics & Live Stream" width="100%">
</details>

---

## ⚡ Quickstart (15 Lines of Python)

```python
import espmui
from machine import Pin

led = Pin(4, Pin.OUT, value=0)

app = espmui.App(title="S3 IoT Dashboard", theme="dark")
tab = app.tab("Controls", icon="sliders")

tab.switch("Main LED", value=False, on_change=lambda w, val: led.value(1 if val else 0))
tab.slider("Speed", min=0, max=100, step=5, value=25, unit="%", on_change=lambda w, val: print("Speed:", val))
tab.button("Pulse", accent="danger", on_click=lambda w: print("Pulse clicked!"))

# Turnkey System Health diagnostics & Web OTA updater
app.enable_diagnostics()
app.enable_ota()

if __name__ == "__main__":
    app.run(port=80)
```

---

## ✨ Key Architectural Features

* **Zero External Runtime Dependencies**: Built entirely with standard MicroPython `uasyncio` and built-in socket modules.
* **Compact Pre-Gzipped Embedded Frontend**: Minified and compressed single-page application (~13.4 KB) with zero external CDN dependencies, mobile-responsive vertical/horizontal navigation, and dark glassmorphic styling.
* **Two-Way Reactive Synchronization**:
  * Python variable assignments broadcast small JSON diffs (~35 bytes) over WebSockets to all connected clients.
  * User inputs (buttons, switches, sliders, forms) invoke Python callbacks directly.
* **Fault-Isolated Execution**: Exceptions inside user callbacks are safely trapped and reported to the serial console and web interface without crashing the `uasyncio` event loop.
* **Backpressure Protection**: Bounded outbound queues with a latest-state-wins dropping policy prevent heap starvation when network clients stall.
* **📡 Wi-Fi Provisioner & Captive Portal (Milestone 1)**:
  * Zero-friction mobile onboarding via SoftAP and RFC 1035 UDP DNS interception (port 53).
  * Traps captive probe URLs (`/generate_204`, `/hotspot-detect.html`, `/ncsi.txt`) with instant 302 redirects.
  * Mobile-first frontend card with background network scanning, visual RSSI signal bars, and safe connection verification before AP teardown.
* **💾 Persistent Parameter & Config Store (Milestone 2)**:
  * Schema-driven HTML form generator (`ConfigForm`) with type enforcement, bounds validation, and dropdown selects.
  * Atomic write-to-temp and inode rename pattern protecting `/config.json` against 0-byte truncation on power cuts.
  * Direct Python attribute binding (`config.param`) and reactive sync/async change hooks (`@config.on_change`).
* **📊 Live System Diagnostics & Telemetry (Milestone 3)**:
  * Real-time tracking of `gc.mem_free()` and `gc.mem_alloc()` heap status, LittleFS/FAT storage usage, Wi-Fi RSSI (dBm), and rollover-safe uptime (`time.ticks_diff()`).
  * Turnkey "System Health" tab with visual progress bars, interactive Garbage Collector trigger (`gc.collect()`), and safe remote soft restart (`machine.reset()`).
* **🚀 Web-Based Drag-and-Drop OTA Updater (Milestone 4)**:
  * Streaming multipart parser using a 512-byte sliding window (<4 KB peak RAM) preventing OOM crashes during 1–3 MB binary uploads.
  * Direct inactive flash partition writing (`esp32.Partition.get_next_update()`) with incremental SHA-256 verification and atomic boot switching.
  * Embedded frontend dialog with drag-and-drop dropzone, live upload percentage progress bar, amber risk banner, and 10-second post-reboot reconnect countdown.
* **🧰 IoT Component Suite**:
  * 📑 **Multi-Tab Layout**: Switchable vertical/horizontal navigation tabs.
  * 📸 **Camera Viewfinder**: Live MJPEG streaming and snapshot capture for OV2640/OV3660 sensors.
  * 📈 **Canvas Line Chart**: Lightweight client-side sparkline renderer without external JS chart libraries.
  * 💡 **Controls**: Switches, range sliders with units, push buttons, and metrics.
  * 💻 **Web Terminal**: Streams serial and log output to an in-browser console.
  * 📁 **Flash File Explorer**: Interactive browser for files stored in onboard flash memory.

---

## 📂 Example Catalog

The [`examples/`](examples/) directory contains ready-to-run scripts covering each subsystem:

| Script | Subsystem / Feature | Description |
| :--- | :--- | :--- |
| [`01_minimal_controls.py`](examples/01_minimal_controls.py) | **Core Controls** | Minimal switch, slider, and button setup in under 15 lines. |
| [`02_sensor_telemetry.py`](examples/02_sensor_telemetry.py) | **Full Station** | Multi-tab dashboard with sparkline charts, camera viewfinder, and SDMMC card. |
| [`03_camera_stream_dashboard.py`](examples/03_camera_stream_dashboard.py) | **Camera** | Live camera snapshot capture and streaming viewfinder. |
| [`04_wifi_provisioner_portal.py`](examples/04_wifi_provisioner_portal.py) | **Wi-Fi Provisioner** | SoftAP and DNS captive redirection for zero-friction mobile onboarding. |
| [`05_persistent_config_store.py`](examples/05_persistent_config_store.py) | **Config Store** | Schema-driven settings forms and atomic `/config.json` flash persistence. |
| [`06_live_diagnostics.py`](examples/06_live_diagnostics.py) | **Diagnostics** | Turnkey System Health tab with live RAM meters, GC trigger, and soft reboot. |
| [`07_web_ota_updater.py`](examples/07_web_ota_updater.py) | **Web OTA** | Drag-and-drop web firmware flasher with SHA-256 verification. |

---

## 🌐 Accessing Dashboards: Desktop vs. Physical ESP32

When running examples, keep in mind where the Python process is executing:

### 1. Running on Physical ESP32 Hardware (via `mpremote`)
When executing a script on your connected board:
```bash
.venv/bin/mpremote run examples/06_live_diagnostics.py
```
* **Station Mode (Examples 02, 05, 06, 07)**:
  The ESP32 connects to your Wi-Fi network and prints its assigned local IP address:
  ```text
  Connecting to Wi-Fi 'NARASIMHA'...
  Dashboard URL: http://192.168.88.9:80/
  ```
  Open **`http://<ESP32_IP>:80/`** (e.g. `http://192.168.88.9:80/`) in your browser. *(Do NOT use `localhost`, as `localhost` points to your computer, not the microcontroller).*
* **Captive Portal Mode (Example 04)**:
  The ESP32 starts an Access Point named **`espmui-Setup`**. Connect your computer or phone to `espmui-Setup` and browse to **`http://192.168.4.1/`**.

### 2. Testing Locally on Your Computer (Desktop Simulation)
All `espmui` examples run natively on standard Python without hardware attached:
```bash
.venv/bin/python examples/06_live_diagnostics.py
```
Open **`http://localhost:80/`** directly in your browser.

---

## 📦 Installation & Deployment

### 🛠️ Local Development Setup

```bash
# 1. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dev dependencies (mpremote, ruff)
pip install -r requirements-dev.txt
# or: make install-dev
```

### Option 1: Direct via MicroPython `mip` (Recommended)
Connect your board to Wi-Fi and install `espmui` directly from GitHub:

```python
import mip
mip.install("github:csseeker/espmui")
```

Or install from your computer using `mpremote`:
```bash
mpremote mip install github:csseeker/espmui
```

### Option 2: Copy Package to Board
Copy the library directly to your board's root filesystem:

```bash
# Upload library package
mpremote fs cp -r src/espmui :

# Run telemetry station example
mpremote run examples/02_sensor_telemetry.py
```

---

## 🧪 Running Unit Tests

Unit tests use Python's standard `unittest` module and require zero third-party dependencies:

```bash
# Run all 62 unit tests
make test
# or: python3 -m unittest discover -s tests -p "test_*.py"

# Run linter
make lint
# or: ruff check .
```

---

## 📚 Documentation & Specifications

* [Feature Reference & Deep-Dive Guide](docs/FEATURES.md) — Comprehensive technical reference with sequence diagrams, architectural justifications, and code examples for each subsystem.
* [Product & Technical Roadmap](docs/ROADMAP.md) — Phased milestones, priorities, and detailed task breakdowns.
* [Architecture & System Design](docs/architecture.md) — High-level system architecture, component trees, and dataflow.
* [Value Proposition & User Personas](docs/VALUE_PROPOSITION.md) — Developer personas, user journeys, and competitive evaluation.
* [WebSocket Wire Protocol Specification](docs/protocol_spec.md) — Detailed JSON opcode schemas, event flows, and diff formats.
* [Concurrency, Non-blocking & Resilience Specification](docs/concurrency_and_resilience.md) — Concurrency models, cooperative yield slicing, backpressure queues, and fault isolation barriers.

---

## 🗺️ Product Roadmap & Milestone Status

* [x] **Milestone 1: Wi-Fi Provisioner & Captive Portal** (SoftAP, DNS port 53 interception, `/generate_204` redirects, mobile onboarding card).
* [x] **Milestone 2: Persistent Parameter & Config Store** (Schema-driven forms, atomic write-temp & rename flash persistence, change hooks).
* [x] **Milestone 3: Live Diagnostics & Telemetry Dashboard** (Heap allocation tracking, LittleFS storage, Wi-Fi RSSI, uptime, manual GC, soft reboot).
* [x] **Milestone 4: Web-Based Drag-and-Drop OTA Updater** (512B sliding window streaming, <4 KB peak RAM, incremental SHA-256, active partition toggling).
* [ ] **Milestone 5: Authentication & Access Control** (Configurable PIN / password protection for admin tabs and OTA endpoints).
* [ ] **Milestone 6: SD Card Logging & File Server** (Continuous historical telemetry logging and web file browser/download).

See the full [Pragmatic Product Roadmap](docs/ROADMAP.md) for architectural details and implementation plans.
