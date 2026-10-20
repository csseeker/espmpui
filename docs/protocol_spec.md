# `espmpui` WebSocket Wire Protocol Specification

Version: 1.0.0-draft

## 1. Overview
Communication between the MicroPython `espmpui` server and connected browser clients uses a bidirectional, text-based JSON WebSocket protocol.

The protocol is designed around three practical goals:
1. **Compact payload size**: State updates are formatted as small JSON objects (typically < 100 bytes).
2. **Targeted state diffs**: Modifying a widget sends individual property updates rather than re-transmitting the full UI tree.
3. **Multi-client broadcast**: Updates are broadcast to all connected clients to keep displays synchronized.

---

## 2. Message Types

All messages are JSON objects containing an `"op"` (operation) field.

| Opcode | Direction | Description | Typical Size |
| :--- | :--- | :--- | :--- |
| `init` | Server -> Client | Full UI tree sent upon initial connection | ~1-3 KB |
| `evt` | Client -> Server | Inbound user interaction (click, slider change, form input) | ~30-50 bytes |
| `set` | Server -> Client | Reactive widget state change (telemetry, feedback) | ~30-50 bytes |
| `batch` | Server -> Client | Multiple state changes bundled together | ~100-200 bytes |
| `cmd` | Both | System-level commands (e.g. reboot, clear log, camera trigger) | ~30 bytes |

---

## 3. Detailed Schemas

### 3.1. `init` (Initial Handshake)
Sent by the ESP immediately after the WebSocket connection completes.

```json
{
  "op": "init",
  "title": "ESP32-S3 Camera Node",
  "theme": "dark",
  "tabs": [
    {
      "id": "tab_main",
      "title": "Controls",
      "icon": "sliders",
      "widgets": [
        {
          "id": "w_relay",
          "type": "switch",
          "label": "Light Relay",
          "val": true
        },
        {
          "id": "w_bright",
          "type": "slider",
          "label": "Brightness",
          "min": 0,
          "max": 100,
          "step": 1,
          "val": 75
        }
      ]
    },
    {
      "id": "tab_telemetry",
      "title": "Sensors",
      "icon": "activity",
      "widgets": [
        {
          "id": "w_temp",
          "type": "metric",
          "label": "Die Temperature",
          "val": 42.5,
          "unit": "°C",
          "badge": "Normal"
        }
      ]
    }
  ]
}
```

### 3.2. `evt` (Client Interaction Event)
Sent by the browser when the user interacts with an element.

```json
{
  "op": "evt",
  "id": "w_bright",
  "e": "change",
  "val": 82
}
```

For buttons:
```json
{
  "op": "evt",
  "id": "w_btn_capture",
  "e": "click"
}
```

### 3.3. `set` (Server State Diff)
Sent by the ESP when any widget property changes in Python.

```json
{
  "op": "set",
  "id": "w_temp",
  "val": 43.1
}
```

Updating multiple properties (e.g., value + badge color):
```json
{
  "op": "set",
  "id": "w_temp",
  "val": 65.0,
  "badge": "Hot",
  "accent": "danger"
}
```

### 3.4. `batch` (Bundled Telemetry Updates)
When multiple sensors update at once, the ESP can combine updates into one frame to minimize network roundtrips:

```json
{
  "op": "batch",
  "diffs": [
    {"id": "w_temp", "val": 42.3},
    {"id": "w_mem", "val": 7820},
    {"id": "w_rssi", "val": -54}
  ]
}
```

### 3.5. `stream` (Terminal / Log Streaming)
Pushes live text or debug prints directly into the browser terminal widget:

```json
{
  "op": "stream",
  "id": "w_term",
  "text": "[Sensor] Reading calibrated: 1013.25 hPa\n"
}
```

---

## 4. Reconnection & Resilience
* The browser automatically pings the server if idle for 15 seconds.
* If disconnected (e.g. Wi-Fi blip or ESP reboot), the client displays a subtle "Reconnecting..." indicator and automatically attempts to reconnect every 2 seconds with exponential backoff.
* Upon reconnection, the client automatically requests a fresh `init` state to resynchronize without a full browser refresh.
