from __future__ import annotations

import subprocess
import tempfile
import time
from pathlib import Path
from typing import Callable

from .core import ElementNode


VisionProvider = Callable[[Path], str]


def capture_element_screenshot(
    element: ElementNode,
    *,
    output_dir: str | Path | None = None,
    filename_prefix: str = "axtree-node",
) -> Path:
    """Capture a cropped screenshot for an element's absolute screen bounds."""

    target_dir = Path(output_dir) if output_dir else Path(tempfile.gettempdir()) / "axtree-api"
    target_dir.mkdir(parents=True, exist_ok=True)

    timestamp = int(time.time() * 1000)
    safe_id = element.id.replace(".", "-")
    output_path = target_dir / f"{filename_prefix}-{safe_id}-{timestamp}.png"
    rect = f"{int(round(element.x))},{int(round(element.y))},{int(round(element.width))},{int(round(element.height))}"

    subprocess.run(
        ["screencapture", "-x", "-R", rect, str(output_path)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError(f"screencapture did not create a usable image at {output_path}")

    return output_path


def get_semantic_label_from_vision(
    image_path: str | Path,
    *,
    provider: VisionProvider | None = None,
) -> str:
    """Resolve a cropped element image to a semantic label through a caller-supplied Vision provider."""

    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(path)
    if provider is None:
        raise RuntimeError(
            "No Vision provider configured. Pass a callable that accepts the cropped image Path "
            "and returns a semantic label."
        )

    label = provider(path).strip()
    if not label:
        raise RuntimeError(f"Vision provider returned an empty label for {path}")
    return label


def label_unlabeled_element(
    element: ElementNode,
    *,
    output_dir: str | Path | None = None,
    provider: VisionProvider | None = None,
) -> str:
    """Capture and label an element when AXTitle is absent."""

    if element.title:
        return element.title

    image_path = capture_element_screenshot(element, output_dir=output_dir)
    return get_semantic_label_from_vision(image_path, provider=provider)
