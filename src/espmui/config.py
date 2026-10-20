"""
Persistent Parameter & Schema-Driven Config Store for espmui.
Features atomic flash writes (temp file + rename pattern), corruption recovery,
schema validation, Python variable binding, and change hooks.
"""

import json
import os
import sys

try:
    import uasyncio as asyncio
except ImportError:
    import asyncio

from espmui.widgets import Widget, _generate_id, is_awaitable

def print_exception(exc):
    """Prints exception traceback on both MicroPython and standard Python."""
    if hasattr(sys, "print_exception"):
        sys.print_exception(exc)
    else:
        import traceback
        traceback.print_exception(exc)


def _file_exists(filepath: str) -> bool:
    """Checks file existence compatible with both MicroPython (os.stat) and standard Python."""
    try:
        os.stat(filepath)
        return True
    except OSError:
        return False


class ConfigValidationError(ValueError):
    """Raised when configuration parameter fails schema validation."""
    pass


class ConfigStore:
    """
    Persistent configuration store with atomic flash writes, corruption recovery,
    schema-driven validation, and reactive change hooks.
    """

    def __init__(self, schema: dict, filepath: str = "config.json", app=None, autosave: bool = True):
        self._schema = schema
        self._filepath = filepath
        self._app = app
        self._autosave = autosave
        self._values = {}
        self._hooks = {}          # key -> list of callbacks
        self._global_hooks = []   # list of callbacks receiving (key, new, old)

        # Initialize defaults from schema
        for key, spec in self._schema.items():
            self._values[key] = spec.get("default", None)

        # Load persisted values
        self.load()

    @property
    def schema(self) -> dict:
        return self._schema

    @property
    def filepath(self) -> str:
        return self._filepath

    def validate_field(self, key: str, val):
        """Validates a value against the schema specification for key."""
        if key not in self._schema:
            return val

        spec = self._schema[key]
        field_type = spec.get("type", "text")

        if field_type == "bool":
            if not isinstance(val, bool):
                raise ConfigValidationError(f"Field '{key}' must be a boolean, got {type(val).__name__}")
            return val

        elif field_type in ("number", "slider"):
            if not isinstance(val, (int, float)) or isinstance(val, bool):
                try:
                    val = float(val) if "." in str(val) else int(val)
                except (ValueError, TypeError):
                    raise ConfigValidationError(f"Field '{key}' must be a number, got {val}")

            min_val = spec.get("min")
            max_val = spec.get("max")
            if min_val is not None and val < min_val:
                raise ConfigValidationError(f"Field '{key}' value {val} is below minimum {min_val}")
            if max_val is not None and val > max_val:
                raise ConfigValidationError(f"Field '{key}' value {val} is above maximum {max_val}")
            return val

        elif field_type == "select":
            options = spec.get("options", [])
            if val not in options:
                raise ConfigValidationError(f"Field '{key}' value '{val}' not in allowed options: {options}")
            return val

        elif field_type in ("text", "password"):
            if not isinstance(val, str):
                val = str(val)
            return val

        return val

    def load(self):
        """
        Loads configuration from flash with atomic corruption recovery.
        Recovers from .tmp if the main file is truncated (0 bytes or malformed).
        """
        data = None

        # 1. Try reading primary config file
        if _file_exists(self._filepath):
            try:
                with open(self._filepath, encoding="utf-8") as f:
                    content = f.read().strip()
                if content:
                    data = json.loads(content)
            except Exception:
                data = None

        # 2. Recovery: Check if .tmp exists if main file is missing or corrupted
        tmp_path = self._filepath + ".tmp"
        if data is None and _file_exists(tmp_path):
            try:
                with open(tmp_path, encoding="utf-8") as f:
                    content = f.read().strip()
                if content:
                    data = json.loads(content)
                    # Restore .tmp to primary
                    try:
                        os.rename(tmp_path, self._filepath)
                    except Exception:
                        pass
            except Exception:
                data = None

        # 3. Apply loaded values matching schema
        if isinstance(data, dict):
            for k, v in data.items():
                if k in self._schema:
                    try:
                        validated_val = self.validate_field(k, v)
                        self._values[k] = validated_val
                    except Exception:
                        pass

    def save(self):
        """
        Atomically saves configuration to flash.
        Writes to .tmp first, flushes, then executes atomic rename to prevent corruption.
        """
        tmp_path = self._filepath + ".tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self._values, f)
                f.flush()
                # If sync is available (MicroPython LittleFS / os.sync)
                if hasattr(os, "sync"):
                    try:
                        os.sync()
                    except Exception:
                        pass

            # Atomic rename (POSIX & LittleFS atomic inode switch)
            if sys.platform == "win32" and _file_exists(self._filepath):
                os.remove(self._filepath)
            os.rename(tmp_path, self._filepath)
        except Exception as exc:
            print_exception(exc)
            if _file_exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

    def set(self, key: str, val, save: bool = None):
        """Sets a configuration value synchronously and invokes registered hooks."""
        validated = self.validate_field(key, val)
        old_val = self._values.get(key)
        if old_val == validated:
            return

        self._values[key] = validated

        # Run registered change hooks
        self._dispatch_hooks(key, validated, old_val)

        do_save = self._autosave if save is None else save
        if do_save:
            self.save()

    async def set_async(self, key: str, val, save: bool = None):
        """Sets a configuration value and awaits any async hooks cooperatively."""
        validated = self.validate_field(key, val)
        old_val = self._values.get(key)
        if old_val == validated:
            return

        self._values[key] = validated

        # Run hooks (cooperatively awaiting awaitable callbacks)
        await self._dispatch_hooks_async(key, validated, old_val)

        do_save = self._autosave if save is None else save
        if do_save:
            self.save()

    def update(self, new_values: dict, save: bool = None):
        """Batch updates multiple configuration fields with transactional validation."""
        validated_batch = {}
        for k, v in new_values.items():
            if k in self._schema:
                validated_batch[k] = self.validate_field(k, v)

        changed = []
        for k, validated in validated_batch.items():
            old = self._values.get(k)
            if old != validated:
                self._values[k] = validated
                changed.append((k, validated, old))

        for k, v, old in changed:
            self._dispatch_hooks(k, v, old)

        do_save = self._autosave if save is None else save
        if do_save and changed:
            self.save()

    def reset_defaults(self, save: bool = True):
        """Resets all configuration values to schema defaults."""
        defaults = {k: spec.get("default") for k, spec in self._schema.items()}
        self.update(defaults, save=save)

    def on_change(self, key_or_func=None, func=None):
        """
        Registers a change hook callback.
        Usage:
          @config.on_change("interval")
          def handler(new_val, old_val): ...

          @config.on_change
          def global_handler(key, new_val, old_val): ...

          config.on_change("interval", handler)
        """
        if callable(key_or_func) and func is None:
            # Decorator without argument -> global hook
            self._global_hooks.append(key_or_func)
            return key_or_func

        if isinstance(key_or_func, str):
            if func is not None:
                self._hooks.setdefault(key_or_func, []).append(func)
                return func
            else:
                def decorator(cb):
                    self._hooks.setdefault(key_or_func, []).append(cb)
                    return cb
                return decorator

        if key_or_func is None and func is not None:
            self._global_hooks.append(func)
            return func

        return None

    def _dispatch_hooks(self, key: str, new_val, old_val):
        """Fault barrier for synchronous change hook execution."""
        for cb in self._hooks.get(key, []):
            try:
                res = cb(new_val, old_val)
                if is_awaitable(res):
                    asyncio.create_task(res)
            except Exception as ex:
                print_exception(ex)

        for cb in self._global_hooks:
            try:
                res = cb(key, new_val, old_val)
                if is_awaitable(res):
                    asyncio.create_task(res)
            except Exception as ex:
                print_exception(ex)

    async def _dispatch_hooks_async(self, key: str, new_val, old_val):
        """Awaits coroutine change hooks cooperatively."""
        for cb in self._hooks.get(key, []):
            try:
                res = cb(new_val, old_val)
                if is_awaitable(res):
                    await res
            except Exception as ex:
                print_exception(ex)

        for cb in self._global_hooks:
            try:
                res = cb(key, new_val, old_val)
                if is_awaitable(res):
                    await res
            except Exception as ex:
                print_exception(ex)

    def to_dict(self) -> dict:
        """Returns shallow copy of current configuration dictionary."""
        return dict(self._values)

    def __getattr__(self, name: str):
        if name.startswith("_"):
            return super().__getattribute__(name)
        if name in self._values:
            return self._values[name]
        raise AttributeError(f"'ConfigStore' has no setting '{name}'")

    def __setattr__(self, name: str, value):
        if name.startswith("_") or name in ("schema", "filepath"):
            super().__setattr__(name, value)
        elif hasattr(self, "_schema") and name in self._schema:
            self.set(name, value)
        else:
            super().__setattr__(name, value)

    def __getitem__(self, key: str):
        return self._values[key]

    def __setitem__(self, key: str, value):
        self.set(key, value)


class ConfigForm(Widget):
    """Declarative web widget rendering an automatic schema-driven form."""

    def __init__(self, config_store: ConfigStore, label: str = "Configuration", id: str = None):
        super().__init__(label=label, id=id or _generate_id("form"))
        self.config_store = config_store

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": "config_form",
            "label": self.label,
            "schema": self.config_store.schema,
            "values": self.config_store.to_dict(),
        }

    async def handle_event(self, event_name: str, val):
        """Handles inbound events from browser form submissions."""
        if event_name == "save" and isinstance(val, dict):
            try:
                self.config_store.update(val)
                if self.app:
                    await self.app._broadcast_toast("Settings saved successfully", level="info")
            except ConfigValidationError as err:
                if self.app:
                    await self.app._broadcast_toast(f"Validation Error: {str(err)}", level="error")
        elif event_name == "reset":
            self.config_store.reset_defaults()
            if self.app:
                await self.app._broadcast_toast("Settings reset to defaults", level="info")
