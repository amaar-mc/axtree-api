#!/usr/bin/env python3
"""Small first-run example for AXTree API."""

from __future__ import annotations

import json
import subprocess
import time

from axtree_api import ActionAPI, DaemonManager, ElementNode, UIState


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


def calculator_display_value() -> str:
    script = """
tell application "System Events"
    tell process "Calculator"
        value of static texts of scroll areas of group 1 of group 1 of splitter group 1 of group 1 of window 1
    end tell
end tell
"""
    result = subprocess.run(
        ["osascript", "-e", script],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    values = [item.strip() for item in result.stdout.split(",") if item.strip()]
    if not values:
        raise RuntimeError("Calculator display did not expose a readable value.")
    return values[-1].replace("\u200e", "").strip()


def find_button(state: UIState, labels: set[str]) -> ElementNode:
    button = state.find(
        role="AXButton",
        predicate=lambda element: element.label in labels,
    )
    if button is None:
        available = sorted(
            element.label for element in state.elements if element.role == "AXButton" and element.label
        )
        raise RuntimeError(f"Could not find {sorted(labels)}. Available buttons: {available}")
    return button


def click_button(manager: DaemonManager, actions: ActionAPI, labels: set[str]) -> None:
    state = manager.wait_for_state(app_name="Calculator", timeout=10.0)
    actions.click_element(find_button(state, labels))
    time.sleep(0.2)


def main() -> int:
    open_calculator()

    with DaemonManager() as manager:
        actions = ActionAPI(manager)
        manager.wait_for_state(app_name="Calculator", timeout=15.0)

        click_button(manager, actions, {"All Clear", "Clear"})
        click_button(manager, actions, {"9", "Nine"})
        click_button(manager, actions, {"+", "Add"})
        click_button(manager, actions, {"1", "One"})
        actions.key_press("return")
        time.sleep(0.5)

    print(json.dumps({"expression": "9+1", "display": calculator_display_value()}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
