"""
Example 04: Wi-Fi Provisioner & DNS Captive Portal with espmui
Demonstrates out-of-the-box SoftAP captive portal and zero-friction onboarding.
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
app = espmui.App(title="IoT Gateway Node", theme="dark")

# 2. Add Standard Dashboard Tabs & Controls
tab_status = app.tab("Device Status", icon="activity")
tab_status.metric("System State", value="Provisioning Mode", unit="", badge="SoftAP Active")

tab_controls = app.tab("Controls", icon="sliders")
tab_controls.switch("Relay Output", value=False, on_change=lambda w, v: print(f"Relay toggled: {v}"))

# 3. Enable Captive Portal & Wi-Fi Provisioner
# Automatically starts SoftAP, intercepts DNS (port 53), redirects captive probes
# (/generate_204, /hotspot-detect.html, /ncsi.txt), and serves the mobile-first setup view.
portal = app.enable_captive_portal(
    ap_ssid="espmui-Setup",
    ap_password=None,       # Open AP for initial setup (or set password)
    ap_ip="192.168.4.1"     # Standard default gateway
)

if __name__ == "__main__":
    print("==================================================")
    print(" espmui Wi-Fi Provisioner & Captive Portal Active")
    print("==================================================")
    print(" 1. Connect smartphone to Wi-Fi SSID: 'espmui-Setup'")
    print(" 2. Device automatically pops up the captive portal")
    print("    Or manually browse to: http://192.168.4.1/")
    print("==================================================")
    app.run(port=80)
