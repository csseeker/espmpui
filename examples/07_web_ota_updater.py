"""
Example 07: Web-Based Drag-and-Drop OTA Firmware Updater
Demonstrates streaming multipart file uploads without RAM buffering,
direct flash partition writes, incremental SHA-256 verification, and active boot switching.
"""

try:
    import espmpui
except ImportError:
    import os
    import sys
    if hasattr(os, "path"):
        sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))
    import espmpui

# 1. Initialize Application
app = espmpui.App(title="OTA Edge Node", theme="dark")

# 2. Add Standard Operational Tabs
tab_ctrl = app.tab("Controls", icon="sliders")
tab_ctrl.switch("Sensor Power", value=True)
tab_ctrl.slider("Sample Interval", min=1, max=60, value=5, unit="s")

# 3. Enable System Diagnostics
app.enable_diagnostics(title="System Health", icon="cpu")

# 4. Enable Web-Based Drag-and-Drop OTA Updater
# Registers:
# - GET /api/ota/status -> active boot partition & inactive target update partition
# - POST /api/ota/upload -> streaming multipart receiver (512B chunking, OOM safe)
# - Header "⬆ OTA" button + Drag-and-Drop modal dialog with real-time progress bar,
#   amber flash risk warning, SHA-256 checksum readout, and 10s reboot countdown.
ota = app.enable_ota()

def connect_wifi():
    """Connects to Wi-Fi using .env credentials on MicroPython, or returns IP/localhost."""
    try:
        import network
        import time
        wlan = network.WLAN(network.STA_IF)
        wlan.active(True)
        if not wlan.isconnected():
            ssid, pwd = "", ""
            for p in (".env", "/.env", "../.env"):
                try:
                    with open(p) as f:
                        for line in f:
                            clean_line = line.split("#", 1)[0].strip()
                            if clean_line.startswith("WIFI_SSID") and "=" in clean_line:
                                ssid = clean_line.split("=", 1)[1].strip().strip("'\"")
                            elif clean_line.startswith("WIFI_PASSWORD") and "=" in clean_line:
                                pwd = clean_line.split("=", 1)[1].strip().strip("'\"")
                except Exception:
                    pass
            if ssid:
                print(f"Connecting to Wi-Fi '{ssid}'...")
                wlan.connect(ssid, pwd)
                for _ in range(25):
                    if wlan.isconnected():
                        break
                    time.sleep(0.4)
        if wlan.isconnected():
            return wlan.ifconfig()[0]
    except Exception:
        pass
    return "localhost"


if __name__ == "__main__":
    ip = connect_wifi()
    st = ota.get_status()
    print("==================================================")
    print(" espmpui Web OTA Updater Initialized")
    print("==================================================")
    print(f" Active Boot Partition:   {st['running_partition']}")
    print(f" Target Update Partition: {st['next_update_partition']}")
    print(f" Dashboard URL:           http://{ip}:80/")
    print(f" (Open http://{ip}:80/ in Safari on your Mac/Phone)")
    print(" Click '⬆ OTA' in top header to upload firmware (.bin)")
    print("==================================================")
    app.run(port=80)
