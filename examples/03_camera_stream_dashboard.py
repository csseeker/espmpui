"""
Example 03: ESP32-S3 Camera Viewfinder & Remote Controller
Combines the CameraStream widget with lighting/exposure controls and telemetry.
"""
try:
    import espmpui
except ImportError:
    import sys
    import os
    if hasattr(os, "path"):
        sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))
    import espmpui

# Hardware Camera & LED initialization
has_camera = False
try:
    import camera
    camera.init(0, format=camera.JPEG, framesize=camera.FRAME_QVGA)
    has_camera = True
except Exception:
    pass

# 1. Initialize espmpui
app = espmpui.App(title="ESP32-S3 AI Cam Node", theme="dark")

tab_cam = app.tab("Live Camera", icon="camera")
tab_ctrl = app.tab("Camera Settings", icon="sliders")

# 2. Add Live Viewfinder Widget
viewfinder = tab_cam.camera(
    "OV3660 Live View",
    stream_url="/stream",
    snapshot_url="/snapshot"
)

# 3. Add Control Widgets
tab_ctrl.switch(
    "Flash Torch (GPIO 4)",
    value=False,
    on_change=lambda w, val: print(f"[Cam] Flash torch set to {val}")
)

tab_ctrl.slider(
    "Exposure Quality",
    min=10, max=63, step=1, value=12,
    on_change=lambda w, val: print(f"[Cam] Quality adjusted to {val}")
)

tab_ctrl.button(
    "Trigger High-Res Snap",
    text="📸 Capture to Flash",
    accent="danger",
    on_click=lambda w: print("[Cam] Captured high-resolution photo!")
)

if __name__ == "__main__":
    print("Camera dashboard starting on http://0.0.0.0:80 ...")
    app.run(port=80)
