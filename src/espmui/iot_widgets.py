"""
Specialized IoT Widgets for espmui:
- Live Web Terminal (Log streaming / REPL)
- Real-time Canvas Sparkline / Line Chart
- Live Camera Viewfinder (MJPEG & Snapshot)
- Flash File Manager
"""

import os

from espmui.widgets import Widget


class Terminal(Widget):
    """Browser-based live log terminal & stdout monitor."""

    def __init__(self, label: str = "System Log", max_lines: int = 100, **kwargs):
        super().__init__(label, **kwargs)
        self.type = "terminal"
        self.max_lines = max_lines
        self.lines = []

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({
            "max_lines": self.max_lines,
        })
        return d

    def log(self, text: str):
        """Appends text or log line and broadcasts to all clients."""
        if not text.endswith("\n"):
            text += "\n"
        self.lines.append(text)
        if len(self.lines) > self.max_lines:
            self.lines.pop(0)

        if self.app:
            self.app._queue_diff({
                "op": "stream",
                "id": self.id,
                "text": text
            })

    async def handle_event(self, event_name: str, value=None):
        if event_name == "clear":
            self.lines.clear()


class LineChart(Widget):
    """Real-time scrolling HTML5 canvas line chart."""

    def __init__(self, label: str, max_points: int = 30, unit: str = "", color: str = "#38bdf8", **kwargs):
        super().__init__(label, **kwargs)
        self.type = "chart"
        self.max_points = max_points
        self.unit = unit
        self.color = color
        self.points = []

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({
            "max_points": self.max_points,
            "unit": self.unit,
            "color": self.color,
        })
        return d

    def add_point(self, val: float):
        """Appends a data point and broadcasts to canvas chart."""
        self.points.append(val)
        if len(self.points) > self.max_points:
            self.points.pop(0)

        if self.app:
            self.app._queue_diff({
                "op": "chart_point",
                "id": self.id,
                "val": val
            })


class CameraStream(Widget):
    """Responsive camera viewfinder supporting MJPEG live streaming and snapshot capture."""

    def __init__(self, label: str = "Camera Live View", stream_url: str = "/stream", snapshot_url: str = "/snapshot", **kwargs):
        super().__init__(label, **kwargs)
        self.type = "camera"
        self.stream_url = stream_url
        self.snapshot_url = snapshot_url

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({
            "stream_url": self.stream_url,
            "snapshot_url": self.snapshot_url,
        })
        return d


class FileManager(Widget):
    """Flash storage file explorer: browse, view, and manage files on LittleFS/FAT."""

    def __init__(self, label: str = "Flash Storage", root_path: str = ".", **kwargs):
        super().__init__(label, **kwargs)
        self.type = "file_manager"
        self.root_path = root_path

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({
            "root_path": self.root_path,
        })
        return d

    def list_files(self) -> list:
        """Returns list of files and sizes."""
        files = []
        try:
            for entry in os.listdir(self.root_path):
                stat = os.stat(f"{self.root_path}/{entry}")
                files.append({
                    "name": entry,
                    "size": stat[6],  # Size in bytes
                })
        except Exception:
            pass
        return files
