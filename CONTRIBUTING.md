# Contributing to `espmpui`

Thank you for your interest in contributing to `espmpui`! We welcome contributions of all kinds: bug fixes, new IoT widgets, documentation improvements, and feature requests.

---

## 🛠️ Development Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/csseeker/espmpui.git
   cd espmpui
   ```

2. **Create a virtual environment**:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -e .[dev]
   ```

---

## 🧪 Running Tests

`espmpui` has zero external runtime dependencies and runs tests using standard Python `unittest`:

```bash
make test
# or: python3 -m unittest discover -s tests -p "test_*.py"
```

---

## 🎨 Modifying Frontend Web Assets

The web dashboard SPA lives in `web/index.html`. It is a single-file, zero-dependency HTML/CSS/JavaScript application with an embedded canvas sparkline engine.

Whenever you make changes to `web/index.html`:
1. Test your changes locally in a browser or by running an example script.
2. Compile and compress the assets:
   ```bash
   make build-web
   # or: python3 web/build.py
   ```
3. This minifies and gzips the SPA to `< 5 KB` and regenerates `src/espmpui/assets.py`.
4. Commit both `web/index.html` and `src/espmpui/assets.py`.

> [!NOTE]
> The automated CI workflow will fail if `src/espmpui/assets.py` does not match the compiled output of `web/index.html`.

---

## 📋 Pull Request Guidelines

1. **Keep it lightweight**: Remember that `espmpui` runs on microcontroller flash and RAM. Avoid adding external C or Python dependencies.
2. **Preserve non-blocking safety**: Every I/O or network loop must cooperatively yield (`await asyncio.sleep_ms(0)`).
3. **Write tests**: Add unit tests in `tests/` for any new widget or protocol feature.
4. **Lint your code**: Run `make lint` (or `ruff check .`) before submitting.
