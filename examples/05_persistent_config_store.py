"""
Example 05: Persistent Configuration Store & Schema-Driven Forms
Demonstrates atomic flash persistence, input validation, change hooks, and automatic web forms.
"""

try:
    import espmui
except ImportError:
    import os
    import sys
    if hasattr(os, "path"):
        sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))
    import espmui

# 1. Initialize espmui Dashboard
app = espmui.App(title="Smart Greenhouse Node", theme="dark")

# 2. Define Parameter Schema
config_schema = {
    "node_name": {
        "type": "text",
        "label": "Node Identifier",
        "default": "Greenhouse-North",
        "hint": "Name displayed in telemetry feeds",
    },
    "sample_rate": {
        "type": "number",
        "label": "Sensor Polling Interval (sec)",
        "default": 10,
        "min": 1,
        "max": 3600,
        "unit": "s",
        "hint": "Sampling period (1 to 3600 seconds)",
    },
    "auto_vent": {
        "type": "bool",
        "label": "Automatic Ventilation Fan",
        "default": True,
    },
    "target_temp": {
        "type": "slider",
        "label": "Target Temperature (°C)",
        "default": 24,
        "min": 15,
        "max": 35,
        "unit": "°C",
    },
    "log_level": {
        "type": "select",
        "label": "Diagnostics Verbosity",
        "options": ["DEBUG", "INFO", "WARN", "ERROR"],
        "default": "INFO",
    },
}

# 3. Attach Persistent ConfigStore
# Loads /config.json (with atomic write and 0-byte power-cut recovery)
config = app.attach_config(config_schema, filepath="config.json")

# 4. Register Change Hooks
# Triggered when configuration changes via Web UI, REST API, or Python code
@config.on_change("target_temp")
def on_target_temp_change(new_val, old_val):
    print(f"[Hardware] Target temperature updated: {old_val}°C -> {new_val}°C")

@config.on_change("auto_vent")
def on_vent_toggle(new_val, old_val):
    print(f"[Hardware] Ventilation mode set to: {'ENABLED' if new_val else 'DISABLED'}")

# 5. Build Dashboard Tabs
tab_status = app.tab("Telemetry", icon="activity")
tab_status.metric("Target Temp", value=config.target_temp, unit="°C", badge="Setpoint")

# 6. Add Schema-Driven Settings Form
tab_settings = app.tab("Settings", icon="sliders")
tab_settings.config_form(config, label="System Configuration")

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
    print("==================================================")
    print(f" Loaded node_name:   {config.node_name}")
    print(f" Loaded sample_rate: {config.sample_rate}s")
    print(f" Loaded target_temp: {config.target_temp}°C")
    print(f" Dashboard URL:      http://{ip}:80/")
    print(f" (Open http://{ip}:80/ in Safari on your Mac/Phone)")
    print("==================================================")
    app.run(port=80)
