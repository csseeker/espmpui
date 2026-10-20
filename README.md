# `espmui`: Modern Reactive Web Dashboard for MicroPython

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![MicroPython](https://img.shields.io/badge/MicroPython-v1.20%2B-green.svg)](https://micropython.org/)
[![Zero External Dependencies](https://img.shields.io/badge/Dependencies-Zero-brightgreen.svg)]()
[![Bundle Size](https://img.shields.io/badge/Bundle%20Size-4.7%20KB-blueviolet.svg)]()

`espmui` is a lightweight web dashboard library designed for **MicroPython** microcontrollers (such as ESP32, ESP32-S2/S3, ESP32-C3/C6, and Raspberry Pi Pico W).

It provides a simple declarative Python API to create on-device controls and telemetry displays, paired with a compact pre-gzipped frontend bundle (~4.7 KB) served directly over HTTP and synchronized via WebSockets with no external runtime dependencies.

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
tab.slider("Speed", min=0, max=100, step=5, value=25, on_change=lambda w, val: print("Speed:", val))
tab.button("Pulse", accent="danger", on_click=lambda w: print("Pulse clicked!"))

if __name__ == "__main__":
    app.run(port=80)
```

---

## ✨ Key Features

* **No External Runtime Dependencies**: Built entirely with standard MicroPython `uasyncio` and socket modules.
* **Compact Embedded Frontend**: The single-page interface (HTML, CSS, JS, and canvas sparkline) compresses to ~4.7 KB and is served from flash in small chunks with cooperative yields (`sleep_ms(0)`).
* **Two-Way Synchronization**:
  * Updating `widget.value` in Python sends a small JSON diff over WebSockets to connected browsers.
  * User inputs (such as buttons, sliders, and switches) invoke Python callbacks directly.
* **Callback Exception Handling**: Exceptions inside user callbacks are caught and reported to the serial console and web interface, helping keep the main event loop running.
* **Bounded Queues**: Telemetry updates use bounded queues with a latest-state-wins policy to help conserve RAM if clients are slow or disconnected.
* **Wi-Fi Provisioner & Captive Portal**:
  * Zero-friction mobile onboarding with SoftAP and RFC 1035 UDP DNS interception (port 53).
  * Traps captive probe URLs (`/generate_204`, `/hotspot-detect.html`, `/ncsi.txt`) with instant 302 redirects.
  * Mobile-first frontend onboarding card with background scanning, RSSI signal bars, password reveal, and safe connection testing without AP teardown.
* **Included Widgets**:
  * 📑 **Multi-Tab Layout**: Organize dashboards across multiple tabs (e.g., Controls, Sensors, Diagnostics).
  * 📸 **Camera Viewfinder**: Basic snapshot capture and MJPEG streaming for supported camera modules (such as OV2640).
  * 📈 **Canvas Line Chart**: Simple client-side sparkline renderer without external JavaScript libraries.
  * 💡 **Controls**: Switches, sliders, buttons, and color pickers.
  * 💻 **Web Terminal**: Streams serial and log output to an in-browser console.
  * 📁 **File Explorer**: Basic browser for files stored in onboard flash memory.

---

## 📦 Installation & Deployment

### 🛠️ Local Development & Flashing Setup

To develop locally, run tests, or upload to your board:

```bash
# 1. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies & dev tools (mpremote, ruff)
pip install -r requirements-dev.txt
# or: make install-dev
```

### Option 1: Direct via MicroPython `mip` (Recommended)
Connect your board to Wi-Fi and install `espmui` with one line:

```python
import mip
mip.install("github:csseeker/espmui")
```

Or install from your computer using `mpremote`:
```bash
mpremote mip install github:csseeker/espmui
```

### Option 2: Copy via `mpremote`
Copy the package directly to your board's root filesystem:

```bash
# Upload library package
mpremote fs cp -r src/espmui :

# Run telemetry station example
mpremote run examples/02_sensor_telemetry.py
```

Then open your browser to your ESP32's IP address (e.g. `http://192.168.1.100:80/`)!

---

## 🧪 Running Unit Tests

Unit tests use Python's standard `unittest` module and require no third-party libraries:

```bash
make test
# or: python3 -m unittest discover -s tests -p "test_*.py"
```

---

## 📚 Documentation & Specifications

* [Value Proposition & User Personas](docs/VALUE_PROPOSITION.md)
* [Feature Reference & Deep Dive](docs/FEATURES.md)
* [Product & Technical Roadmap](docs/ROADMAP.md)
* [Architecture & System Design](docs/architecture.md)
* [WebSocket Wire Protocol Specification](docs/protocol_spec.md)
* [Concurrency, Non-blocking & Resilience Specification](docs/concurrency_and_resilience.md)

---

## 🗺️ Product Roadmap & Upcoming Milestones

We are actively expanding `espmui` with high-impact, turnkey IoT modules:
* 📡 **Wi-Fi Manager & Captive Portal**: SoftAP mode fallback with `/generate_204` captive detection to scan networks and input credentials without hardcoding secrets.
* 💾 **Persistent Parameter Store**: Atomic flash persistence for settings forms that survive device reboots.
* 📊 **Live Hardware Diagnostics**: Real-time free heap & GC meters, Wi-Fi RSSI monitor, uptime counters, and system controls.
* 🚀 **Web-Based OTA Updater**: Drag-and-drop firmware `.bin` and filesystem flashing directly from the browser.

See the full [Pragmatic Product Roadmap](docs/ROADMAP.md) for architectural rationale and milestone deliverables.


