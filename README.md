# `espmpui`: Reactive Web Micro-Framework & Device Management Toolkit for MicroPython

[![PyPI](https://img.shields.io/pypi/v/espmpui.svg)](https://pypi.org/project/espmpui/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![MicroPython](https://img.shields.io/badge/MicroPython-v1.20%2B-green.svg)](https://micropython.org/)
[![Zero External Dependencies](https://img.shields.io/badge/Dependencies-Zero-brightgreen.svg)]()
[![Bundle Size](https://img.shields.io/badge/Bundle%20Size-~13.2%20KB-blueviolet.svg)]()
[![Tests](https://img.shields.io/badge/Tests-62%20Passing-success.svg)]()

> **A zero-dependency reactive micro-framework and device management toolkit that brings app-like web dashboards, mobile Wi-Fi captive portals, persistent configuration, and OTA updating to your ESP32 or Pico W in under 15 lines of pure Python.**

`espmpui` is an ultra-lightweight, zero-dependency **reactive web micro-framework and device management toolkit** for **MicroPython** (ESP32, ESP32-S2/S3, ESP32-C3/C6, and Raspberry Pi Pico W).

It pairs a declarative Python API with a pre-gzipped, CDN-free embedded frontend (~13.2 KB) synchronized in real-time over WebSockets.

<p align="center">
  <img src="docs/images/dashboard_sensors.png" alt="espmpui Sensors Dashboard" width="100%">
</p>

<details>
  <summary><b>📷 View More Screenshots (Heap Telemetry & Diagnostics)</b></summary>
  <br>

  #### Memory & GC Tracking
  <img src="docs/images/dashboard_memory.png" alt="Memory & Heap Telemetry" width="100%">

  #### Live Telemetry & Terminal Stream
  <img src="docs/images/dashboard_diagnostics.png" alt="Diagnostics & Live Stream" width="100%">
</details>

---

## ⚡ Why `espmpui`?

Building web interfaces for microcontrollers usually means wrestling with raw socket strings, 1995-style HTML forms, or heavy Node/npm pipelines that exhaust microcontroller memory.

`espmpui` provides a complete, modern embedded device interface out-of-the-box:

* **No Frontend Toolchain Needed**: Zero `npm` builds, Webpack configs, or CDN dependencies. The single-page app (~13.2 KB) is served straight from device flash.
* **Two-Way Reactive Sync**: State changes update connected web clients in real-time via compact (~35 byte) WebSocket diffs.
* **Low Memory Footprint**: Operates within `< 8 KB RAM` overhead and `< 4 KB RAM` during OTA updates. Built specifically for constrained microcontrollers.
* **Fault-Isolated Execution**: User callback crashes are caught gracefully without breaking the `uasyncio` server loop.
* **Complete Hardware Lifecycle**: Out-of-the-box Wi-Fi captive portal, persistent flash config store, real-time diagnostics, and drag-and-drop OTA firmware updating.

---

## 📊 How Does It Compare?

| Feature | `espmpui` | Microdot / Picoweb | ESPHome / Tasmota | Blynk / Cloud IoT |
| :--- | :---: | :---: | :---: | :---: |
| **Language** | **MicroPython** | MicroPython | C++ / YAML | C++ / Python |
| **Turnkey Modern UI** | ✅ Built-in (MUI style) | ❌ Manual HTML/CSS | ✅ Built-in | ✅ App-based |
| **Zero Frontend Tooling** | ✅ Pre-compiled (~13.2 KB) | ❌ Build your own | ✅ Pre-compiled | ❌ Cloud setup |
| **Local / Air-Gapped** | ✅ 100% Local | ✅ Local | ✅ Local | ❌ Requires Cloud |
| **Embeddable in Custom Code** | ✅ Yes (`import espmpui`) | ✅ Yes | ❌ Owns entire firmware | ⚠️ Partial |
| **Captive Portal + OTA Included** | ✅ Turnkey | ❌ Manual implementation | ✅ Built-in | ⚠️ Paid / Complex |
| **RAM Overhead** | **< 8 KB** | < 10 KB | ~30–60 KB | ~20–40 KB |

---

## 🖥️ Hardware & Platform Support

| Target Platform | Status | Connection | Features Supported |
| :--- | :---: | :---: | :--- |
| **ESP32 / ESP32-S2 / ESP32-S3** | ✅ Tested | Wi-Fi / AP | Full suite (Captive Portal, Diagnostics, OTA Partition Switch) |
| **ESP32-C3 / ESP32-C6 (RISC-V)** | ✅ Tested | Wi-Fi / AP | Full suite |
| **Raspberry Pi Pico W** | ✅ Tested | Wi-Fi / AP | Full suite (OTA operates in filesystem write mode) |
| **Desktop Simulation (macOS/Linux/Win)** | ✅ Tested | `localhost:80` | Full UI & Controls simulation (no hardware required) |

---

## 🚀 Quick Start in 60 Seconds

### Option A: Test on your Desktop (No Hardware Required)
You can test `espmpui` directly on your computer before plugging in a microcontroller:

```bash
git clone https://github.com/csseeker/espmpui.git
cd espmpui
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

# Run the minimal controls demo locally
python examples/01_minimal_controls.py
```
Open **`http://localhost:80/`** in your browser.

---

### Option B: Deploy to a Physical ESP32 or Pico W

#### 1. Copy `espmpui` to your board
Using [`mpremote`](https://docs.micropython.org/en/latest/reference/mpremote.html):
```bash
mpremote fs cp -r src/espmpui :
```
*(Or install directly over Wi-Fi on the board via `mip.install("github:csseeker/espmpui")`)*.

#### 2. Run your first dashboard
Save this as `main.py` on your ESP32:

```python
import espmpui
from machine import Pin
import network

# 1. Connect to local Wi-Fi (or use espmpui's Captive Portal)
wlan = network.WLAN(network.STA_IF)
wlan.active(True)
wlan.connect("YOUR_WIFI_SSID", "YOUR_WIFI_PASSWORD")

led = Pin(2, Pin.OUT, value=0)

# 2. Build Dashboard
app = espmpui.App(title="ESP32 IoT Dashboard", theme="dark")
tab = app.tab("Controls", icon="sliders")

tab.switch("LED", value=False, on_change=lambda w, val: led.value(1 if val else 0))
tab.slider("Speed", min=0, max=100, step=5, value=25, unit="%", on_change=lambda w, val: print("Speed:", val))
tab.button("Pulse", accent="danger", on_click=lambda w: print("Pulse clicked!"))

# 3. Turnkey System Health Diagnostics & Web OTA Updater
app.enable_diagnostics()
app.enable_ota()

if __name__ == "__main__":
    app.run(port=80)
```

Run it immediately:
```bash
mpremote run main.py
```
Check the serial console for your device IP and navigate to **`http://<ESP32_IP>:80/`**.

---

## 🧰 Turnkey Features

| Feature | Description | Example |
| :--- | :--- | :--- |
| **Core Widgets** | Switches, range sliders, push buttons, metrics, and tab navigation. | [`01_minimal_controls.py`](examples/01_minimal_controls.py) |
| **Sensor Telemetry** | Canvas sparkline charts, metrics, and live camera streaming (OV2640). | [`02_sensor_telemetry.py`](examples/02_sensor_telemetry.py) |
| **Wi-Fi Captive Portal** | SoftAP + DNS interception (`192.168.4.1`) for painless mobile Wi-Fi onboarding. | [`04_wifi_provisioner_portal.py`](examples/04_wifi_provisioner_portal.py) |
| **Persistent Config** | Schema-driven form generator with atomic, corruption-proof `/config.json` saves. | [`05_persistent_config_store.py`](examples/05_persistent_config_store.py) |
| **Live Diagnostics** | Out-of-the-box RAM/heap meters, flash storage usage, manual GC trigger, and soft reboot. | [`06_live_diagnostics.py`](examples/06_live_diagnostics.py) |
| **Web OTA Updater** | Browser drag-and-drop firmware flashing with SHA-256 verification and partition switching. | [`07_web_ota_updater.py`](examples/07_web_ota_updater.py) |

---

## 🧪 Testing & Verification

Unit tests use Python's standard `unittest` module and run standalone without hardware:

```bash
# Run all tests
make test
# or: python3 -m unittest discover -s tests -p "test_*.py"

# Run linter
make lint
# or: ruff check .
```

---

## 📚 Technical References

* [Feature Reference & Deep-Dive Guide](docs/FEATURES.md) — Architectural justifications and component guides.
* [Product & Technical Roadmap](docs/ROADMAP.md) — Phased milestones, priorities, and detailed task breakdowns.
* [System Value Proposition & Personas](docs/VALUE_PROPOSITION.md) — Target user personas, before/after journeys, and feature gating rules.
* [Architecture & System Design](docs/architecture.md) — System architecture, component trees, and dataflow.
* [WebSocket Wire Protocol Specification](docs/protocol_spec.md) — JSON opcode schemas, event flows, and diff formats.
* [Concurrency & Resilience Specification](docs/concurrency_and_resilience.md) — Cooperative slicing, backpressure queues, and fault isolation.

---

## 📄 License & Disclaimer

This project is licensed under the [MIT License](LICENSE).

### Disclaimer of Warranty

> **Important**: This software is provided **"as is"**, without warranty of any kind, express or implied, including but not limited to the warranties of merchantability, fitness for a particular purpose, non-infringement, or system uptime. 
>
> In no event shall the authors, maintainers, or contributors be held liable for any claim, damages, hardware damage (including but not limited to bricked microcontrollers, corrupted flash memory, or electrical hazards), data loss, or other liabilities arising from the use of, or inability to use, this software. Users and developers are solely responsible for testing and validating their device configurations, wiring, and firmware updates.
