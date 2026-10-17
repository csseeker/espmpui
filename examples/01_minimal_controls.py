"""
Example 01: Minimal Hardware Controls with espmui
Demonstrates a clean, 15-line declarative web dashboard for ESP32.
"""

try:
    import espmui
except ImportError:
    import sys, os
    if hasattr(os, "path"):
        sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))
    import espmui

# Hardware Setup (fallback to mock if running on PC)
try:
    from machine import Pin
    led = Pin(4, Pin.OUT, value=0)
except ImportError:
    class MockPin:
        def value(self, v=None):
            if v is not None:
                print(f"[Hardware] LED set to {v}")
    led = MockPin()

# 1. Create espmui Application
app = espmui.App(title="S3 Hardware Controller", theme="dark")

# 2. Add Tab
tab = app.tab("Controls", icon="sliders")

# 3. Add Interactive Widgets
tab.button(
    "Test Pulse", 
    text="Trigger Pulse", 
    accent="danger",
    on_click=lambda w: print("[App] Button clicked!")
)

tab.switch(
    "Main LED (Pin 4)", 
    value=False, 
    on_change=lambda w, val: led.value(1 if val else 0)
)

tab.slider(
    "Motor Speed", 
    min=0, max=100, step=5, value=25,
    on_change=lambda w, val: print(f"[App] Motor speed adjusted to: {val}%")
)

# 4. Start Dashboard Server
if __name__ == "__main__":
    print("Starting espmui server on http://0.0.0.0:80 ...")
    app.run(port=80)
