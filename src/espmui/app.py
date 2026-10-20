"""
Application controller, tab hierarchy, and reactive state coordinator for espmui.
Integrates with AsyncServer and enforces strict fault-isolation barriers.
"""

import json
import sys

try:
    import uasyncio as asyncio
except ImportError:
    import asyncio

from espmui.server import AsyncServer
from espmui.widgets import Widget, Button, Switch, Slider, Metric, Progress, is_awaitable, _generate_id

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
        from espmui.iot_widgets import Terminal
        return self.add_widget(Terminal(label, **kwargs))

    def chart(self, label: str, **kwargs):
        from espmui.iot_widgets import LineChart
        return self.add_widget(LineChart(label, **kwargs))

    def camera(self, label: str = "Camera Live View", **kwargs):
        from espmui.iot_widgets import CameraStream
        return self.add_widget(CameraStream(label, **kwargs))

    def file_manager(self, label: str = "Flash Storage", **kwargs):
        from espmui.iot_widgets import FileManager
        return self.add_widget(FileManager(label, **kwargs))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "icon": self.icon,
            "widgets": [w.to_dict() for w in self.widgets],
        }


class App:
    """The central espmui dashboard application."""

    def __init__(self, title: str = "espmui Dashboard", theme: str = "dark", tab_layout: str = "vertical", **kwargs):
        self.title = title
        self.theme = theme
        self.tab_layout = kwargs.get("tab_layout", tab_layout)
        self.tabs = []
        self.widgets_by_id = {}
        self.server = None
        self.portal = None
        self._on_diff = None  # Hook for tests or custom observers
        self.tasks = []
        self._custom_routes = {}

    def enable_captive_portal(self, ap_ssid: str = "espmui-Setup", ap_password: str = None, ap_ip: str = "192.168.4.1", dns_port: int = 53):
        """Configures and activates SoftAP captive portal and Wi-Fi provisioner."""
        from espmui.wifi import CaptivePortal, WiFiManager
        wifi_mgr = WiFiManager()
        wifi_mgr.start_ap(ssid=ap_ssid, password=ap_password, ip=ap_ip)
        self.portal = CaptivePortal(self.server, wifi_manager=wifi_mgr, ap_ip=ap_ip, dns_port=dns_port)
        if self.server:
            self.portal.attach()
        return self.portal

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
