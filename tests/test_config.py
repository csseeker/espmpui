import asyncio
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from espmpui.config import ConfigStore, ConfigValidationError
from espmpui.app import App


class TestConfigStorePersistence(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.test_dir, "config.json")
        self.schema = {
            "node_name": {
                "type": "text",
                "default": "DefaultNode",
                "label": "Node Name",
            },
            "interval": {
                "type": "number",
                "default": 10,
                "min": 1,
                "max": 300,
                "label": "Interval",
            },
            "enabled": {
                "type": "bool",
                "default": True,
                "label": "Enabled",
            },
            "mode": {
                "type": "select",
                "options": ["AUTO", "MANUAL", "OFF"],
                "default": "AUTO",
                "label": "Mode",
            },
            "brightness": {
                "type": "slider",
                "default": 50,
                "min": 0,
                "max": 100,
                "label": "Brightness",
            },
        }

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_default_values_when_no_file_exists(self):
        """Verify ConfigStore initializes with schema defaults when file does not exist."""
        store = ConfigStore(self.schema, filepath=self.config_path)
        self.assertEqual(store.node_name, "DefaultNode")
        self.assertEqual(store["interval"], 10)
        self.assertEqual(store.enabled, True)
        self.assertEqual(store.mode, "AUTO")
        self.assertEqual(store.brightness, 50)

    def test_atomic_save_and_reload(self):
        """Verify changes are atomically saved to flash and reloaded across instances."""
        store1 = ConfigStore(self.schema, filepath=self.config_path)
        store1.node_name = "GardenNode"
        store1.interval = 30
        store1.enabled = False
        store1.save()

        # Verify physical file exists and temp file was cleaned up
        self.assertTrue(os.path.exists(self.config_path))
        self.assertFalse(os.path.exists(self.config_path + ".tmp"))

        # Verify file content is valid JSON
        with open(self.config_path, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["node_name"], "GardenNode")
        self.assertEqual(data["interval"], 30)
        self.assertEqual(data["enabled"], False)

        # Reload with a fresh instance
        store2 = ConfigStore(self.schema, filepath=self.config_path)
        self.assertEqual(store2.node_name, "GardenNode")
        self.assertEqual(store2.interval, 30)
        self.assertEqual(store2.enabled, False)
        # Unmodified keys retain defaults
        self.assertEqual(store2.mode, "AUTO")

    def test_corrupted_file_recovery(self):
        """Verify that 0-byte or corrupt config files gracefully fallback to defaults or temp file."""
        # 1. Simulate 0-byte power-cut truncation
        with open(self.config_path, "w", encoding="utf-8") as f:
            f.write("")  # 0 bytes

        store = ConfigStore(self.schema, filepath=self.config_path)
        # Should not crash and should load schema defaults
        self.assertEqual(store.node_name, "DefaultNode")
        self.assertEqual(store.interval, 10)

        # 2. Simulate valid .tmp file from interrupted rename
        valid_tmp = {"node_name": "RecoveredNode", "interval": 45}
        with open(self.config_path + ".tmp", "w", encoding="utf-8") as f:
            json.dump(valid_tmp, f)

        store_tmp = ConfigStore(self.schema, filepath=self.config_path)
        self.assertEqual(store_tmp.node_name, "RecoveredNode")
        self.assertEqual(store_tmp.interval, 45)

    def test_validation_bounds(self):
        """Verify input validation enforces min, max, type, and select options."""
        store = ConfigStore(self.schema, filepath=self.config_path)

        # Numeric bounds
        with self.assertRaises(ConfigValidationError):
            store.interval = 0  # Below min 1
        with self.assertRaises(ConfigValidationError):
            store.interval = 500  # Above max 300

        # Select options
        with self.assertRaises(ConfigValidationError):
            store.mode = "INVALID_MODE"

        # Type checking
        with self.assertRaises(ConfigValidationError):
            store.enabled = "not a bool"

        # Valid assignments should succeed
        store.interval = 60
        store.mode = "MANUAL"
        store.enabled = False
        self.assertEqual(store.interval, 60)
        self.assertEqual(store.mode, "MANUAL")


class TestConfigHooksAndBinding(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.test_dir, "config.json")
        self.schema = {
            "baudrate": {"type": "number", "default": 115200},
            "tag": {"type": "text", "default": "alpha"},
        }
        self.store = ConfigStore(self.schema, filepath=self.config_path)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_sync_change_hook(self):
        """Verify synchronous change hooks trigger on value modification."""
        hook_events = []

        def on_baud_change(new_val, old_val):
            hook_events.append((new_val, old_val))

        self.store.on_change("baudrate", on_baud_change)
        self.store.baudrate = 9600

        self.assertEqual(len(hook_events), 1)
        self.assertEqual(hook_events[0], (9600, 115200))

    async def test_async_change_hook(self):
        """Verify asynchronous change hooks execute cooperatively."""
        async_events = []

        async def async_tag_change(new_val, old_val):
            await asyncio.sleep(0.01)
            async_events.append((new_val, old_val))

        self.store.on_change("tag", async_tag_change)
        await self.store.set_async("tag", "beta")

        self.assertEqual(len(async_events), 1)
        self.assertEqual(async_events[0], ("beta", "alpha"))

    def test_global_change_hook(self):
        """Verify global change hook receives all field modifications."""
        changes = []

        def on_any(key, new_val, old_val):
            changes.append((key, new_val, old_val))

        self.store.on_change(None, on_any)
        self.store.tag = "omega"
        self.store.baudrate = 57600

        self.assertEqual(len(changes), 2)
        self.assertEqual(changes[0], ("tag", "omega", "alpha"))
        self.assertEqual(changes[1], ("baudrate", 57600, 115200))


class TestConfigRESTAndAppIntegration(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.test_dir, "config.json")
        self.schema = {
            "ssid": {"type": "text", "default": "MyRouter", "label": "SSID"},
            "power": {"type": "slider", "default": 80, "min": 0, "max": 100, "label": "TX Power"},
        }
        self.app = App(title="Config App")
        self.config = self.app.attach_config(self.schema, filepath=self.config_path)
        self.tab = self.app.tab("Settings", icon="sliders")
        self.form = self.tab.config_form(self.config, label="System Parameters")
        await self.app.start(host="127.0.0.1", port=0)
        self.port = self.app.server.port

    async def asyncTearDown(self):
        await self.app.server.stop()
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_config_form_widget_schema(self):
        """Verify ConfigForm widget outputs declarative schema with initial values."""
        form_dict = self.form.to_dict()
        self.assertEqual(form_dict["type"], "config_form")
        self.assertEqual(form_dict["label"], "System Parameters")
        self.assertIn("schema", form_dict)
        self.assertEqual(form_dict["values"]["ssid"], "MyRouter")
        self.assertEqual(form_dict["values"]["power"], 80)

    async def test_get_api_config(self):
        """Verify GET /api/config returns values and schema."""
        reader, writer = await asyncio.open_connection("127.0.0.1", self.port)
        writer.write(b"GET /api/config HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n")
        await writer.drain()

        resp = await reader.read(4096)
        writer.close()
        await writer.wait_closed()

        self.assertIn(b"HTTP/1.1 200 OK", resp)
        self.assertIn(b'"ssid": "MyRouter"', resp)
        self.assertIn(b'"power": 80', resp)

    async def test_post_api_config_success(self):
        """Verify POST /api/config updates values and saves atomically."""
        reader, writer = await asyncio.open_connection("127.0.0.1", self.port)
        body = json.dumps({"values": {"ssid": "NewOfficeNet", "power": 50}}).encode("utf-8")
        req = (
            b"POST /api/config HTTP/1.1\r\n"
            b"Host: 127.0.0.1\r\n"
            b"Content-Type: application/json\r\n"
            b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body
        )
        writer.write(req)
        await writer.drain()

        resp = await reader.read(4096)
        writer.close()
        await writer.wait_closed()

        self.assertIn(b"HTTP/1.1 200 OK", resp)
        self.assertIn(b'"status": "ok"', resp)

        # Verify in memory
        self.assertEqual(self.config.ssid, "NewOfficeNet")
        self.assertEqual(self.config.power, 50)

        # Verify on disk
        with open(self.config_path, encoding="utf-8") as f:
            disk_data = json.load(f)
        self.assertEqual(disk_data["ssid"], "NewOfficeNet")
        self.assertEqual(disk_data["power"], 50)

    async def test_post_api_config_validation_error(self):
        """Verify POST /api/config with out-of-bound values returns 400 Bad Request."""
        reader, writer = await asyncio.open_connection("127.0.0.1", self.port)
        body = json.dumps({"values": {"power": 250}}).encode("utf-8")  # Max is 100
        req = (
            b"POST /api/config HTTP/1.1\r\n"
            b"Host: 127.0.0.1\r\n"
            b"Content-Type: application/json\r\n"
            b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body
        )
        writer.write(req)
        await writer.drain()

        resp = await reader.read(4096)
        writer.close()
        await writer.wait_closed()

        self.assertIn(b"HTTP/1.1 400", resp)
        self.assertIn(b'"status": "error"', resp)
        self.assertEqual(self.config.power, 80)  # Remains unchanged


if __name__ == "__main__":
    unittest.main()
