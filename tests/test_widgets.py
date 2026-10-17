import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from espmui.widgets import Widget, Button, Switch, Slider, Metric, Progress
from espmui.app import App


class TestWidgetHierarchy(unittest.TestCase):
    def setUp(self):
        self.app = App(title="Test Node")
        self.tab = self.app.tab("Main", icon="home")

    def test_button_creation_and_schema(self):
        btn = self.tab.button("Relay", text="Trigger", accent="danger")
        schema = btn.to_dict()
        self.assertEqual(schema["type"], "button")
        self.assertEqual(schema["label"], "Relay")
        self.assertEqual(schema["text"], "Trigger")
        self.assertEqual(schema["accent"], "danger")
        self.assertTrue(schema["id"].startswith("w_"))

    def test_switch_reactive_value_change(self):
        sw = self.tab.switch("Power", value=False)
        diffs = []
        self.app._on_diff = lambda diff: diffs.append(diff)

        # Updating property directly in Python
        sw.value = True
        self.assertEqual(sw.value, True)
        self.assertEqual(len(diffs), 1)
        self.assertEqual(diffs[0], {"op": "set", "id": sw.id, "val": True})

    def test_slider_bounds_and_change(self):
        slider = self.tab.slider("Speed", min=10, max=200, step=5, value=50)
        schema = slider.to_dict()
        self.assertEqual(schema["min"], 10)
        self.assertEqual(schema["max"], 200)
        self.assertEqual(schema["step"], 5)
        self.assertEqual(schema["val"], 50)

    def test_metric_and_progress_schema(self):
        m = self.tab.metric("Temp", value=25.4, unit="°C")
        p = self.tab.progress("RAM", max=8192, unit="KB", value=4096)

        m_dict = m.to_dict()
        p_dict = p.to_dict()
        self.assertEqual(m_dict["val"], 25.4)
        self.assertEqual(m_dict["unit"], "°C")
        self.assertEqual(p_dict["max"], 8192)
        self.assertEqual(p_dict["val"], 4096)

    def test_full_app_init_schema(self):
        self.tab.button("B1")
        tab2 = self.app.tab("Sensors")
        tab2.metric("Volt", value=3.3)

        init_payload = self.app.get_init_schema()
        self.assertEqual(init_payload["op"], "init")
        self.assertEqual(init_payload["title"], "Test Node")
        self.assertEqual(len(init_payload["tabs"]), 2)
        self.assertEqual(len(init_payload["tabs"][0]["widgets"]), 1)
        self.assertEqual(len(init_payload["tabs"][1]["widgets"]), 1)


class TestEventDispatchAndFaultIsolation(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = App(title="Test App")
        self.tab = self.app.tab("Tab 1")

    async def test_button_click_event_dispatch(self):
        clicked = []
        btn = self.tab.button("Click Me", on_click=lambda w: clicked.append(True))

        # Simulate inbound WebSocket event
        event_msg = f'{{"op":"evt","id":"{btn.id}","e":"click"}}'
        await self.app.handle_inbound_message(None, event_msg)

        self.assertEqual(len(clicked), 1)

    async def test_switch_change_event_dispatch(self):
        received_vals = []
        sw = self.tab.switch("Toggle", on_change=lambda w, val: received_vals.append(val))

        event_msg = f'{{"op":"evt","id":"{sw.id}","e":"change","val":true}}'
        await self.app.handle_inbound_message(None, event_msg)

        self.assertEqual(sw.value, True)
        self.assertEqual(received_vals, [True])

    async def test_async_callback_support(self):
        async_events = []
        async def on_slide(w, val):
            await asyncio.sleep(0.01)
            async_events.append(val)

        slider = self.tab.slider("Vol", on_change=on_slide)
        event_msg = f'{{"op":"evt","id":"{slider.id}","e":"change","val":75}}'
        await self.app.handle_inbound_message(None, event_msg)

        self.assertEqual(async_events, [75])

    async def test_fault_shield_catches_callback_exceptions(self):
        """Verify that an exception in a user callback does not raise or crash the app."""
        def bad_callback(w):
            return 1 / 0  # ZeroDivisionError!

        toasts = []
        self.app._broadcast_toast = lambda msg, level="error": toasts.append((msg, level))

        btn = self.tab.button("Boom", on_click=bad_callback)
        event_msg = f'{{"op":"evt","id":"{btn.id}","e":"click"}}'

        # This should execute safely without throwing ZeroDivisionError
        await self.app.handle_inbound_message(None, event_msg)

        # An error toast should have been emitted
        self.assertEqual(len(toasts), 1)
        self.assertIn("ZeroDivisionError", toasts[0][0])
        self.assertEqual(toasts[0][1], "error")


if __name__ == "__main__":
    unittest.main()
