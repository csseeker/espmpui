"""
Live Diagnostics & System Telemetry Subsystem for espmpui.
Tracks free heap, GC fragmentation, filesystem usage, Wi-Fi RSSI, and CPU telemetry.
Provides out-of-the-box administrative controls (manual GC, safe soft reboot).
"""

import gc
import json
import os
import sys
import time

try:
    import uasyncio as asyncio
except ImportError:
    import asyncio

def print_exception(exc):
    """Prints exception traceback on both MicroPython and standard Python."""
    if hasattr(sys, "print_exception"):
        sys.print_exception(exc)
    else:
        import traceback
        traceback.print_exception(exc)


def format_uptime(seconds: int) -> str:
    """Formats seconds into readable uptime string (e.g. '1d 2h 15m 30s')."""
    seconds = int(seconds)
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)

    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if secs > 0 or not parts:
        parts.append(f"{secs}s")

    return " ".join(parts)


class SystemDiagnostics:
    """
    Live system telemetry collector and administrative controller.
    """

    def __init__(self, app=None, tab_title: str = "System Health", tab_icon: str = "cpu"):
        self.app = app
        self.tab_title = tab_title
        self.tab_icon = tab_icon
        self._start_time = time.time()
        self._start_ticks = time.ticks_ms() if hasattr(time, "ticks_ms") else None
        self._telemetry_task = None
        self._running = False
        self._reboot_fn = self._default_reboot

        # Cache initial flash capacity
        self._flash_total_kb, self._flash_free_kb = self._read_flash_storage()

        # UI Widgets (populated if attached to App)
        self.tab = None
        self.heap_widget = None
        self.flash_widget = None
        self.uptime_widget = None
        self.rssi_widget = None
        self.cpu_widget = None

        if self.app:
            self._setup_ui()
            self._register_rest_routes()

    def get_uptime_seconds(self) -> int:
        """Returns uptime in seconds with rollover handling."""
        if self._start_ticks is not None and hasattr(time, "ticks_ms") and hasattr(time, "ticks_diff"):
            now_ticks = time.ticks_ms()
            elapsed_ms = time.ticks_diff(now_ticks, self._start_ticks)
            return max(0, elapsed_ms // 1000)
        return max(0, int(time.time() - self._start_time))

    def _get_heap_metrics(self) -> dict:
        """Collects MicroPython heap telemetry or realistic desktop mock."""
        if hasattr(gc, "mem_free") and hasattr(gc, "mem_alloc"):
            free = gc.mem_free()
            alloc = gc.mem_alloc()
        else:
            # Desktop simulation (standard ESP32-S3 heap envelope)
            alloc = 128 * 1024
            free = 192 * 1024

        total = alloc + free
        pct_free = round((free / total) * 100, 1) if total > 0 else 0
        return {
            "free": free,
            "alloc": alloc,
            "total": total,
            "pct_free": pct_free,
            "free_kb": free // 1024,
            "alloc_kb": alloc // 1024,
            "total_kb": total // 1024,
        }

    def _read_flash_storage(self):
        """Reads total and free filesystem flash storage in KB."""
        try:
            if hasattr(os, "statvfs"):
                st = os.statvfs("/")
                bsize = st[0]
                blocks = st[2]
                bavail = st[4]
                total_kb = (blocks * bsize) // 1024
                free_kb = (bavail * bsize) // 1024
                return max(1, total_kb), max(0, free_kb)
        except Exception:
            pass
        # Fallback default (4 MB Flash)
        return 4096, 2048

    def _get_wifi_rssi(self):
        """Returns current Wi-Fi RSSI in dBm if connected."""
        try:
            import network
            sta = network.WLAN(network.STA_IF)
            if sta.isconnected() and hasattr(sta, "status"):
                return sta.status("rssi")
        except Exception:
            pass
        return None

    def _get_cpu_freq_mhz(self) -> int:
        """Returns CPU frequency in MHz."""
        try:
            import machine
            if hasattr(machine, "freq"):
                return machine.freq() // 1000000
        except Exception:
            pass
        return 240  # Standard ESP32 default

    def get_metrics(self) -> dict:
        """Collects complete real-time diagnostic telemetry dictionary."""
        heap = self._get_heap_metrics()
        total_kb, free_kb = self._read_flash_storage()
        used_kb = max(0, total_kb - free_kb)
        pct_used = round((used_kb / total_kb) * 100, 1) if total_kb > 0 else 0

        uptime_s = self.get_uptime_seconds()
        rssi = self._get_wifi_rssi()
        freq = self._get_cpu_freq_mhz()

        impl = getattr(sys, "implementation", None)
        impl_name = impl.name if impl else "cpython"

        return {
            "heap": heap,
            "flash": {
                "total": total_kb,
                "free": free_kb,
                "used": used_kb,
                "pct_used": pct_used,
            },
            "uptime_sec": uptime_s,
            "uptime_str": format_uptime(uptime_s),
            "rssi": rssi,
            "cpu_freq_mhz": freq,
            "platform": sys.platform,
            "implementation": impl_name,
        }

    def collect_garbage(self) -> dict:
        """Triggers manual garbage collection and returns freed memory statistics."""
        before = gc.mem_free() if hasattr(gc, "mem_free") else 192 * 1024
        gc.collect()
        after = gc.mem_free() if hasattr(gc, "mem_free") else (192 * 1024 + 4096)
        freed = max(0, after - before)

        heap = self._get_heap_metrics()
        return {
            "status": "ok",
            "freed_bytes": freed,
            "freed_kb": freed // 1024,
            "heap": heap,
        }

    def _default_reboot(self):
        """Soft resets the microcontroller."""
        try:
            import machine
            machine.reset()
        except Exception:
            pass

    async def schedule_reboot(self, delay_ms: int = 500):
        """Asynchronously waits for response to flush, then invokes soft reset."""
        await asyncio.sleep(delay_ms / 1000.0)
        self._reboot_fn()

    def _setup_ui(self):
        """Creates the System Health navigation tab and telemetry widgets."""
        self.tab = self.app.tab(self.tab_title, icon=self.tab_icon)

        metrics = self.get_metrics()
        heap = metrics["heap"]
        flash = metrics["flash"]

        # 1. RAM / Heap Progress
        self.heap_widget = self.tab.progress(
            "Free Heap / RAM",
            value=heap["free_kb"],
            max=heap["total_kb"],
            unit="KB"
        )

        # 2. Flash Storage Progress
        self.flash_widget = self.tab.progress(
            "Flash Storage",
            value=flash["used"],
            max=flash["total"],
            unit="KB"
        )

        # 3. Uptime Metric
        self.uptime_widget = self.tab.metric(
            "System Uptime",
            value=metrics["uptime_str"],
            badge="Online"
        )

        # 4. CPU & Platform Metric
        self.cpu_widget = self.tab.metric(
            "CPU & Platform",
            value=f"{metrics['cpu_freq_mhz']} MHz",
            badge=metrics["platform"]
        )

        # 5. Maintenance Controls
        async def on_gc_click(w):
            res = self.collect_garbage()
            freed = res["freed_bytes"]
            self.heap_widget.value = res["heap"]["free_kb"]
            if self.app:
                await self.app._broadcast_toast(f"GC Complete: {freed:,} bytes freed", level="info")

        self.tab.button(
            "Memory Optimization",
            text="🧹 Run Garbage Collector",
            accent="accent",
            on_click=on_gc_click
        )

        async def on_reboot_click(w):
            if self.app:
                await self.app._broadcast_toast("Rebooting device...", level="warning")
            asyncio.create_task(self.schedule_reboot(delay_ms=800))

        self.tab.button(
            "Device Maintenance",
            text="⚡ Restart Device",
            accent="danger",
            on_click=on_reboot_click
        )

    def _register_rest_routes(self):
        """Registers administrative REST API endpoints onto App server."""
        async def handle_metrics(reader, writer, path, headers):
            metrics = self.get_metrics()
            payload = json.dumps(metrics).encode("utf-8")
            resp = (
                f"HTTP/1.1 200 OK\r\n"
                f"Content-Type: application/json\r\n"
                f"Content-Length: {len(payload)}\r\n"
                f"Connection: close\r\n\r\n"
            ).encode("ascii") + payload
            writer.write(resp)
            await writer.drain()

        async def handle_gc(reader, writer, path, headers):
            res = self.collect_garbage()
            payload = json.dumps(res).encode("utf-8")
            resp = (
                f"HTTP/1.1 200 OK\r\n"
                f"Content-Type: application/json\r\n"
                f"Content-Length: {len(payload)}\r\n"
                f"Connection: close\r\n\r\n"
            ).encode("ascii") + payload
            writer.write(resp)
            await writer.drain()

        async def handle_reboot(reader, writer, path, headers):
            payload = json.dumps({"status": "rebooting"}).encode("utf-8")
            resp = (
                f"HTTP/1.1 200 OK\r\n"
                f"Content-Type: application/json\r\n"
                f"Content-Length: {len(payload)}\r\n"
                f"Connection: close\r\n\r\n"
            ).encode("ascii") + payload
            writer.write(resp)
            await writer.drain()
            asyncio.create_task(self.schedule_reboot(delay_ms=400))

        self.app.add_route("/api/system/metrics", handle_metrics)
        self.app.add_route("/api/system/gc", handle_gc)
        self.app.add_route("/api/system/reboot", handle_reboot)

    def start_telemetry_loop(self, interval_sec: int = 2):
        """Starts a cooperative background coroutine updating UI widgets."""
        if self._telemetry_task is None:
            self._running = True
            self._telemetry_task = asyncio.create_task(self._poll_loop(interval_sec))
        return self._telemetry_task

    async def _poll_loop(self, interval_sec: int):
        """Cooperative update loop for live widgets."""
        while self._running:
            try:
                metrics = self.get_metrics()
                if self.heap_widget:
                    self.heap_widget.value = metrics["heap"]["free_kb"]
                if self.uptime_widget:
                    self.uptime_widget.value = metrics["uptime_str"]
            except Exception as ex:
                print_exception(ex)
            await asyncio.sleep(interval_sec)

    async def stop(self):
        """Stops background telemetry loop."""
        self._running = False
        if self._telemetry_task:
            self._telemetry_task.cancel()
            try:
                await self._telemetry_task
            except asyncio.CancelledError:
                pass
            self._telemetry_task = None
