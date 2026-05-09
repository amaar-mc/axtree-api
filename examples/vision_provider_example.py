#!/usr/bin/env python3
"""Example: plug a local or hosted vision provider into AXTree for unlabeled controls."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from axtree_api import (
    ElementNode,
    get_semantic_label_from_vision,
)


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
    # For demonstration purposes, since finding a truly unlabeled control
    # in Calculator may not be reliable, we use a synthetic ElementNode
    # to showcase the vision provider hook.
    element = ElementNode(
        id="synthetic-unlabeled-button",
        role="button",
        title=None,
        description=None,
        x=100.0,
        y=100.0,
        width=50.0,
        height=50.0,
        center_x=125.0,
        center_y=125.0,
        focused=False,
        raw={},
    )

    # Create a dummy image path for demonstration
    image_path = Path("/tmp/synthetic_screenshot.png")
    # In a real scenario, this would be: image_path = capture_element_screenshot(element)
    # For synthetic, we create a placeholder
    image_path.write_bytes(b"placeholder image data for demonstration")

    label = get_semantic_label_from_vision(
        image_path,
        provider=my_vision_provider,
    )

    print("Demonstrated vision provider with synthetic unlabeled control:")
    print(f"  element id: {element.id}")
    print(f"  role: {element.role}")
    print(f"  image path: {image_path}")
    print(f"  semantic label: {label}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
