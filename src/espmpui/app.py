"""
Application controller, tab hierarchy, and reactive state coordinator for espmpui.
Integrates with AsyncServer and enforces strict fault-isolation barriers.
"""

import json
import sys

try:
    import uasyncio as asyncio
except ImportError:
    import asyncio

from espmpui.server import AsyncServer
from espmpui.widgets import Widget, Button, Switch, Slider, Metric, Progress, is_awaitable, _generate_id

def print_exception(exc):
    """Prints exception traceback on both MicroPython and standard Python."""
    if hasattr(sys, "print_exception"):
        sys.print_exception(exc)
    else:
        import traceback
        traceback.print_exception(exc)


class Tab:
    """Represents a navigation tab containing a set of widgets."""

    def __init__(self, title: str, icon: str = "", id: str = None, app=None):
        self.id = id or _generate_id("tab")
        self.title = title
        self.icon = icon
        self.app = app
        self.widgets = []

    def add_widget(self, widget: Widget) -> Widget:
        widget.app = self.app
        self.widgets.append(widget)
        if self.app:
            self.app._register_widget(widget)
        return widget

    def button(self, label: str, **kwargs) -> Button:
        btn = Button(label, **kwargs)
        return self.add_widget(btn)

    def switch(self, label: str, **kwargs) -> Switch:
        sw = Switch(label, **kwargs)
        return self.add_widget(sw)

    def slider(self, label: str, **kwargs) -> Slider:
        sl = Slider(label, **kwargs)
        return self.add_widget(sl)

    def metric(self, label: str, **kwargs) -> Metric:
        m = Metric(label, **kwargs)
        return self.add_widget(m)

    def progress(self, label: str, **kwargs) -> Progress:
        p = Progress(label, **kwargs)
        return self.add_widget(p)

    def terminal(self, label: str = "System Log", **kwargs):
        from espmpui.iot_widgets import Terminal
        return self.add_widget(Terminal(label, **kwargs))

    def chart(self, label: str, **kwargs):
        from espmpui.iot_widgets import LineChart
        return self.add_widget(LineChart(label, **kwargs))

    def camera(self, label: str = "Camera Live View", **kwargs):
        from espmpui.iot_widgets import CameraStream
        return self.add_widget(CameraStream(label, **kwargs))

    def file_manager(self, label: str = "Flash Storage", **kwargs):
        from espmpui.iot_widgets import FileManager
        return self.add_widget(FileManager(label, **kwargs))

    def config_form(self, config_store, label: str = "Configuration", **kwargs):
        from espmpui.config import ConfigForm
        return self.add_widget(ConfigForm(config_store, label=label, **kwargs))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "icon": self.icon,
            "widgets": [w.to_dict() for w in self.widgets],
        }


class App:
    """The central espmpui dashboard application."""

    def __init__(self, title: str = "espmpui Dashboard", theme: str = "dark", tab_layout: str = "vertical", **kwargs):
        self.title = title
        self.theme = theme
        self.tab_layout = kwargs.get("tab_layout", tab_layout)
        self.tabs = []
        self.widgets_by_id = {}
        self.server = None
        self.portal = None
        self.diagnostics = None
        self._on_diff = None  # Hook for tests or custom observers
        self.tasks = []
        self._custom_routes = {}

    def enable_captive_portal(self, ap_ssid: str = "espmpui-Setup", ap_password: str = None, ap_ip: str = "192.168.4.1", dns_port: int = 53):
        """Configures and activates SoftAP captive portal and Wi-Fi provisioner."""
        from espmpui.wifi import CaptivePortal, WiFiManager
        wifi_mgr = WiFiManager()
        wifi_mgr.start_ap(ssid=ap_ssid, password=ap_password, ip=ap_ip)
        self.portal = CaptivePortal(self.server, wifi_manager=wifi_mgr, ap_ip=ap_ip, dns_port=dns_port)
        if self.server:
            self.portal.attach()
        return self.portal

    def attach_config(self, schema: dict, filepath: str = "config.json", autosave: bool = True):
        """Attaches a persistent configuration store and registers REST endpoints."""
        from espmpui.config import ConfigStore, ConfigValidationError
        store = ConfigStore(schema, filepath=filepath, app=self, autosave=autosave)
        self.config_store = store

        async def _handle_config_endpoint(reader, writer, path, headers):
            method = headers.get("method", "GET").upper()
            if method == "POST":
                content_len = int(headers.get("content-length", 0))
                body = b""
                if content_len > 0:
                    body = await reader.read(content_len)

                try:
                    data = json.loads(body.decode("utf-8"))
                    new_vals = data.get("values", {})
                    store.update(new_vals)
                    resp_dict = {"status": "ok", "values": store.to_dict()}
                    status_line = "HTTP/1.1 200 OK"
                except ConfigValidationError as err:
                    resp_dict = {"status": "error", "message": str(err)}
                    status_line = "HTTP/1.1 400 Bad Request"
                except Exception as ex:
                    resp_dict = {"status": "error", "message": str(ex)}
                    status_line = "HTTP/1.1 400 Bad Request"
            else:
                resp_dict = {
                    "status": "ok",
                    "values": store.to_dict(),
                    "schema": store.schema,
                }
                status_line = "HTTP/1.1 200 OK"

            payload = json.dumps(resp_dict).encode("utf-8")
            resp = (
                f"{status_line}\r\n"
                f"Content-Type: application/json\r\n"
                f"Content-Length: {len(payload)}\r\n"
                f"Connection: close\r\n\r\n"
            ).encode("ascii") + payload
            writer.write(resp)
            await writer.drain()

        self.add_route("/api/config", _handle_config_endpoint)
        return store

    def enable_diagnostics(self, title: str = "System Health", icon: str = "cpu", start_loop: bool = True):
        """Attaches an out-of-the-box System Diagnostics tab and REST telemetry endpoints."""
        from espmpui.diagnostics import SystemDiagnostics
        diag = SystemDiagnostics(app=self, tab_title=title, tab_icon=icon)
        self.diagnostics = diag
        if start_loop:
            diag.start_telemetry_loop()
        return diag

    def enable_ota(self, partition=None, chunk_size: int = 512):
        """Attaches streaming Web OTA updater routes (/api/ota/status, /api/ota/upload)."""
        from espmpui.ota import OTAHandler, parse_multipart_boundary
        handler = OTAHandler(target_partition=partition, chunk_size=chunk_size)
        self.ota = handler

        async def _handle_ota_status(reader, writer, path, headers):
            st = handler.get_status()
            body = json.dumps(st).encode("utf-8")
            resp = (
                "HTTP/1.1 200 OK\r\n"
                "Content-Type: application/json\r\n"
                f"Content-Length: {len(body)}\r\n"
                "Connection: close\r\n\r\n"
            ).encode("ascii") + body
            writer.write(resp)
            await writer.drain()

        async def _handle_ota_upload(reader, writer, path, headers):
            method = headers.get("method", "GET").upper()
            if method != "POST":
                resp = (
                    "HTTP/1.1 405 Method Not Allowed\r\n"
                    "Content-Length: 0\r\n"
                    "Connection: close\r\n\r\n"
                ).encode("ascii")
                writer.write(resp)
                await writer.drain()
                return

            ctype = headers.get("content-type", "")
            boundary = parse_multipart_boundary(ctype)
            if not boundary:
                body = json.dumps({"status": "error", "message": "Missing multipart boundary"}).encode("utf-8")
                resp = (
                    "HTTP/1.1 400 Bad Request\r\n"
                    "Content-Type: application/json\r\n"
                    f"Content-Length: {len(body)}\r\n"
                    "Connection: close\r\n\r\n"
                ).encode("ascii") + body
                writer.write(resp)
                await writer.drain()
                return

            content_len = int(headers.get("content-length", 0))
            result = await handler.process_upload_stream(reader, boundary, content_len)
            status_code = 200 if result.get("status") == "ok" else 400
            status_text = "OK" if status_code == 200 else "Bad Request"
            body = json.dumps(result).encode("utf-8")
            resp = (
                f"HTTP/1.1 {status_code} {status_text}\r\n"
                "Content-Type: application/json\r\n"
                f"Content-Length: {len(body)}\r\n"
                "Connection: close\r\n\r\n"
            ).encode("ascii") + body
            writer.write(resp)
            await writer.drain()

        self.add_route("/api/ota/status", _handle_ota_status)
        self.add_route("/api/ota/upload", _handle_ota_upload)
        return handler

    def add_route(self, path: str, handler):
        """Registers a custom HTTP route handler."""
        self._custom_routes[path] = handler
        if self.server:
            self.server.add_route(path, handler)

    def route(self, path: str):
        """Decorator to register a custom HTTP route handler."""
        def decorator(handler):
            self.add_route(path, handler)
            return handler
        return decorator

    def tab(self, title: str, icon: str = "") -> Tab:
        """Creates and attaches a new navigation tab."""
        t = Tab(title=title, icon=icon, app=self)
        self.tabs.append(t)
        return t

    def _register_widget(self, widget: Widget):
        self.widgets_by_id[widget.id] = widget

    def get_init_schema(self) -> dict:
        """Constructs the initial full-state handshake JSON schema."""
        return {
            "op": "init",
            "title": self.title,
            "theme": self.theme,
            "tab_layout": self.tab_layout,
            "tabs": [t.to_dict() for t in self.tabs],
        }

    def _queue_diff(self, diff: dict):
        """Broadcasts a property diff to connected clients."""
        if self._on_diff:
            self._on_diff(diff)
        if self.server and getattr(self.server, "clients", None):
            msg = json.dumps(diff)
            self.server.broadcast_sync(msg)

    async def _broadcast_toast(self, message: str, level: str = "info"):
        """Broadcasts an error/info toast to connected clients."""
        payload = {"op": "toast", "msg": message, "type": level}
        if self.server and getattr(self.server, "clients", None):
            self.server.broadcast_sync(json.dumps(payload))

    def _on_ws_connect(self, client):
        """Called by server when a new WebSocket client connects: sync full state."""
        schema = self.get_init_schema()
        self.server.send_sync(client, json.dumps(schema))

    async def handle_inbound_message(self, client, text: str):
        """Parses inbound JSON event from browser and dispatches through fault barrier."""
        try:
            msg = json.loads(text)
        except Exception:
            return

        op = msg.get("op")
        if op == "evt":
            w_id = msg.get("id")
            event_name = msg.get("e")
            val = msg.get("val")

            widget = self.widgets_by_id.get(w_id)
            if widget:
                await self._safe_dispatch(widget, event_name, val)

    async def _safe_dispatch(self, widget: Widget, event_name: str, val):
        """Fault Barrier: Executes widget handler safely without crashing the server or chip."""
        try:
            await widget.handle_event(event_name, val)
        except Exception as exc:
            # Print traceback to serial console for developer debugging
            print_exception(exc)
            # Notify browser with non-intrusive error toast
            err_msg = f"{type(exc).__name__}: {str(exc)}"
            res = self._broadcast_toast(err_msg, level="error")
            if is_awaitable(res):
                await res

    def create_task(self, coro):
        """Registers a background coroutine (e.g. sensor telemetry loop)."""
        t = asyncio.create_task(coro)
        self.tasks.append(t)
        return t

    async def start(self, host: str = "0.0.0.0", port: int = 80):
        """Starts the dashboard server asynchronously."""
        self.server = AsyncServer(host=host, port=port)
        for p, h in self._custom_routes.items():
            self.server.add_route(p, h)
        if self.portal:
            self.portal.server = self.server
            self.portal.attach()
            await self.portal.start()
        self.server.on_ws_message = lambda client, text: asyncio.create_task(self.handle_inbound_message(client, text))
        self.server.on_ws_connect = self._on_ws_connect
        await self.server.start()

    def run(self, host: str = "0.0.0.0", port: int = 80):
        """Blocking convenience runner for standalone applications."""
        async def main():
            await self.start(host, port)
            while True:
                await asyncio.sleep(3600)

        try:
            asyncio.run(main())
        except KeyboardInterrupt:
            pass
