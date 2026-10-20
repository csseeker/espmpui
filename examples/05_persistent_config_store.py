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

if __name__ == "__main__":
    print("==================================================")
    print(f" Loaded node_name:   {config.node_name}")
    print(f" Loaded sample_rate: {config.sample_rate}s")
    print(f" Loaded target_temp: {config.target_temp}°C")
    print(" Open http://localhost:80/ in your browser to tune settings.")
    print("==================================================")
    app.run(port=80)
