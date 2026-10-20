# `espmui`: Architecture & System Design

## 1. Overview & Motivation

`espmui` (ESP MicroPython UI) is a lightweight web dashboard library for the MicroPython ecosystem (ESP32, ESP32-S2/S3, ESP32-C2/C3/C6, and Raspberry Pi Pico W).

When developing microcontroller projects in MicroPython, creating an on-device web interface often involves assembling custom HTTP handlers, writing manual string formatting, or managing external web assets alongside hardware control code.

`espmui` aims to provide a simple, self-contained approach:
* Define user interfaces declaratively in Python (`App` -> `Tab` -> `Widget`).
* Serve a pre-compiled, compact web client directly from the microcontroller's flash memory.
* Synchronize widget states bidirectionally using small JSON messages over WebSockets.
* Keep runtime overhead modest so other tasks (such as sensor reading or motor control) continue to execute smoothly.

---

## 2. Design Principles

`espmui` is designed around several practical considerations common to embedded development:

| Principle | Approach in `espmui` | Practical Consideration |
| :--- | :--- | :--- |
| **Pythonic API** | Object-oriented widgets with callback registration (`on_click`, `on_change`) and property assignments. | Keeps setup straightforward and familiar for MicroPython developers. |
| **Self-Contained Bundle** | Single pre-compressed bundle (< 5 KB gzipped) containing HTML, CSS, and JavaScript. | Avoids external asset dependencies or manual asset deployment steps. |
| **Chunked Streaming** | Serves static assets directly in small chunks (e.g. 512–1024 bytes) with cooperative yields. | Helps prevent socket buffers or memory allocations from blocking the event loop. |
| **Differential State Sync** | Uses small JSON diffs (~35 bytes) for state updates rather than full page reloads. | Keeps network traffic and serialization overhead modest on resource-limited MCUs. |
| **Memory Consciousness** | Bounded queues and minimal state dictionaries. | Designed to operate within standard ESP32 RAM limits (~30–40 KB free heap). |
| **Extensible Widgets** | Base `Widget` class that can be extended for specialized sensors or actuators. | Allows users to create project-specific components if needed. |
| **Standard Library Focus** | Built on standard `uasyncio` and built-in socket APIs without external runtime libraries. | Simplifies installation via `mip` or direct file copying. |

---

## 3. Core Architectural Pillars

### 3.1. Pre-Compressed Asset Pipeline
* The frontend single-page application is minified and gzipped into an embedded byte stream (`assets.py`, currently ~4.7 KB).
* When an HTTP client requests `GET /`, MicroPython streams the compressed byte stream in small chunks (e.g., 1024 bytes) directly from storage:
  ```http
  HTTP/1.1 200 OK
  Content-Type: text/html
  Content-Encoding: gzip
  Cache-Control: max-age=86400
  ```
* **Memory impact**: Reduces RAM pressure by streaming compressed data directly in chunks, avoiding in-memory template rendering or large string allocations.

### 3.2. Asynchronous Server & WebSocket Engine
* Built with standard `uasyncio` (`asyncio.start_server`).
* Features a compact WebSocket implementation supporting RFC 6455 handshakes and frame handling.
* Operates cooperatively within the event loop to run alongside user tasks such as sensor polling or motor control.

### 3.3. Declarative Component Tree & Diff Protocol
* The Python application defines a hierarchy: `App` -> `Tab` -> `Widget`.
* **Initial handshake**:
  * Browser connects via WebSocket.
  * ESP sends the schema JSON: `{"op": "init", "title": "Node 1", "tabs": [...]}`.
  * The browser constructs the corresponding UI elements.
* **Inbound events (Browser -> ESP)**:
  * User moves slider to 75: `{"op": "evt", "id": "w_brightness", "val": 75}`.
  * ESP executes user's registered Python callback: `on_change(widget, value)`.
* **Outbound state sync (ESP -> Browser)**:
  * ESP sensor loop reads temp: `temp_gauge.value = 42.1`.
  * Python setter automatically broadcasts diff: `{"op": "set", "id": "w_temp", "val": 42.1}`.
  * Connected browser clients receive the diff and update their local controls without a full page reload.

### 3.4. Wi-Fi Provisioner & Captive Portal Subsystem
* **DNS Interception Server (`DNSServer`)**:
  * Asynchronous UDP listener on port 53.
  * Intercepts all standard OS domain resolution probes (`connectivitycheck.gstatic.com`, `captive.apple.com`, `msftconnecttest.com`) and resolves them with RFC 1035 A-records pointing to the device's SoftAP IP (`192.168.4.1`).
* **Captive HTTP Redirection (`CaptivePortal`)**:
  * Traps captive probe URLs (`/generate_204`, `/gen_204`, `/hotspot-detect.html`, `/ncsi.txt`, `/connecttest.txt`) and responds with HTTP 302 redirects to `http://192.168.4.1/`.
  * Immediately prompts mobile operating systems (iOS CNA sheet, Android captive notification) to display the onboarding screen.
* **Asynchronous Wi-Fi Manager (`WiFiManager`)**:
  * Non-blocking background scanning with SSID deduplication and RSSI signal quality bars.
  * Robust credential verification that tests station connection asynchronously without terminating SoftAP, preventing user lockout if credentials are mistyped.
* **REST Provisioning Endpoints**:
  * `GET /api/wifi/scan`: Discovers nearby networks with signal bars and security status.
  * `POST /api/wifi/connect`: Receives credentials, verifies link, and returns assigned station IP.
  * `GET /api/wifi/status`: Returns current Wi-Fi status and mode.

### 3.5. Persistent Parameter & Config Store Subsystem
* **Atomic Flash Persistence Engine (`ConfigStore`)**:
  * Implements an atomic write-to-temp (`config.json.tmp`) and inode rename (`os.rename`) pattern to eliminate the zero-byte truncation risk inherent to sudden MCU power brownouts.
  * Automatic power-cut recovery: if `config.json` is truncated or corrupted on boot, automatically recovers from `.tmp` or falls back gracefully to schema defaults.
* **Schema-Driven Form Generation (`ConfigForm`)**:
  * Dynamically generates styled HTML form components directly from a Python dictionary definition (`text`, `number`, `bool`, `select`, `slider`, `password`).
  * Enforces strict type checking, numeric bounds (`min`/`max`), and dropdown option validation before committing changes.
* **Variable Binding & Change Hooks**:
  * Direct attribute access (`config.sample_rate`) with support for synchronous and asynchronous (`async def`) change callbacks (`@config.on_change("param")`).
* **REST Endpoints**:
  * `GET /api/config`: Returns active values and schema metadata.
  * `POST /api/config`: Validates incoming payload, commits to flash atomically, triggers change hooks, and returns status.

### 3.6. Live Diagnostics & Telemetry Dashboard Subsystem
* **System Metrics Aggregator (`SystemDiagnostics`)**:
  * Gathers real-time hardware telemetry: `gc.mem_free()` and `gc.mem_alloc()` heap status, LittleFS/FAT storage from `os.statvfs('/')`, Wi-Fi RSSI (dBm), CPU clock frequency, and rollover-safe uptime (`time.ticks_diff()`).
* **Turnkey Administrative UI (`app.enable_diagnostics()`)**:
  * Injects a turnkey "System Health" navigation tab with visual progress bars, uptime/CPU metrics, and actionable maintenance controls.
* **Maintenance & Recovery Actions**:
  * Interactive Garbage Collector trigger (`gc.collect()`) reporting byte recovery in real-time.
  * Safe soft restart (`machine.reset()`) with delayed scheduling to allow graceful socket teardown.
* **REST Endpoints**:
  * `GET /api/system/metrics`: Live JSON metrics payload.
  * `POST /api/system/gc`: Executes garbage collection and returns freed bytes.
  * `POST /api/system/reboot`: Acknowledges and schedules soft reboot.

---

## 4. Developer Experience & API Design

```python
import asyncio
import espmui
from machine import Pin

relay = Pin(4, Pin.OUT, value=0)

# 1. Initialize Application
app = espmui.App(title="S3 Sensor Dashboard", theme="dark")

# 2. Add Navigation Tabs
tab_ctrl = app.tab("Controls", icon="sliders")
tab_diag = app.tab("Diagnostics", icon="activity")

# 3. Add Control Widgets
relay_switch = tab_ctrl.switch(
    "Main Relay", 
    value=False, 
    on_change=lambda w, val: relay.value(1 if val else 0)
)

brightness = tab_ctrl.slider(
    "LED Brightness", 
    min=0, max=100, value=50, 
    on_change=lambda w, val: print("Brightness:", val)
)

# 4. Add Telemetry Widgets
temp_metric = tab_diag.metric("Die Temp", value="--", unit="°C", icon="thermometer")
mem_progress = tab_diag.progress("Free Memory", max=8192, unit="KB")

# 5. Background Sensor Loop (updates UI reactively)
async def sensor_loop():
    import esp32, gc
    while True:
        temp_metric.value = round((esp32.raw_temperature() - 32) * 5 / 9, 1)
        mem_progress.value = gc.mem_free() // 1024
        await asyncio.sleep(2)

# 6. Start Application
app.create_task(sensor_loop())
app.run(host="0.0.0.0", port=80)
```

-## 5. Widget Catalog

### 5.1. Control Widgets
* **Button**: Push, momentary, or pulse buttons with custom color accents and icon support.
* **Switch / Toggle**: Smooth animated toggle switch with state change callback.
* **Slider**: Touch-friendly slider with live numeric readout.
* **Button Pad / D-Pad**: Directional pad layout for robotics or pan-tilt control.
* **Select / Dropdown**: Single and multi-option selectors.
* **Color Picker**: Compact color picker with hex/RGB support.
* **Text & Number Input**: Input forms with validation and submit callbacks.

### 5.2. Telemetry & Monitoring Widgets
* **Metric Card**: Numerical display with label, unit, status badge, and optional icon.
* **Progress Bar**: Linear horizontal progress bar with percentage readout.
* **Gauge**: Radial dial gauge for sensor metrics.
* **Live Line Chart**: Canvas time-series chart with a rolling buffer and no external JS libraries.
* **Status Badge**: Status indicators (e.g., Online/Offline, Warning, OK).

### 5.3. Specialized IoT Widgets
* **Camera Streamer**: Viewport supporting snapshot capture and MJPEG streaming for supported sensors (such as OV2640 / OV3660 / OV5640).
* **Live Web Terminal**: Streams `print()` output and log messages into an in-browser console.
* **Flash File Explorer**: File browser to view, download, and delete files on onboard LittleFS/FAT storage.
* **System Monitor**: Displays system telemetry (RAM, Flash, Wi-Fi RSSI, and uptime).

---

## 6. Directory Structure

```
espmui/
├── docs/
│   ├── architecture.md               # System design and architecture
│   ├── protocol_spec.md              # WebSocket wire protocol specification
│   └── concurrency_and_resilience.md # Non-blocking concurrency & resilience specification
├── src/
│   └── espmui/
│       ├── __init__.py               # Library entrypoint
│       ├── app.py                    # App coordinator and tab management
│       ├── server.py                 # Async HTTP and WebSocket server
│       ├── widgets.py                # Standard widget classes
│       ├── iot_widgets.py            # Additional widgets (Camera, Terminal, File Manager)
│       ├── wifi.py                   # Wi-Fi Provisioner, DNS Interceptor, Captive Portal
│       ├── config.py                 # Persistent Parameter Store & Schema Form
│       ├── diagnostics.py            # Live Diagnostics & Telemetry Collector
│       └── assets.py                 # Pre-compressed web assets
├── web/                              # Frontend source
│   ├── index.html                    # Single-page application shell
│   └── build.py                      # Build script: minify, gzip, generate assets.py
├── examples/
│   ├── 01_minimal_controls.py        # Basic controls example
│   ├── 02_sensor_telemetry.py        # Sensor telemetry and line chart
│   ├── 03_camera_dashboard.py        # Camera dashboard example
│   └── 04_system_monitor.py          # System diagnostic dashboard
├── tests/                            # Automated unit tests
└── README.md                         # Project documentation
```

---

## 7. Phased Implementation Roadmap

### Phase 1: Micro-Server & WebSocket Core
* Implement `espmui.server`: non-blocking async HTTP/1.1 parser + WebSocket handshake & framing.
* Implement gzip chunked file streaming directly from flash.
* Validate memory allocation per connection during handshake.

### Phase 2: Python Component Model & Protocol
* Implement `App`, `Tab`, `Widget` base classes.
* Implement property setters with reactive broadcast queues.
* Define JSON message formats for `init`, `evt`, `set`, and `batch`.

### Phase 3: Embedded Frontend
* Develop the single-page application shell:
  * Dark mode layout with responsive CSS.
  * Vanilla JS WebSocket state reconciler (updates DOM elements based on widget IDs).
  * Touch and pointer interactions.
* Build automated Python bundling script (`build.py`) that inlines CSS/JS, minifies, gzips, and creates `assets.py`.

### Phase 4: Core Widget Suite
* Deliver Button, Switch, Slider, Metric Card, Progress Bar, and Dropdown.
* Build multi-client state sync verification across connected browsers.

### Phase 5: Specialized IoT Widgets
* Implement **Camera Streamer** widget (integrates with MicroPython `camera` module).
* Implement **Live Web Terminal** (integrates with stdout broadcast queue).
* Implement **Flash File Explorer** widget.
* Implement **Canvas Sparkline/Line Chart** widget.

### Phase 6: Packaging, Examples & Testing
* Test across target hardware configurations (ESP32-S3 with PSRAM and standard ESP32).
* Provide clear examples in `examples/`.
* Write documentation and package for deployment via `mip` and `mpremote`.
