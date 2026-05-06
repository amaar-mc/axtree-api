# AXTree API

Event-driven macOS computer use for agents.

AXTree API turns the macOS Accessibility tree into a small, real-time action map. A Swift daemon listens for UI changes, waits until the interface settles, emits a filtered JSON tree of interactive controls, and accepts action commands. A Python package runs the daemon, keeps the latest UI state in memory, and exposes a clean API for clicking, typing, pressing keys, and falling back to cropped screenshots when Accessibility labels are missing.

This is built for agent workflows where polling the whole screen is too slow and raw Accessibility output is too noisy.

The project is a developer preview: the core loop works against real macOS apps today, while the API surface is still intentionally small.

## Why This Exists

Most computer-use stacks spend too much time asking, "What is on screen right now?" AXTree API flips that around:

- macOS tells us when the UI changes.
- The daemon debounces event bursts for 300 ms.
- The frontmost window is walked only after it settles.
- Non-actionable nodes are filtered out.
- Agents receive click-ready controls with labels and bounds.

The result is a compact stream of actionable UI state instead of repeated full-screen inspection.

## What It Can Do

- Observe the frontmost macOS application with `AXObserver`.
- Listen for focused element, window-created, and element-destroyed notifications.
- Emit newline-delimited JSON state snapshots over stdout.
- Filter the tree to actionable controls: buttons, text fields, text areas, links, and checkboxes.
- Extract role, title, description, focus state, absolute bounds, and center coordinates.
- Accept JSON commands over stdin.
- Execute `click`, `type`, and `keyPress` actions.
- Launch and manage the daemon from Python.
- Maintain the latest UI state as Python dataclasses.
- Crop unlabeled elements with `screencapture -R` for vision-model fallback.

## Architecture

```text
macOS app
   |
   | Accessibility notifications
   v
Swift daemon
   - AXObserver
   - 300 ms debounce
   - frontmost-window tree walk
   - actionable-node filtering
   - stdout JSON state stream
   - stdin JSON command listener
   |
   | newline-delimited JSON
   v
Python orchestrator
   - subprocess lifecycle
   - async stdout/stderr readers
   - UIState / ElementNode dataclasses
   - ActionAPI click/type/keyPress helpers
   - localized screenshot fallback
```

The Swift side uses only standard Apple frameworks: `ApplicationServices`, `Cocoa`, and CoreGraphics APIs. The Python side uses the standard library only.

## Requirements

- macOS with Accessibility support.
- Apple Silicon Mac for the default build command used by the scripts.
- Swift toolchain.
- Python 3.11 or newer.
- Accessibility permission for the terminal or IDE launching the daemon.

Grant permission here:

```text
System Settings > Privacy & Security > Accessibility
```

If permission is missing, the daemon exits with a clear error and the test scripts print the same instruction.

## Quickstart

Clone the repo, install the Python package in editable mode, and build the daemon:

```bash
python3 -m pip install -e .
swift build --arch arm64
```

Run the beginner example:

```bash
examples/calculator_quickstart.py
```

It opens Calculator, finds buttons from the Accessibility tree, clicks `9 + 1`, presses Return, and prints the display value.

Run the basic Calculator stream check:

```bash
scripts/test_calculator_state.py
```

Run the full Notes evaluation:

```bash
scripts/evaluate_notes_e2e.py
```

That script opens Notes, waits for a settled UI state, finds the `New Note` button, clicks it, waits for the editor to focus, types `Hello World`, and verifies the newest note body.

## Python Usage

```python
import subprocess
import time

from axtree_api import ActionAPI, DaemonManager

subprocess.run(["open", "-a", "Calculator"], check=True)
time.sleep(1)

with DaemonManager() as manager:
    actions = ActionAPI(manager)
    state = manager.wait_for_state(app_name="Calculator", timeout=15)

    nine = state.find(
        role="AXButton",
        predicate=lambda element: element.label in {"9", "Nine"},
    )
    if nine is None:
        raise RuntimeError("Could not find the 9 button")

    actions.click_element(nine)
```

For keyboard navigation:

```python
actions.key_press("return")
actions.key_press("f", modifiers=["command"])
actions.key_press("escape")
actions.key_press(key_code=36)  # raw macOS virtual key code escape hatch
```

For text entry into the focused control:

```python
actions.type_text("Hello World")
```

## Examples

The `examples/` directory is for short scripts that are easy to read before touching the lower-level daemon protocol.

```bash
examples/calculator_quickstart.py
```

The integration checks in `scripts/` are more assertive: they verify behavior and raise errors if the live app state does not match expectations.

## Daemon Protocol

The daemon writes newline-delimited JSON state updates to stdout.

Example state payload:

```json
{
  "type": "state",
  "reason": "command.click",
  "pid": 12345,
  "appName": "Calculator",
  "bundleIdentifier": "com.apple.calculator",
  "timestamp": "2026-05-06T16:42:00Z",
  "windowTitle": "Calculator",
  "elements": [
    {
      "id": "0.0.0.0.0.9",
      "role": "AXButton",
      "title": null,
      "description": "All Clear",
      "x": 759,
      "y": 381,
      "width": 60,
      "height": 48,
      "centerX": 789,
      "centerY": 405,
      "focused": false
    }
  ]
}
```

The daemon reads newline-delimited JSON commands from stdin.

Click:

```json
{"action":"click","coordinates":[789,405]}
```

Type text:

```json
{"action":"type","text":"Hello World"}
```

Press a key:

```json
{"action":"keyPress","key":"return"}
```

Press a modified key:

```json
{"action":"keyPress","key":"f","modifiers":["command"]}
```

Successful commands produce a `commandResult` payload and then schedule a new debounced state snapshot.

## Vision Fallback

Some apps expose unlabeled icon buttons. AXTree API does not bundle a vision model, but it provides the local plumbing needed to use one.

```python
from axtree_api import capture_element_screenshot, get_semantic_label_from_vision

image_path = capture_element_screenshot(element)
label = get_semantic_label_from_vision(
    image_path,
    provider=lambda path: your_vision_client.describe(path),
)
```

The crop uses the element's Accessibility bounds and macOS `screencapture -R`, so the vision model sees only the relevant control instead of the full screen.

## Verification Scripts

All verification scripts are executable and live in `scripts/`.

```bash
scripts/test_calculator_state.py
scripts/test_calculator_click.py
scripts/test_python_calculator.py
scripts/test_keyboard_command.py
scripts/test_calculator_complex_expression.py
scripts/test_vision_fallback.py
scripts/evaluate_notes_e2e.py
```

What they cover:

- `test_calculator_state.py`: builds the daemon, opens Calculator, and verifies actionable button JSON.
- `test_calculator_click.py`: clicks Calculator's `Nine` button by emitted coordinates and verifies the display.
- `test_python_calculator.py`: drives `1 + 1 =` through the Python API and verifies `2`.
- `test_keyboard_command.py`: evaluates `1 + 1` with `keyPress("return")`.
- `test_calculator_complex_expression.py`: evaluates `((78+65)*(43-21))/11` and verifies `286`.
- `test_vision_fallback.py`: crops a real unlabeled Calculator control and runs the provider hook.
- `evaluate_notes_e2e.py`: opens Notes, creates a note, types `Hello World`, and verifies the app state.

Run a full local pass:

```bash
swift build --arch arm64
python3 -m compileall axtree_api examples scripts
examples/calculator_quickstart.py
scripts/test_calculator_state.py
scripts/test_calculator_click.py
scripts/test_python_calculator.py
scripts/test_keyboard_command.py
scripts/test_calculator_complex_expression.py
scripts/test_vision_fallback.py
scripts/evaluate_notes_e2e.py
```

These tests manipulate foreground macOS apps, so run them sequentially.

## Project Layout

```text
.
|-- .github/workflows/ci.yml
|-- CONTRIBUTING.md
|-- LICENSE
|-- Package.swift
|-- Sources/AXTreeDaemon/main.swift
|-- SECURITY.md
|-- axtree_api/
|   |-- __init__.py
|   |-- core.py
|   `-- vision.py
|-- examples/
|   `-- calculator_quickstart.py
|-- scripts/
|   |-- evaluate_notes_e2e.py
|   |-- test_calculator_click.py
|   |-- test_calculator_complex_expression.py
|   |-- test_calculator_state.py
|   |-- test_keyboard_command.py
|   |-- test_python_calculator.py
|   `-- test_vision_fallback.py
`-- pyproject.toml
```

## Open Source Notes

This project is released under the MIT License. See `LICENSE`.

Before contributing, read `CONTRIBUTING.md` for setup, test, and commit guidance. For safety expectations and vulnerability reporting, read `SECURITY.md`.

CI runs on GitHub-hosted macOS and covers:

- Python package installation.
- Python compile checks for `axtree_api`, `examples`, and `scripts`.
- Swift daemon build.
- Public Python API import checks.

The real GUI integration scripts are intentionally not run in CI because they require foreground macOS apps and Accessibility permissions.

## Current Limitations

- The daemon currently tracks the frontmost application and frontmost/focused window.
- Element ids are path-based within the current walked tree, not persistent cross-session object ids.
- The action surface is intentionally small: `click`, `type`, and `keyPress`.
- Vision fallback is a provider hook, not a bundled model.
- Tests require real macOS GUI apps and Accessibility permissions.

## Development Notes

Build the daemon:

```bash
swift build --arch arm64
```

Install the Python package locally:

```bash
python3 -m pip install -e .
```

The Python manager can build the Swift daemon automatically if no binary path is provided:

```python
with DaemonManager() as manager:
    state = manager.wait_for_state(timeout=10)
```

If you are debugging raw daemon output, run the built binary directly:

```bash
.build/arm64-apple-macosx/debug/axtree-daemon
```
