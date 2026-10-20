"""
Example 06: Live System Diagnostics & Administrative Dashboard
Demonstrates zero-setup heap monitoring, GC optimization, flash usage, and remote reboot.
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
app = espmpui.App(title="S3 Industrial Node", theme="dark")

# 2. Add Standard Operational Tabs
tab_ctrl = app.tab("Controls", icon="sliders")
tab_ctrl.switch("Pump Relay", value=False)
tab_ctrl.slider("Flow Rate", min=0, max=100, value=40, unit="%")

# 3. Enable Out-of-the-Box Diagnostics
# Automatically creates a "System Health" tab with:
# - Live RAM / Heap allocation & free progress bar
# - LittleFS/FAT Flash storage meter
# - Human-readable system uptime counter
# - CPU clock frequency & platform badge
# - Interactive "🧹 Run Garbage Collector" button (shows freed bytes in toast)
# - Interactive "⚡ Restart Device" button (with soft reboot delay)
# - REST telemetry API (/api/system/metrics, /api/system/gc, /api/system/reboot)
diag = app.enable_diagnostics(title="System Health", icon="cpu", start_loop=True)

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
    metrics = diag.get_metrics()
    print("==================================================")
    print(f" Platform:       {metrics['platform']} ({metrics['implementation']})")
    print(f" CPU Clock:      {metrics['cpu_freq_mhz']} MHz")
    print(f" Free RAM:       {metrics['heap']['free_kb']} KB / {metrics['heap']['total_kb']} KB")
    print(f" Flash Free:     {metrics['flash']['free']} KB / {metrics['flash']['total']} KB")
    print(f" Dashboard URL:  http://{ip}:80/")
    print(f" (Open http://{ip}:80/ in Safari on your Mac/Phone)")
    print("==================================================")
    app.run(port=80)
