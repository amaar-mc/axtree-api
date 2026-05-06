#!/usr/bin/env python3
"""Comprehensive Notes evaluation for the AXTree API."""

from __future__ import annotations

import json
import subprocess
import sys
import time

from axtree_api import ActionAPI, DaemonError, DaemonManager, ElementNode, UIState


TEXT_ROLES = {"AXTextArea", "AXTextField"}
NOTE_TEXT = "Hello World"


def open_notes() -> None:
    subprocess.run(["open", "-a", "Notes"], check=True)
    subprocess.run(
        ["osascript", "-e", 'tell application "Notes" to activate'],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    time.sleep(2.0)


def find_new_note_button(state: UIState) -> ElementNode:
    button = state.find(
        role="AXButton",
        predicate=lambda element: element.label == "New Note",
    )
    if button is None:
        labels = sorted(element.label for element in state.elements if element.role == "AXButton")
        raise LookupError(f"New Note button not found. Available button labels: {labels}")
    return button


def focused_text_input(state: UIState) -> ElementNode | None:
    return state.find(
        predicate=lambda element: element.role in TEXT_ROLES and element.focused,
    )


def newest_note_body() -> str:
    result = subprocess.run(
        ["osascript", "-e", 'tell application "Notes" to get body of note 1 of default account'],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.stdout


def main() -> int:
    open_notes()

    try:
        with DaemonManager() as manager:
            actions = ActionAPI(manager)

            settled = manager.wait_for_state(app_name="Notes", timeout=20.0)
            new_note = find_new_note_button(settled)
            actions.click_element(new_note)

            focused_state = manager.wait_for_state(
                app_name="Notes",
                timeout=20.0,
                predicate=lambda state: focused_text_input(state) is not None,
            )
            target = focused_text_input(focused_state)
            if target is None:
                raise AssertionError("Notes did not expose a focused text input after New Note.")

            actions.type(NOTE_TEXT, timeout=10.0)
            time.sleep(1.0)
    except DaemonError as error:
        message = str(error)
        if "Accessibility permission required" in message:
            print(
                "Grant Accessibility permission to the terminal or IDE in "
                "System Settings > Privacy & Security > Accessibility, then re-run this script.",
                file=sys.stderr,
            )
        raise

    body = newest_note_body()
    if NOTE_TEXT not in body:
        raise AssertionError(f"Newest Notes body does not contain {NOTE_TEXT!r}: {body!r}")

    print(
        json.dumps(
            {
                "ok": True,
                "app": "Notes",
                "clicked": "New Note",
                "focusedRole": target.role,
                "typed": NOTE_TEXT,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
