"""
espmpui: Modern Reactive Web Dashboard for MicroPython
"""

from espmpui.app import App, Tab
from espmpui.widgets import Widget, Button, Switch, Slider, Metric, Progress
from espmpui.iot_widgets import Terminal, LineChart, CameraStream, FileManager
from espmpui.wifi import WiFiManager, DNSServer, CaptivePortal
from espmpui.config import ConfigStore, ConfigForm, ConfigValidationError
from espmpui.diagnostics import SystemDiagnostics, format_uptime
from espmpui.ota import OTAHandler, MockOTAPartition, parse_multipart_boundary

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
    "OTAHandler",
    "MockOTAPartition",
    "parse_multipart_boundary",
]
