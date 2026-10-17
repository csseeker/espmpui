import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from espmui.app import App
from espmui.iot_widgets import Terminal, LineChart, CameraStream, FileManager


class TestIoTWidgets(unittest.TestCase):
    def setUp(self):
        self.app = App(title="IoT Test Node")
        self.tab = self.app.tab("IoT Lab")

    def test_terminal_widget(self):
        diffs = []
        self.app._on_diff = lambda d: diffs.append(d)

        term = self.tab.add_widget(Terminal("System Console", max_lines=100))
        schema = term.to_dict()
        self.assertEqual(schema["type"], "terminal")
        self.assertEqual(schema["max_lines"], 100)

        # Append log message
        term.log("Booting system...")
        self.assertEqual(len(diffs), 1)
        self.assertEqual(diffs[0]["op"], "stream")
        self.assertEqual(diffs[0]["id"], term.id)
        self.assertIn("Booting system...", diffs[0]["text"])

    def test_line_chart_widget(self):
        diffs = []
        self.app._on_diff = lambda d: diffs.append(d)

        chart = self.tab.add_widget(LineChart("Temperature History", max_points=20, unit="°C", color="#38bdf8"))
        schema = chart.to_dict()
        self.assertEqual(schema["type"], "chart")
        self.assertEqual(schema["max_points"], 20)
        self.assertEqual(schema["color"], "#38bdf8")

        # Push data point
        chart.add_point(42.5)
        self.assertEqual(len(diffs), 1)
        self.assertEqual(diffs[0]["op"], "chart_point")
        self.assertEqual(diffs[0]["val"], 42.5)

    def test_camera_stream_widget(self):
        cam = self.tab.add_widget(CameraStream("Live Viewfinder", stream_url="/stream", snapshot_url="/snapshot"))
        schema = cam.to_dict()
        self.assertEqual(schema["type"], "camera")
        self.assertEqual(schema["stream_url"], "/stream")
        self.assertEqual(schema["snapshot_url"], "/snapshot")

    def test_file_manager_widget(self):
        fm = self.tab.add_widget(FileManager("Flash Storage", root_path="."))
        schema = fm.to_dict()
        self.assertEqual(schema["type"], "file_manager")


if __name__ == "__main__":
    unittest.main()
