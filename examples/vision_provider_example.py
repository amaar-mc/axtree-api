#!/usr/bin/env python3
"""Example: plug a local or hosted vision provider into AXTree for unlabeled controls."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Callable

from axtree_api import (
    DaemonManager,
    ElementNode,
    capture_element_screenshot,
    get_semantic_label_from_vision,
    UIState,
)

VisionProvider = Callable[[Path], str]


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


def my_vision_provider(cropped_image_path: Path) -> str:
    """Stub provider for an unlabeled cropped element.

    Replace this stub with a call to your own vision model or hosted
    Vision API. Keep secrets and API keys out of your repository by
    loading them from the environment or a secure config.

    Example:
        image_bytes = cropped_image_path.read_bytes()
        return call_my_vision_api(image_bytes)
    """

    # TODO: implement a real provider using a local VLM or hosted Vision API.
    return "unlabeled-icon"


def main() -> int:
    open_calculator()

    with DaemonManager() as manager:
        state = manager.wait_for_state(app_name="Calculator", timeout=15.0)
        element = find_unlabeled_node(state.elements)
        image_path = capture_element_screenshot(element)

        label = get_semantic_label_from_vision(
            image_path,
            provider=my_vision_provider,
        )

    print("Found unlabeled control and cropped its screenshot:")
    print(f"  element id: {element.id}")
    print(f"  role: {element.role}")
    print(f"  image path: {image_path}")
    print(f"  semantic label: {label}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
