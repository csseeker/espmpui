"""
espmui: Modern Reactive Web Dashboard for MicroPython
"""

from espmui.app import App, Tab
from espmui.widgets import Widget, Button, Switch, Slider, Metric, Progress
from espmui.iot_widgets import Terminal, LineChart, CameraStream, FileManager
from espmui.wifi import WiFiManager, DNSServer, CaptivePortal
from espmui.config import ConfigStore, ConfigForm, ConfigValidationError
from espmui.diagnostics import SystemDiagnostics, format_uptime

__version__ = "0.1.0"
__all__ = [
    "App",
    "Tab",
    "Widget",
    "Button",
    "Switch",
    "Slider",
    "Metric",
    "Progress",
    "Terminal",
    "LineChart",
    "CameraStream",
    "FileManager",
    "WiFiManager",
    "DNSServer",
    "CaptivePortal",
    "ConfigStore",
    "ConfigForm",
    "ConfigValidationError",
    "SystemDiagnostics",
    "format_uptime",
]
