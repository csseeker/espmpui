import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from espmpui.diagnostics import SystemDiagnostics, format_uptime
from espmpui.app import App


class TestSystemMetricsCollector(unittest.TestCase):
    def setUp(self):
        self.diag = SystemDiagnostics()

    def test_format_uptime(self):
        """Verify seconds formatting into readable human intervals."""
        self.assertEqual(format_uptime(45), "45s")
        self.assertEqual(format_uptime(125), "2m 5s")
        self.assertEqual(format_uptime(3665), "1h 1m 5s")
        self.assertEqual(format_uptime(90061), "1d 1h 1m 1s")

    def test_collect_heap_metrics(self):
        """Verify heap allocation and free memory metric collection."""
        metrics = self.diag.get_metrics()
        heap = metrics["heap"]
        self.assertIn("free", heap)
        self.assertIn("alloc", heap)
        self.assertIn("total", heap)
        self.assertIn("pct_free", heap)
        self.assertGreater(heap["total"], 0)
        self.assertGreaterEqual(heap["pct_free"], 0)
        self.assertLessEqual(heap["pct_free"], 100)

    def test_collect_flash_metrics(self):
        """Verify filesystem flash metrics reporting total and free bytes."""
        metrics = self.diag.get_metrics()
        flash = metrics["flash"]
        self.assertIn("total", flash)
        self.assertIn("free", flash)
        self.assertIn("used", flash)
        self.assertIn("pct_used", flash)
        self.assertGreater(flash["total"], 0)

    def test_collect_system_info(self):
        """Verify CPU frequency and platform telemetry."""
        metrics = self.diag.get_metrics()
        self.assertIn("uptime_sec", metrics)
        self.assertIn("uptime_str", metrics)
        self.assertIn("platform", metrics)
        self.assertIn("cpu_freq_mhz", metrics)

    def test_gc_collect_reports_freed_memory(self):
        """Verify manual GC triggers collection and reports freed memory."""
        res = self.diag.collect_garbage()
        self.assertIn("freed_bytes", res)
        self.assertIn("heap", res)
        self.assertIsInstance(res["freed_bytes"], int)


class TestDiagnosticsAppIntegration(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = App(title="Diagnostics Node")
        self.diag = self.app.enable_diagnostics(title="System Health", icon="cpu")
        await self.app.start(host="127.0.0.1", port=0)
        self.port = self.app.server.port

    async def asyncTearDown(self):
        if hasattr(self.diag, "stop"):
            await self.diag.stop()
        await self.app.server.stop()

    def test_diagnostics_tab_and_widgets_created(self):
        """Verify System Health tab with metric and progress widgets is initialized."""
        schema = self.app.get_init_schema()
        tabs = schema["tabs"]
        self.assertEqual(len(tabs), 1)
        diag_tab = tabs[0]
        self.assertEqual(diag_tab["title"], "System Health")
        self.assertEqual(diag_tab["icon"], "cpu")

        # Verify essential widgets exist: RAM progress, Flash progress, Uptime, GC button, Reboot button
        widget_labels = [w.get("label", "") for w in diag_tab["widgets"]]
        self.assertTrue(any("Heap" in label or "RAM" in label for label in widget_labels))
        self.assertTrue(any("Flash" in label or "Storage" in label for label in widget_labels))
        self.assertTrue(any("Uptime" in label for label in widget_labels))

    async def test_get_api_system_metrics(self):
        """Verify GET /api/system/metrics returns live JSON telemetry."""
        reader, writer = await asyncio.open_connection("127.0.0.1", self.port)
        writer.write(b"GET /api/system/metrics HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n")
        await writer.drain()

        resp = await reader.read(4096)
        writer.close()
        await writer.wait_closed()

        self.assertIn(b"HTTP/1.1 200 OK", resp)
        self.assertIn(b'"heap"', resp)
        self.assertIn(b'"flash"', resp)
        self.assertIn(b'"uptime_str"', resp)

    async def test_post_api_system_gc(self):
        """Verify POST /api/system/gc triggers garbage collection and returns result."""
        reader, writer = await asyncio.open_connection("127.0.0.1", self.port)
        writer.write(b"POST /api/system/gc HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Length: 0\r\n\r\n")
        await writer.drain()

        resp = await reader.read(4096)
        writer.close()
        await writer.wait_closed()

        self.assertIn(b"HTTP/1.1 200 OK", resp)
        self.assertIn(b'"freed_bytes"', resp)

    async def test_post_api_system_reboot_endpoint(self):
        """Verify POST /api/system/reboot acknowledges restart request safely."""
        # Ensure test does not reset Python process
        self.diag._reboot_fn = lambda: None

        reader, writer = await asyncio.open_connection("127.0.0.1", self.port)
        writer.write(b"POST /api/system/reboot HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Length: 0\r\n\r\n")
        await writer.drain()

        resp = await reader.read(4096)
        writer.close()
        await writer.wait_closed()

        self.assertIn(b"HTTP/1.1 200 OK", resp)
        self.assertIn(b'"rebooting"', resp)


if __name__ == "__main__":
    unittest.main()
