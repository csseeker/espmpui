# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.1.0] - 2026-10-17

### Added
- Core declarative dashboard framework: `App`, `Tab`, `Widget`.
- Interactive widgets: `Switch`, `Slider`, `Button`, `Metric`, `Progress`.
- IoT specialized widgets:
  - `LineChart`: 60fps HTML5 Canvas streaming sparkline with gradient fill.
  - `CameraStream`: MJPEG / JPEG snapshot viewfinder with exposure controls.
  - `Terminal`: ANSI-compatible live telemetry browser console.
  - `FileManager`: Flash LittleFS/FAT explorer.
- Zero-copy pre-gzipped frontend SPA engine (< 5 KB compressed).
- Pure `uasyncio` HTTP and RFC 6455 WebSocket server with auto-reconnect.
- Two-way reactive state synchronization via compact JSON diffs (~35 bytes).
- Non-blocking cooperative yield execution and fault barrier exception handling.
- MicroPython `mip` installation manifest (`package.json`).
- Automated test suite covering server handshake, widget diffs, and event dispatching.
