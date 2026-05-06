#!/usr/bin/env python3
"""Verify the Swift daemon emits Calculator button state snapshots."""

from __future__ import annotations

import json
import os
import selectors
import signal
import subprocess
import sys
import time
from pathlib import Path


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
    if "Accessibility permission required" in stderr_text:
        print(stderr_text.strip(), file=sys.stderr)
        print(
            "Grant Accessibility permission to the terminal or IDE running this test in "
            "System Settings > Privacy & Security > Accessibility, then re-run this script.",
            file=sys.stderr,
        )
        raise SystemExit(2)


def read_until_calculator_buttons(process: subprocess.Popen[str]) -> dict[str, object]:
    selector = selectors.DefaultSelector()
    assert process.stdout is not None
    assert process.stderr is not None
    selector.register(process.stdout, selectors.EVENT_READ, "stdout")
    selector.register(process.stderr, selectors.EVENT_READ, "stderr")

    stderr_lines: list[str] = []
    deadline = time.monotonic() + TIMEOUT_SECONDS

    while time.monotonic() < deadline:
        if process.poll() is not None:
            stderr_text = "".join(stderr_lines) + process.stderr.read()
            fail_for_permissions(stderr_text)
            raise RuntimeError(
                f"Daemon exited early with code {process.returncode}.\nSTDERR:\n{stderr_text}"
            )

        for key, _ in selector.select(timeout=0.25):
            line = key.fileobj.readline()
            if not line:
                continue

            if key.data == "stderr":
                stderr_lines.append(line)
                fail_for_permissions("".join(stderr_lines))
                continue

            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue

            if payload.get("type") != "state" or payload.get("appName") != "Calculator":
                continue

            elements = payload.get("elements", [])
            if not isinstance(elements, list):
                continue

            button_labels = {
                str(element.get("title") or element.get("description"))
                for element in elements
                if isinstance(element, dict) and element.get("role") == "AXButton"
            }
            if {"9", "8", "7"}.issubset(button_labels) or {
                "Nine",
                "Eight",
                "Seven",
            }.issubset(button_labels):
                return payload

    stderr_text = "".join(stderr_lines)
    fail_for_permissions(stderr_text)
    raise TimeoutError(
        "Timed out waiting for Calculator AXButton JSON containing labels 7, 8, and 9.\n"
        f"Daemon stderr:\n{stderr_text}"
    )


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
        bufsize=1,
    )

    try:
        payload = read_until_calculator_buttons(process)
    finally:
        terminate(process)

    elements = payload["elements"]
    buttons = [
        element
        for element in elements
        if isinstance(element, dict) and element.get("role") == "AXButton"
    ]
    print(
        json.dumps(
            {
                "ok": True,
                "appName": payload["appName"],
                "buttonCount": len(buttons),
                "sampleButtons": [
                    button.get("title") or button.get("description")
                    for button in buttons[:12]
                ],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
