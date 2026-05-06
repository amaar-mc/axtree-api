"""Python bridge for the AXTree Swift daemon."""

from .core import ActionAPI, CommandResult, DaemonError, DaemonManager, ElementNode, UIState
from .vision import (
    capture_element_screenshot,
    get_semantic_label_from_vision,
    label_unlabeled_element,
)

__version__ = "0.1.0"

__all__ = [
    "ActionAPI",
    "CommandResult",
    "DaemonError",
    "DaemonManager",
    "ElementNode",
    "UIState",
    "__version__",
    "capture_element_screenshot",
    "get_semantic_label_from_vision",
    "label_unlabeled_element",
]
