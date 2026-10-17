"""
Declarative UI Widget components for espmui.
Designed for zero-memory bloat, automatic reactive diff propagation, and ISR safety.
"""

import sys

try:
    import uasyncio as asyncio
except ImportError:
    import asyncio

_WIDGET_COUNTER = 0

def is_awaitable(obj):
    """Checks if an object can be awaited in MicroPython or standard Python."""
    return hasattr(obj, "__await__") or type(obj).__name__ in ("generator", "coroutine")

def _generate_id(prefix="w"):
    global _WIDGET_COUNTER
    _WIDGET_COUNTER += 1
    return f"{prefix}_{_WIDGET_COUNTER}"


class Widget:
    """Base class for all espmui UI widgets."""

    def __init__(self, label: str, val=None, id: str = None, app=None):
        self.id = id or _generate_id()
        self.label = label
        self._val = val
        self.app = app
        self.type = "generic"
        self.debounce_ms = 0
        self.drop_if_busy = False
        self._is_busy = False

    @property
    def value(self):
        return self._val

    @value.setter
    def value(self, new_val):
        self.set_value(new_val)

    def set_value(self, new_val, **kwargs):
        """Updates the widget value and broadcasts a diff to all clients."""
        self._val = new_val
        if self.app:
            diff = {"op": "set", "id": self.id, "val": new_val}
            diff.update(kwargs)
            self.app._queue_diff(diff)

    def schedule_value(self, new_val):
        """
        Safely update value from a hardware Interrupt Service Routine (ISR).
        Bridges hard ISR context into MicroPython main loop using micropython.schedule.
        """
        try:
            import micropython
            micropython.schedule(lambda _: setattr(self, "value", new_val), 0)
        except (ImportError, AttributeError):
            self.value = new_val

    def to_dict(self) -> dict:
        """Serializes widget to a JSON-compatible dictionary."""
        return {
            "id": self.id,
            "type": self.type,
            "label": self.label,
            "val": self._val,
        }

    async def handle_event(self, event_name: str, value=None):
        """Handles an event dispatched from the client browser."""
        pass


class Button(Widget):
    """Interactive push button."""

    def __init__(self, label: str, text: str = "Press", on_click=None, accent: str = "", **kwargs):
        super().__init__(label, **kwargs)
        self.type = "button"
        self.text = text
        self.accent = accent
        self.on_click = on_click

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({
            "text": self.text,
            "accent": self.accent,
        })
        return d

    async def handle_event(self, event_name: str, value=None):
        if event_name == "click" and self.on_click:
            res = self.on_click(self)
            if is_awaitable(res):
                await res


class Switch(Widget):
    """Toggle switch with immediate two-way state synchronization."""

    def __init__(self, label: str, value: bool = False, on_change=None, **kwargs):
        super().__init__(label, val=bool(value), **kwargs)
        self.type = "switch"
        self.on_change = on_change

    async def handle_event(self, event_name: str, value=None):
        if event_name == "change":
            self._val = bool(value)
            if self.on_change:
                res = self.on_change(self, self._val)
                if is_awaitable(res):
                    await res


class Slider(Widget):
    """Continuous range slider with min/max and step."""

    def __init__(self, label: str, min: float = 0, max: float = 100, step: float = 1, value: float = 0, on_change=None, **kwargs):
        super().__init__(label, val=value, **kwargs)
        self.type = "slider"
        self.min = min
        self.max = max
        self.step = step
        self.on_change = on_change

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({
            "min": self.min,
            "max": self.max,
            "step": self.step,
        })
        return d

    async def handle_event(self, event_name: str, value=None):
        if event_name == "change":
            self._val = value
            if self.on_change:
                res = self.on_change(self, self._val)
                if is_awaitable(res):
                    await res


class Metric(Widget):
    """Telemetry display card for sensors (temperature, voltage, RSSI)."""

    def __init__(self, label: str, value="--", unit: str = "", badge: str = "", **kwargs):
        super().__init__(label, val=value, **kwargs)
        self.type = "metric"
        self.unit = unit
        self.badge = badge

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({
            "unit": self.unit,
            "badge": self.badge,
        })
        return d


class Progress(Widget):
    """Progress bar for memory, disk, or percentage indicators."""

    def __init__(self, label: str, max: float = 100, unit: str = "", value: float = 0, **kwargs):
        super().__init__(label, val=value, **kwargs)
        self.type = "progress"
        self.max = max
        self.unit = unit

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({
            "max": self.max,
            "unit": self.unit,
        })
        return d
