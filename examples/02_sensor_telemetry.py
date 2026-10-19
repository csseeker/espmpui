"""
Example 02: Flagship Multi-Tab Sensor Telemetry & Actuator Station
Features:
- Dedicated tabs for every sensor and onboard hardware functionality:
  * 🌡️ Sensors: MCU Core Temperature, CPU Frequency, System Uptime, Live Temp Graph
  * 🧠 Memory: Octal PSRAM + Heap telemetry, utilization progress, memory chart, Force GC
  * 📶 Wi-Fi: RSSI signal strength, link quality, IP address, MAC, connection testing
  * 💡 RGB LED: WS2812 NeoPixel (GPIO 48) color/brightness sliders, presets, GPIO 4 Torch
  * 📷 Camera: OmniVision OV3660 live viewfinder, snapshot capture, hardware status
  * 🗄️ Storage: Flash LittleFS storage total, used, free, utilization progress
  * 💻 Diagnostics: Live scrolling web terminal, system reboot control
- 100% Non-blocking cooperative async with real hardware drivers and off-board fallbacks.
"""

import gc
import math
import os
import sys
import time

try:
    import uasyncio as asyncio
except ImportError:
    import asyncio

try:
    import espmui
except ImportError:
    if hasattr(os, "path"):
        sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))
    import espmui

# ==============================================================================
# Hardware Peripheral Setup & Safe Probing
# ==============================================================================

# 1. CPU Frequency & Architecture
try:
    import machine
    CPU_FREQ_MHZ = machine.freq() // 1000000
except Exception:
    CPU_FREQ_MHZ = 240

# 2. MCU Temperature Sensor
def get_die_temperature():
    try:
        import esp32
        if hasattr(esp32, "mcu_temperature"):
            return round(esp32.mcu_temperature(), 1)
        return round((esp32.raw_temperature() - 32) * 5 / 9, 1)
    except Exception:
        # Simulated thermal cycle with minor sinusoidal jitter
        t = time.time()
        return round(34.0 + 3.5 * math.sin(t / 8.0) + 0.3 * math.sin(t), 1)

# 3. Heap & Octal PSRAM Memory
def get_free_kb():
    try:
        return gc.mem_free() // 1024
    except Exception:
        return 7840

def get_alloc_kb():
    try:
        return gc.mem_alloc() // 1024
    except Exception:
        return 480

# 4. Storage & SD Card Telemetry
_sd_card_obj = None
_sd_mounted = False
_sd_probed = False

_sd_last_error = ""

def init_sdcard():
    global _sd_card_obj, _sd_mounted, _sd_probed, _sd_last_error
    _sd_probed = True
    if _sd_mounted:
        return True

    import machine

    strategies = [
        # Strategy A: SDMMC Slot 1 with native pin arguments (sck=39, cmd=38, data=(40,))
        ("SDMMC Slot 1 (sck=39, cmd=38, data=[40])", lambda: machine.SDCard(slot=1, width=1, sck=39, cmd=38, data=(40,))),
        # Strategy B: SDMMC Slot 1 with Pin objects
        ("SDMMC Slot 1 (Pin objs)", lambda: machine.SDCard(slot=1, width=1, sck=machine.Pin(39), cmd=machine.Pin(38), data=(machine.Pin(40),))),
        # Strategy C: SDMMC Slot 0 with pin arguments
        ("SDMMC Slot 0 (sck=39, cmd=38, data=[40])", lambda: machine.SDCard(slot=0, width=1, sck=39, cmd=38, data=(40,))),
        # Strategy D: SDMMC Slot 1 with GPIO Matrix register override (CCLK=172, CCMD=178, D0=180)
        ("SDMMC Slot 1 (Matrix Remap)", None),
        # Strategy E: SPI mode on Slot 2 (if hardware supports SPI fallback)
        ("SPI Slot 2 (sck=39, mosi=38, miso=40)", lambda: machine.SDCard(slot=2, sck=machine.Pin(39), mosi=machine.Pin(38), miso=machine.Pin(40), cs=machine.Pin(47))),
    ]

    for name, init_fn in strategies:
        _sd = None
        try:
            if init_fn is not None:
                _sd = init_fn()
            else:
                # Direct GPIO Matrix mapping for Freenove ESP32-S3 SDMMC Slot 1
                # Pin 39 = SDMMC_CLK (out sig 172)
                # Pin 38 = SDMMC_CMD (out sig 178, in sig 178)
                # Pin 40 = SDMMC_D0  (out sig 180, in sig 180)
                _ = machine.Pin(39, machine.Pin.OUT)
                _ = machine.Pin(38, machine.Pin.OUT)
                _ = machine.Pin(40, machine.Pin.IN, machine.Pin.PULL_UP)
                machine.mem32[0x60004554 + 4 * 39] = 172  # GPIO_FUNC39_OUT_SEL
                machine.mem32[0x60004554 + 4 * 38] = 178  # GPIO_FUNC38_OUT_SEL
                machine.mem32[0x60004554 + 4 * 40] = 180  # GPIO_FUNC40_OUT_SEL
                # GPIO input matrix configuration for ESP32-S3:
                # Reg for signal S is 0x60004154 + 4 * (S - 36)
                machine.mem32[0x60004154 + 4 * (178 - 36)] = 0x80 | 38  # CCMD_IN_1
                machine.mem32[0x60004154 + 4 * (180 - 36)] = 0x80 | 40  # CDATA_IN_10
                _sd = machine.SDCard(slot=1, width=1)
                # Re-verify GPIO matrix after host init
                machine.mem32[0x60004554 + 4 * 39] = 172
                machine.mem32[0x60004554 + 4 * 38] = 178
                machine.mem32[0x60004554 + 4 * 40] = 180
                machine.mem32[0x60004154 + 4 * (178 - 36)] = 0x80 | 38
                machine.mem32[0x60004154 + 4 * (180 - 36)] = 0x80 | 40

            os.mount(_sd, "/sd")
            _sd_card_obj = _sd
            _sd_mounted = True
            _sd_last_error = f"Success ({name})"
            print(f"[SD Card] Successfully mounted via {name}")
            return True
        except Exception as exc:
            _sd_last_error = f"{name}: {exc}"
            print(f"[SD Card] {name} failed: {exc}")
            if _sd is not None and hasattr(_sd, "deinit"):
                try:
                    _sd.deinit()
                except Exception:
                    pass

    _sd_mounted = False
    return False

def get_sdcard_stats():
    global _sd_mounted, _sd_probed
    if not _sd_probed:
        init_sdcard()

    if not _sd_mounted:
        return {"mounted": False, "total_gb": 0, "free_gb": 0, "pct": 0}

    try:
        st_sd = os.statvfs("/sd")
        st_root = os.statvfs("/")
        if st_sd == st_root:
            _sd_mounted = False
            return {"mounted": False, "total_gb": 0, "free_gb": 0, "pct": 0}

        bsize = st_sd[0]
        total_mb = (bsize * st_sd[2]) // (1024 * 1024)
        free_mb = (bsize * st_sd[3]) // (1024 * 1024)
        used_mb = max(0, total_mb - free_mb)
        pct = round((used_mb / total_mb) * 100, 1) if total_mb else 0
        return {
            "mounted": True,
            "total_gb": round(total_mb / 1024, 2),
            "free_gb": round(free_mb / 1024, 2),
            "pct": pct
        }
    except Exception:
        _sd_mounted = False
        return {"mounted": False, "total_gb": 0, "free_gb": 0, "pct": 0}

def get_storage_stats():
    try:
        st = os.statvfs('/')
        bsize = st[0]
        total_kb = (bsize * st[2]) // 1024
        free_kb = (bsize * st[3]) // 1024
        used_kb = max(0, total_kb - free_kb)
        pct = round((used_kb / total_kb) * 100, 1) if total_kb else 0
        return total_kb, used_kb, free_kb, pct
    except Exception:
        return 16384, 4120, 12264, 25.1

# 5. Onboard WS2812 NeoPixel (GPIO 48) & Flash Torch (GPIO 4)
PIN_RGB = 48
PIN_TORCH = 4
rgb_pixel = None
torch_pin = None

try:
    from machine import Pin
    torch_pin = Pin(PIN_TORCH, Pin.OUT, value=0)
except Exception:
    pass

try:
    from machine import Pin
    import neopixel
    rgb_pixel = neopixel.NeoPixel(Pin(PIN_RGB), 1)
    rgb_pixel[0] = (0, 0, 0)
    rgb_pixel.write()
except Exception:
    pass

led_state = {
    "power": False,
    "brightness": 50,
    "r": 0,
    "g": 230,
    "b": 255
}

def apply_neopixel():
    if not rgb_pixel:
        return
    if not led_state["power"]:
        rgb_pixel[0] = (0, 0, 0)
    else:
        scale = (led_state["brightness"] / 100.0)
        r = int(led_state["r"] * scale)
        g = int(led_state["g"] * scale)
        b = int(led_state["b"] * scale)
        rgb_pixel[0] = (r, g, b)
    try:
        rgb_pixel.write()
    except Exception:
        pass

# 6. Camera Subsystem (OmniVision OV3660)
has_camera_hardware = False
camera_sensor_name = "Not Detected"
cam_inst = None
cam_encoder = None
cam_width = 320
cam_height = 240
cam_rgb888_buf = None

# Minimal fallback JPEG image (1x1 pixel)
FALLBACK_JPEG = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00"
    b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c"
    b"\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c"
    b"\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342\xff\xc0\x00\x0b\x08\x00\x01"
    b"\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01"
    b"\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08"
    b"\t\n\x0b\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xbf\x80\xff\xd9"
)

try:
    import camera
    import jpeg

    @micropython.viper
    def rgb565_to_rgb888_fast(src_buf, dst_buf, num_pixels: int):
        src = ptr16(src_buf)
        dst = ptr8(dst_buf)
        for i in range(num_pixels):
            p = int(src[i])
            p = ((p & 0xFF) << 8) | ((p >> 8) & 0xFF)
            r = (p >> 11) & 0x1F
            g = (p >> 5) & 0x3F
            b = p & 0x1F
            dst[i * 3 + 0] = (r * 527 + 23) >> 6
            dst[i * 3 + 1] = (g * 259 + 33) >> 6
            dst[i * 3 + 2] = (b * 527 + 23) >> 6

    try:
        cam_inst = camera.Camera(
            pixel_format=camera.PixelFormat.RGB565,
            frame_size=camera.FrameSize.QVGA,
            fb_count=2,
            grab_mode=camera.GrabMode.LATEST
        )
        time.sleep_ms(100)
        cam_width = cam_inst.get_pixel_width()
        cam_height = cam_inst.get_pixel_height()
        camera_sensor_name = cam_inst.get_sensor_name() or "OV3660"
        cam_rgb888_buf = bytearray(cam_width * cam_height * 3)
        cam_encoder = jpeg.Encoder(width=cam_width, height=cam_height, pixel_format="RGB888", quality=80)
        has_camera_hardware = True
    except Exception:
        # Fallback to standard ESP-IDF camera if custom driver is inactive
        try:
            camera.init(0, format=camera.JPEG, framesize=camera.FRAME_QVGA)
            has_camera_hardware = True
            camera_sensor_name = "OV3660"
        except Exception:
            pass
except Exception:
    pass

def capture_jpeg_frame():
    """Captures and compresses an image frame."""
    if cam_inst and cam_encoder and cam_rgb888_buf:
        try:
            raw = cam_inst.capture()
            if raw:
                rgb565_to_rgb888_fast(raw, cam_rgb888_buf, cam_width * cam_height)
                return cam_encoder.encode(cam_rgb888_buf)
        except Exception:
            pass
    try:
        import camera
        if hasattr(camera, "capture"):
            frame = camera.capture()
            if frame:
                return frame
    except Exception:
        pass
    return FALLBACK_JPEG

# 7. Wi-Fi & Network Status
_CACHED_MAC = None

def get_network_info():
    global _CACHED_MAC
    try:
        import network
        import ubinascii
        wlan = network.WLAN(network.STA_IF)
        if wlan.isconnected():
            rssi = wlan.status('rssi')
            ip = wlan.ifconfig()[0]
            if _CACHED_MAC is None:
                _CACHED_MAC = ubinascii.hexlify(wlan.config('mac'), ':').decode()
            quality = max(0, min(100, 2 * (rssi + 100)))
            return "Connected", rssi, quality, ip, _CACHED_MAC
    except Exception:
        pass
    return "Offline / AP", -65, 70, "127.0.0.1", "7c:e8:b1:a6:91:50"

# Uptime Tracker
START_TICKS = time.ticks_ms()
def get_uptime_str():
    try:
        diff_s = time.ticks_diff(time.ticks_ms(), START_TICKS) // 1000
    except Exception:
        diff_s = int(time.time())
    hrs = diff_s // 3600
    mins = (diff_s % 3600) // 60
    secs = diff_s % 60
    if hrs > 0:
        return f"{hrs}h {mins}m {secs}s"
    elif mins > 0:
        return f"{mins}m {secs}s"
    return f"{secs}s"


# ==============================================================================
# Construct espmui Tabbed Application
# ==============================================================================
try:
    app = espmui.App(title="ESP32-S3 IoT Node", theme="dark", tab_layout="vertical")
except TypeError:
    app = espmui.App(title="ESP32-S3 IoT Node", theme="dark")
    if hasattr(app, "tab_layout"):
        app.tab_layout = "vertical"

# ------------------------------------------------------------------------------
# TAB 1: 🌡️ Sensors & Environmental Telemetry
# ------------------------------------------------------------------------------
tab_sensors = app.tab("Sensors", icon="sensor")
temp_metric = tab_sensors.metric("MCU Core Temperature", value="--", unit="°C", badge="Optimal")
freq_metric = tab_sensors.metric("CPU Clock Speed", value=str(CPU_FREQ_MHZ), unit="MHz", badge="Dual-Core LX7")
uptime_metric = tab_sensors.metric("System Uptime", value="0s", unit="", badge="Live")
chart_temp = tab_sensors.chart("Live Core Temperature Trend", max_points=30, unit="°C", color="#38bdf8")

# ------------------------------------------------------------------------------
# TAB 2: 🧠 Memory Subsystem & Octal PSRAM
# ------------------------------------------------------------------------------
tab_mem = app.tab("Memory", icon="cpu")
mem_metric = tab_mem.metric("Free Heap Memory", value="--", unit="KB", badge="Octal PSRAM")
alloc_metric = tab_mem.metric("Allocated Memory", value="--", unit="KB")
mem_progress = tab_mem.progress("Available Heap Capacity", max=8192, unit="KB", value=0)
chart_mem = tab_mem.chart("Free Heap History (KB)", max_points=30, unit="KB", color="#10b981")

async def on_gc_click(w):
    before = gc.mem_free() // 1024
    gc.collect()
    after = gc.mem_free() // 1024
    reclaimed = max(0, after - before)
    mem_metric.value = after
    mem_progress.value = after
    alloc_metric.value = get_alloc_kb()
    msg = f"Reclaimed {reclaimed} KB (Total Free: {after} KB)"
    terminal.log(f"[Memory] GC: {msg}")
    await app._broadcast_toast(f"🧹 {msg}", level="info")

tab_mem.button("", text="🧹 Force Garbage Collection (gc.collect)", accent="success", on_click=on_gc_click)

# ------------------------------------------------------------------------------
# TAB 3: 📶 Wi-Fi & Network Telemetry
# ------------------------------------------------------------------------------
tab_wifi = app.tab("Wi-Fi", icon="wifi")
wifi_status_metric = tab_wifi.metric("Connection State", value="Connecting...", badge="Station")
wifi_rssi_metric = tab_wifi.metric("Signal Strength (RSSI)", value="--", unit="dBm")
wifi_prog = tab_wifi.progress("Link Signal Quality", max=100, unit="%", value=0)
wifi_ip_metric = tab_wifi.metric("Local IP Address", value="--")
wifi_mac_metric = tab_wifi.metric("Hardware MAC Address", value="7c:e8:b1:a6:91:50")

async def on_ping_click(w):
    status, rssi, quality, ip, mac = get_network_info()
    terminal.log(f"[Network] Link Check: {status} | IP: {ip} | RSSI: {rssi} dBm")
    await app._broadcast_toast(f"Link Status: {status} ({rssi} dBm)", level="info")

tab_wifi.button("", text="🔄 Verify Network Link", accent="secondary", on_click=on_ping_click)

# ------------------------------------------------------------------------------
# TAB 4: 💡 RGB LED & Actuators
# ------------------------------------------------------------------------------
tab_led = app.tab("RGB LED", icon="light")

def on_power_change(w, val):
    led_state["power"] = bool(val)
    apply_neopixel()
    terminal.log(f"[Actuator] NeoPixel GPIO 48: {'ON' if val else 'OFF'}")

sw_power = tab_led.switch("WS2812 NeoPixel (GPIO 48) Power", value=False, on_change=on_power_change)

def on_bright_change(w, val):
    led_state["brightness"] = int(val)
    apply_neopixel()

sl_bright = tab_led.slider("Master Brightness", min=0, max=100, step=5, value=50, on_change=on_bright_change)

def on_red_change(w, val):
    led_state["r"] = int(val)
    apply_neopixel()

def on_green_change(w, val):
    led_state["g"] = int(val)
    apply_neopixel()

def on_blue_change(w, val):
    led_state["b"] = int(val)
    apply_neopixel()

sl_red = tab_led.slider("Red Channel", min=0, max=255, step=5, value=0, on_change=on_red_change)
sl_green = tab_led.slider("Green Channel", min=0, max=255, step=5, value=230, on_change=on_green_change)
sl_blue = tab_led.slider("Blue Channel", min=0, max=255, step=5, value=255, on_change=on_blue_change)

async def apply_preset(r, g, b, name):
    led_state["power"] = True
    led_state["r"] = r
    led_state["g"] = g
    led_state["b"] = b
    sw_power.value = True
    sl_red.value = r
    sl_green.value = g
    sl_blue.value = b
    apply_neopixel()
    terminal.log(f"[Actuator] NeoPixel Preset: {name} ({r}, {g}, {b})")
    await app._broadcast_toast(f"RGB Preset: {name}", level="info")

tab_led.button("", text="🔵 Cyber Cyan Preset", accent="accent", on_click=lambda w: apply_preset(0, 230, 255, "Cyber Cyan"))
tab_led.button("", text="🟢 Emerald Green Preset", accent="success", on_click=lambda w: apply_preset(0, 255, 60, "Emerald Green"))
tab_led.button("", text="🔴 Coral Red Preset", accent="danger", on_click=lambda w: apply_preset(255, 40, 40, "Coral Red"))
tab_led.button("", text="🟣 Neon Violet Preset", accent="accent", on_click=lambda w: apply_preset(190, 40, 255, "Neon Violet"))

def on_torch_change(w, val):
    if torch_pin:
        try:
            torch_pin.value(1 if val else 0)
        except Exception:
            pass
    terminal.log(f"[Actuator] Flash Torch (GPIO 4): {'ON' if val else 'OFF'}")

tab_led.switch("Flash Torch (GPIO 4)", value=False, on_change=on_torch_change)

# ------------------------------------------------------------------------------
# TAB 5: 📷 Camera Sensor & Live Viewfinder
# ------------------------------------------------------------------------------
tab_cam = app.tab("Camera", icon="camera")
viewfinder = tab_cam.camera(
    "OmniVision OV3660 Viewfinder",
    stream_url="/stream",
    snapshot_url="/snapshot"
)
cam_status_metric = tab_cam.metric(
    "Camera Hardware Sensor",
    value=camera_sensor_name,
    unit="",
    badge="QVGA 320x240" if has_camera_hardware else "Standby"
)

async def on_save_snapshot_click(w):
    filename = "captured_snapshot.jpg"
    frame = capture_jpeg_frame()
    if frame:
        try:
            with open(filename, "wb") as f:
                f.write(frame)
            stat = os.stat(filename)
            terminal.log(f"[Camera] Saved photo '{filename}' ({stat[6]} bytes)")
            await app._broadcast_toast(f"Photo saved ({stat[6]} bytes)", level="info")
        except Exception as e:
            terminal.log(f"[Camera Error] {e}")
            await app._broadcast_toast(f"Save error: {e}", level="error")
    else:
        await app._broadcast_toast("No camera frame available", level="error")

tab_cam.button("", text="📸 Save Snapshot to Flash Storage", accent="primary", on_click=on_save_snapshot_click)

# Snapshot HTTP endpoint route
@app.route("/snapshot")
async def handle_snapshot_http(reader, writer, path, headers):
    frame = capture_jpeg_frame()
    if not frame:
        frame = FALLBACK_JPEG
    header = (
        "HTTP/1.1 200 OK\r\n"
        "Content-Type: image/jpeg\r\n"
        f"Content-Length: {len(frame)}\r\n"
        "Connection: close\r\n"
        "Cache-Control: no-cache, no-store, must-revalidate\r\n\r\n"
    ).encode("ascii")
    writer.write(header)
    writer.write(frame)
    await writer.drain()

# ------------------------------------------------------------------------------
# TAB 6: 🗄️ Storage: Flash (LittleFS) & MicroSD Card (FAT32)
# ------------------------------------------------------------------------------
tab_storage = app.tab("Storage", icon="storage")
flash_free_metric = tab_storage.metric("Available Flash Storage", value="--", unit="KB", badge="LittleFS")
flash_used_metric = tab_storage.metric("Used Flash Storage", value="--", unit="KB")
flash_prog = tab_storage.progress("Flash Storage Utilization", max=100, unit="%", value=0)

# MicroSD Card Subsystem (Auto-detects when inserted)
sd_status_metric = tab_storage.metric("MicroSD Card Status", value="Not Inserted", unit="", badge="Standby")
sd_free_metric = tab_storage.metric("Available SD Storage", value="--", unit="GB")
sd_prog = tab_storage.progress("SD Card Utilization", max=100, unit="%", value=0)
sd_files = tab_storage.file_manager("SD Card File Explorer (/sd)", root_path="/sd")

async def on_mount_sd_click(w):
    global _sd_mounted, _sd_probed, _sd_last_error
    _sd_mounted = False
    _sd_probed = False
    terminal.log("[SD Card] Probing MicroSD (CMD=38, CLK=39, D0=40)...")
    if init_sdcard():
        info = get_sdcard_stats()
        sd_status_metric.value = "Mounted (FAT32)"
        sd_status_metric.badge = f"{info['total_gb']} GB"
        sd_free_metric.value = str(info['free_gb'])
        sd_prog.value = info['pct']
        sd_files.refresh()
        terminal.log(f"[SD Card] ✅ Successfully mounted! Capacity: {info['total_gb']} GB")
        terminal.log(f"[SD Card] Strategy: {_sd_last_error}")
        await app._broadcast_toast(f"SD Card Mounted ({info['total_gb']} GB)", level="info")
    else:
        sd_status_metric.value = "Not Inserted"
        sd_status_metric.badge = "Standby"
        sd_free_metric.value = "--"
        sd_prog.value = 0
        terminal.log(f"[SD Card] ❌ Mount failed: {_sd_last_error}")
        await app._broadcast_toast(f"SD mount failed: {_sd_last_error}", level="error")

tab_storage.button("", text="🔍 Scan & Mount SD Card", accent="primary", on_click=on_mount_sd_click)

# ------------------------------------------------------------------------------
# TAB 7: 💻 Diagnostics, Event Log & System Power
# ------------------------------------------------------------------------------
tab_logs = app.tab("Diagnostics", icon="terminal")
terminal = tab_logs.terminal("Live System Telemetry Stream", max_lines=75)

async def on_reboot_click(w):
    terminal.log("[System] Reboot command received! Restarting MCU...")
    await app._broadcast_toast("Rebooting ESP32 in 1 second...", level="error")
    await asyncio.sleep(1)
    try:
        from machine import reset
        reset()
    except Exception:
        terminal.log("[System] Simulated software reset (host environment)")

tab_logs.button("", text="⚠️ Reboot ESP32 MCU", accent="danger", on_click=on_reboot_click)


# ==============================================================================
# Non-Blocking Background Sensor Loop
# ==============================================================================
async def sensor_loop():
    terminal.log("[System] espmui multi-tab telemetry engine online.")
    terminal.log(f"[Hardware] ESP32-S3 @ {CPU_FREQ_MHZ}MHz | Octal PSRAM: 8MB")
    if has_camera_hardware:
        terminal.log(f"[Camera] {camera_sensor_name} sensor online over DVP bus.")

    cycle = 0
    while True:
        cycle += 1
        # Run periodic garbage collection to reclaim transient strings & buffers
        if cycle % 2 == 1:
            gc.collect()

        temp = get_die_temperature()
        free_kb = get_free_kb()
        alloc_kb = get_alloc_kb()
        uptime = get_uptime_str()

        # Update Tab 1: Sensors
        temp_metric.value = temp
        temp_metric.badge = "Optimal" if temp < 55 else "Elevated"
        uptime_metric.value = uptime
        chart_temp.add_point(temp)

        # Update Tab 2: Memory
        mem_metric.value = free_kb
        alloc_metric.value = alloc_kb
        mem_progress.value = free_kb
        chart_mem.add_point(free_kb)

        # Update Tab 3: Wi-Fi (every 2 cycles)
        if cycle % 2 == 1:
            status, rssi, quality, ip, mac = get_network_info()
            wifi_status_metric.value = status
            wifi_status_metric.badge = f"{rssi} dBm" if status == "Connected" else "Standby"
            wifi_rssi_metric.value = rssi
            wifi_prog.value = quality
            wifi_ip_metric.value = ip
            wifi_mac_metric.value = mac

        # Update Tab 6: Storage & SD Card (every 5 cycles)
        if cycle % 5 == 1:
            tot, used, free_s, pct = get_storage_stats()
            flash_free_metric.value = free_s
            flash_used_metric.value = used
            flash_prog.value = pct

            sd_info = get_sdcard_stats()
            if sd_info["mounted"]:
                sd_status_metric.value = "Mounted (FAT32)"
                sd_status_metric.badge = f"{sd_info['total_gb']} GB"
                sd_free_metric.value = str(sd_info["free_gb"])
                sd_prog.value = sd_info["pct"]
            else:
                sd_status_metric.value = "Not Inserted"
                sd_status_metric.badge = "Standby"
                sd_free_metric.value = "--"
                sd_prog.value = 0

        # Log system heartbeat every 10 seconds (5 cycles) to keep terminal buffer light
        if cycle % 5 == 1:
            terminal.log(f"[{uptime}] Core: {temp}°C | Heap: {free_kb}KB free | Uptime: {uptime}")

        await asyncio.sleep(2)


# ==============================================================================
# Wi-Fi Auto-Connector Helper
# ==============================================================================
def connect_wifi():
    try:
        import network
        wlan = network.WLAN(network.STA_IF)
        if not wlan.active():
            wlan.active(True)
        if not wlan.isconnected():
            ssid = ""
            pwd = ""
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
                try:
                    wlan.connect(ssid, pwd)
                except OSError:
                    wlan.active(False)
                    time.sleep(0.5)
                    wlan.active(True)
                    wlan.connect(ssid, pwd)
                for _ in range(25):
                    if wlan.isconnected():
                        break
                    time.sleep(0.4)
        if wlan.isconnected():
            ip = wlan.ifconfig()[0]
            print(f"Connected! Open dashboard at: http://{ip}:80")
            return ip
    except Exception:
        pass
    return "localhost"


# ==============================================================================
# Main Runner
# ==============================================================================
if __name__ == "__main__":
    ip = connect_wifi()
    app.create_task(sensor_loop())
    print("=" * 60)
    print("  espmui Multi-Tab Sensor Telemetry Station")
    print(f"  Live Dashboard: http://{ip}:80")
    print("=" * 60)
    app.run(port=80)
