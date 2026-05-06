#!/usr/bin/env python3
"""Verify the daemon can click a Calculator button by coordinates."""

from __future__ import annotations

import json
import os
import selectors
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
TIMEOUT_SECONDS = 20.0


def run_checked(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def build_daemon() -> Path:
    run_checked(["swift", "build", "--arch", "arm64"])
    bin_path = run_checked(["swift", "build", "--arch", "arm64", "--show-bin-path"])
    daemon = Path(bin_path.stdout.strip()) / "axtree-daemon"
    if not daemon.exists():
        raise RuntimeError(f"Swift daemon binary was not created at {daemon}")
    return daemon


def open_calculator() -> None:
    subprocess.run(["open", "-a", "Calculator"], check=True)
    subprocess.run(
        ["osascript", "-e", 'tell application "Calculator" to activate'],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    time.sleep(1.0)


def terminate(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=2.0)
    except subprocess.TimeoutExpired:
        process.send_signal(signal.SIGKILL)
        process.wait(timeout=2.0)


def fail_for_permissions(stderr_text: str) -> None:
    if "Accessibility permission required" in stderr_text or "not allowed assistive access" in stderr_text:
        print(stderr_text.strip(), file=sys.stderr)
        print(
            "Grant Accessibility permission to the terminal or IDE running this test in "
            "System Settings > Privacy & Security > Accessibility, then re-run this script.",
            file=sys.stderr,
        )
        raise SystemExit(2)


class DaemonProbe:
    def __init__(self, process: subprocess.Popen[str]) -> None:
        self.process = process
        self.selector = selectors.DefaultSelector()
        assert process.stdout is not None
        assert process.stderr is not None
        self.selector.register(process.stdout, selectors.EVENT_READ, "stdout")
        self.selector.register(process.stderr, selectors.EVENT_READ, "stderr")
        self.stderr_lines: list[str] = []
        self.last_payloads: list[dict[str, Any]] = []

    def send(self, payload: dict[str, Any]) -> None:
        assert self.process.stdin is not None
        self.process.stdin.write(json.dumps(payload, separators=(",", ":")) + "\n")
        self.process.stdin.flush()

    def next_payload(self, timeout: float) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                stderr_text = "".join(self.stderr_lines)
                if self.process.stderr is not None:
                    stderr_text += self.process.stderr.read()
                fail_for_permissions(stderr_text)
                raise RuntimeError(
                    f"Daemon exited early with code {self.process.returncode}.\nSTDERR:\n{stderr_text}"
                )

            for key, _ in self.selector.select(timeout=0.25):
                line = key.fileobj.readline()
                if not line:
                    continue
                if key.data == "stderr":
                    self.stderr_lines.append(line)
                    fail_for_permissions("".join(self.stderr_lines))
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                self.last_payloads.append(payload)
                self.last_payloads = self.last_payloads[-5:]
                return payload

        stderr_text = "".join(self.stderr_lines)
        fail_for_permissions(stderr_text)
        raise TimeoutError(f"Timed out waiting for daemon JSON.\nSTDERR:\n{stderr_text}")

    def wait_for_state(self) -> dict[str, Any]:
        deadline = time.monotonic() + TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            payload = self.next_payload(max(0.1, deadline - time.monotonic()))
            if payload.get("type") == "state" and payload.get("appName") == "Calculator":
                return payload
        raise TimeoutError(f"Timed out waiting for Calculator state. Recent payloads: {self.last_payloads}")

    def wait_for_command_result(self, action: str) -> dict[str, Any]:
        deadline = time.monotonic() + TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            payload = self.next_payload(max(0.1, deadline - time.monotonic()))
            if payload.get("type") == "commandResult" and payload.get("action") == action:
                if payload.get("ok") is not True:
                    raise RuntimeError(f"Daemon reported failed command: {payload}")
                return payload
        raise TimeoutError(f"Timed out waiting for {action!r} command result.")


def label_for(element: dict[str, Any]) -> str:
    return str(element.get("title") or element.get("description") or "")


def find_button(state: dict[str, Any], labels: set[str]) -> dict[str, Any]:
    for element in state.get("elements", []):
        if not isinstance(element, dict) or element.get("role") != "AXButton":
            continue
        if label_for(element) in labels:
            return element
    raise LookupError(f"Could not find button labels {sorted(labels)} in Calculator state.")


def click_element(probe: DaemonProbe, element: dict[str, Any]) -> None:
    probe.send(
        {
            "action": "click",
            "coordinates": [element["centerX"], element["centerY"]],
        }
    )
    probe.wait_for_command_result("click")


def calculator_display_value() -> str:
    script = """
tell application "System Events"
    tell process "Calculator"
        value of static texts of scroll areas of group 1 of group 1 of splitter group 1 of group 1 of window 1
    end tell
end tell
"""
    result = run_checked(["osascript", "-e", script])
    values = [item.strip() for item in result.stdout.split(",") if item.strip()]
    if not values:
        raise RuntimeError("Calculator display did not expose any static text values.")
    return values[-1].replace("\u200e", "").strip()


def main() -> int:
    os.chdir(ROOT)
    daemon = build_daemon()
    open_calculator()

    process = subprocess.Popen(
        [str(daemon)],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.PIPE,
        bufsize=1,
    )
    probe = DaemonProbe(process)

    try:
        state = probe.wait_for_state()
        clear_button = find_button(state, {"All Clear", "Clear"})
        click_element(probe, clear_button)
        time.sleep(0.2)

        state = probe.wait_for_state()
        nine_button = find_button(state, {"9", "Nine"})
        click_element(probe, nine_button)
        time.sleep(0.5)
        display = calculator_display_value()
    finally:
        terminate(process)

    if display != "9":
        raise AssertionError(f"Expected Calculator display to be 9 after click, got {display!r}.")

    print(json.dumps({"ok": True, "clicked": "Nine", "display": display}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
