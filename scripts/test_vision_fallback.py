#!/usr/bin/env python3
"""Verify localized screenshot fallback for an unlabeled AX node."""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

from axtree_api import DaemonManager, ElementNode, capture_element_screenshot, get_semantic_label_from_vision


ROOT = Path(__file__).resolve().parents[1]


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


def find_unlabeled_node(elements: tuple[ElementNode, ...]) -> ElementNode:
    for element in elements:
        if not element.title and element.width >= 10 and element.height >= 10:
            return element
    raise LookupError("No unlabeled element with usable bounds was found.")


def main() -> int:
    open_calculator()

    with DaemonManager() as manager:
        state = manager.wait_for_state(app_name="Calculator", timeout=15.0)
        element = find_unlabeled_node(state.elements)
        image_path = capture_element_screenshot(element, output_dir=ROOT / "artifacts" / "vision")

    label = get_semantic_label_from_vision(
        image_path,
        provider=lambda path: f"cropped:{path.name}",
    )
    if not label.startswith("cropped:"):
        raise AssertionError(f"Unexpected provider label: {label!r}")

    print(
        json.dumps(
            {
                "ok": True,
                "elementId": element.id,
                "role": element.role,
                "imagePath": str(image_path),
                "imageBytes": image_path.stat().st_size,
                "label": label,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
