# AXTree API

AXTree API is a dual-stack macOS Computer Use API that combines low-latency Accessibility event streaming with a Python orchestration layer.

## Architecture

### Component A: Swift Daemon

The Swift daemon is a command-line process built with standard Apple frameworks:

- `ApplicationServices` for Accessibility and CoreGraphics APIs.
- `Cocoa` for application lifecycle notifications and run loop integration.

It observes the frontmost application with `AXObserver`, listens for high-value UI notifications, debounces event bursts for 300 ms, walks the frontmost window's Accessibility tree after the UI settles, filters for actionable elements, and emits flattened JSON state snapshots over stdout. It also accepts newline-delimited JSON commands over stdin for actions such as clicking and typing.

### Component B: Python Orchestrator

The Python package launches the Swift daemon as a subprocess, consumes state snapshots asynchronously, stores the latest UI tree as dataclasses, and exposes action methods that write JSON commands back to the daemon. It also provides a localized screenshot fallback for unlabeled nodes by cropping with the macOS `screencapture` CLI.

## Event Flow

1. The active application changes or posts Accessibility notifications.
2. The daemon resets a 300 ms debounce timer.
3. Once the timer fires, the daemon walks the frontmost window.
4. Actionable elements are serialized to stdout as JSON.
5. Python parses the stream, exposes the latest state, and sends actions to stdin.

## Permissions

macOS Accessibility permission is required for the daemon and for terminal-launched tests. Grant permission to the terminal or IDE that launches the process:

`System Settings > Privacy & Security > Accessibility`

## Repository Layout

- `Package.swift`: Swift package definition.
- `Sources/AXTreeDaemon`: Swift daemon source.
- `axtree_api`: Python orchestrator package.
- `scripts`: Manual and integration verification scripts.
- `tests`: Python unit tests.
