"""
Example 06: Live System Diagnostics & Administrative Dashboard
Demonstrates zero-setup heap monitoring, GC optimization, flash usage, and remote reboot.
"""

try:
    import espmui
except ImportError:
    import os
    import sys
    if hasattr(os, "path"):
        sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))
    import espmui

# 1. Initialize Application
app = espmui.App(title="S3 Industrial Node", theme="dark")

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

if __name__ == "__main__":
    metrics = diag.get_metrics()
    print("==================================================")
    print(f" Platform:   {metrics['platform']} ({metrics['implementation']})")
    print(f" CPU Clock:  {metrics['cpu_freq_mhz']} MHz")
    print(f" Free RAM:   {metrics['heap']['free_kb']} KB / {metrics['heap']['total_kb']} KB")
    print(f" Flash Free: {metrics['flash']['free']} KB / {metrics['flash']['total']} KB")
    print(" Live Diagnostics active at http://localhost:80/")
    print("==================================================")
    app.run(port=80)
