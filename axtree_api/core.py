from __future__ import annotations

import json
import queue
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence


class DaemonError(RuntimeError):
    """Raised when the Swift daemon fails or reports an unusable state."""


@dataclass(frozen=True)
class ElementNode:
    id: str
    role: str
    title: str | None
    description: str | None
    x: float
    y: float
    width: float
    height: float
    center_x: float
    center_y: float
    focused: bool
    raw: dict[str, Any]

    @property
    def label(self) -> str:
        return self.title or self.description or ""


@dataclass(frozen=True)
class UIState:
    reason: str
    pid: int
    app_name: str
    bundle_identifier: str | None
    timestamp: str
    window_title: str | None
    elements: tuple[ElementNode, ...]
    raw: dict[str, Any]

    def find(
        self,
        *,
        role: str | None = None,
        label: str | None = None,
        predicate: Callable[[ElementNode], bool] | None = None,
    ) -> ElementNode | None:
        for element in self.elements:
            if role is not None and element.role != role:
                continue
            if label is not None and element.label != label:
                continue
            if predicate is not None and not predicate(element):
                continue
            return element
        return None


@dataclass(frozen=True)
class CommandResult:
    action: str
    ok: bool
    message: str
    timestamp: str
    raw: dict[str, Any]


class DaemonManager:
    """Launch and monitor the Swift AXTree daemon."""

    def __init__(
        self,
        binary_path: str | Path | None = None,
        *,
        repo_root: str | Path | None = None,
        build_if_missing: bool = True,
    ) -> None:
        self.repo_root = Path(repo_root).resolve() if repo_root else Path(__file__).resolve().parents[1]
        self.binary_path = Path(binary_path).resolve() if binary_path else None
        self.build_if_missing = build_if_missing
        self.process: subprocess.Popen[str] | None = None
        self.latest_state: UIState | None = None

        self._state_condition = threading.Condition()
        self._command_results: queue.Queue[CommandResult] = queue.Queue()
        self._errors: queue.Queue[str] = queue.Queue()
        self._stderr_lines: list[str] = []
        self._reader_threads: list[threading.Thread] = []
        self._stop_requested = threading.Event()

    def build(self) -> Path:
        subprocess.run(
            ["swift", "build", "--arch", "arm64"],
            cwd=self.repo_root,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        bin_path = subprocess.run(
            ["swift", "build", "--arch", "arm64", "--show-bin-path"],
            cwd=self.repo_root,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.binary_path = Path(bin_path.stdout.strip()) / "axtree-daemon"
        return self.binary_path

    def start(self) -> None:
        if self.process is not None and self.process.poll() is None:
            return

        binary = self.binary_path
        if binary is None:
            binary = self.build()
        elif self.build_if_missing and not binary.exists():
            binary = self.build()

        if not binary.exists():
            raise DaemonError(f"Swift daemon binary does not exist: {binary}")

        self._stop_requested.clear()
        self.process = subprocess.Popen(
            [str(binary)],
            cwd=self.repo_root,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self._reader_threads = [
            threading.Thread(target=self._read_stdout, name="axtree-stdout", daemon=True),
            threading.Thread(target=self._read_stderr, name="axtree-stderr", daemon=True),
        ]
        for thread in self._reader_threads:
            thread.start()

    def stop(self) -> None:
        self._stop_requested.set()
        process = self.process
        if process is None or process.poll() is not None:
            return

        process.terminate()
        try:
            process.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            process.send_signal(signal.SIGKILL)
            process.wait(timeout=2.0)

    def __enter__(self) -> DaemonManager:
        self.start()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.stop()

    @property
    def stderr_text(self) -> str:
        return "".join(self._stderr_lines)

    def wait_for_state(
        self,
        *,
        app_name: str | None = None,
        timeout: float = 10.0,
        predicate: Callable[[UIState], bool] | None = None,
    ) -> UIState:
        deadline = time.monotonic() + timeout
        with self._state_condition:
            while time.monotonic() < deadline:
                self._raise_if_failed()
                state = self.latest_state
                if state is not None:
                    app_matches = app_name is None or state.app_name == app_name
                    predicate_matches = predicate is None or predicate(state)
                    if app_matches and predicate_matches:
                        return state

                remaining = max(0.0, deadline - time.monotonic())
                self._state_condition.wait(timeout=min(0.25, remaining))

        self._raise_if_failed()
        raise TimeoutError(f"Timed out waiting for UI state matching app_name={app_name!r}.")

    def send_command(self, payload: dict[str, Any], *, timeout: float = 5.0) -> CommandResult:
        process = self._require_running_process()
        if process.stdin is None:
            raise DaemonError("Daemon stdin is not available.")

        action = str(payload.get("action", "unknown"))
        process.stdin.write(json.dumps(payload, separators=(",", ":")) + "\n")
        process.stdin.flush()
        return self.wait_for_command_result(action, timeout=timeout)

    def wait_for_command_result(self, action: str, *, timeout: float = 5.0) -> CommandResult:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self._raise_if_failed()
            try:
                result = self._command_results.get(timeout=min(0.25, max(0.0, deadline - time.monotonic())))
            except queue.Empty:
                continue
            if result.action == action:
                return result
        self._raise_if_failed()
        raise TimeoutError(f"Timed out waiting for command result for action {action!r}.")

    def _read_stdout(self) -> None:
        process = self.process
        if process is None or process.stdout is None:
            return

        for line in process.stdout:
            if self._stop_requested.is_set():
                break
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            self._handle_payload(payload)

    def _read_stderr(self) -> None:
        process = self.process
        if process is None or process.stderr is None:
            return

        for line in process.stderr:
            self._stderr_lines.append(line)
            if "Accessibility permission required" in line:
                self._errors.put(line.strip())

    def _handle_payload(self, payload: dict[str, Any]) -> None:
        payload_type = payload.get("type")
        if payload_type == "state":
            state = self._parse_state(payload)
            with self._state_condition:
                self.latest_state = state
                self._state_condition.notify_all()
        elif payload_type == "commandResult":
            self._command_results.put(self._parse_command_result(payload))
        elif payload_type == "error":
            self._errors.put(str(payload.get("message", "Unknown daemon error.")))

    def _parse_state(self, payload: dict[str, Any]) -> UIState:
        elements = tuple(self._parse_element(element) for element in payload.get("elements", []))
        return UIState(
            reason=str(payload.get("reason", "")),
            pid=int(payload.get("pid", 0)),
            app_name=str(payload.get("appName", "")),
            bundle_identifier=payload.get("bundleIdentifier"),
            timestamp=str(payload.get("timestamp", "")),
            window_title=payload.get("windowTitle"),
            elements=elements,
            raw=payload,
        )

    def _parse_element(self, payload: dict[str, Any]) -> ElementNode:
        return ElementNode(
            id=str(payload["id"]),
            role=str(payload["role"]),
            title=payload.get("title"),
            description=payload.get("description"),
            x=float(payload["x"]),
            y=float(payload["y"]),
            width=float(payload["width"]),
            height=float(payload["height"]),
            center_x=float(payload["centerX"]),
            center_y=float(payload["centerY"]),
            focused=bool(payload.get("focused", False)),
            raw=payload,
        )

    def _parse_command_result(self, payload: dict[str, Any]) -> CommandResult:
        return CommandResult(
            action=str(payload.get("action", "")),
            ok=bool(payload.get("ok", False)),
            message=str(payload.get("message", "")),
            timestamp=str(payload.get("timestamp", "")),
            raw=payload,
        )

    def _require_running_process(self) -> subprocess.Popen[str]:
        if self.process is None:
            raise DaemonError("Daemon has not been started.")
        if self.process.poll() is not None:
            raise DaemonError(f"Daemon exited with code {self.process.returncode}.\n{self.stderr_text}")
        return self.process

    def _raise_if_failed(self) -> None:
        if not self._errors.empty():
            raise DaemonError(self._errors.get_nowait())
        if self.process is not None and self.process.poll() is not None and not self._stop_requested.is_set():
            raise DaemonError(f"Daemon exited with code {self.process.returncode}.\n{self.stderr_text}")


class ActionAPI:
    """High-level action writer for a running daemon."""

    def __init__(self, manager: DaemonManager) -> None:
        self.manager = manager

    def click(self, x: float, y: float, *, timeout: float = 5.0) -> CommandResult:
        result = self.manager.send_command(
            {"action": "click", "coordinates": [x, y]},
            timeout=timeout,
        )
        if not result.ok:
            raise DaemonError(result.message)
        return result

    def click_element(self, element: ElementNode, *, timeout: float = 5.0) -> CommandResult:
        return self.click(element.center_x, element.center_y, timeout=timeout)

    def type(self, text: str, *, timeout: float = 5.0) -> CommandResult:
        result = self.manager.send_command({"action": "type", "text": text}, timeout=timeout)
        if not result.ok:
            raise DaemonError(result.message)
        return result

    def type_text(self, text: str, *, timeout: float = 5.0) -> CommandResult:
        return self.type(text, timeout=timeout)

    def key_press(
        self,
        key: str | None = None,
        *,
        key_code: int | None = None,
        modifiers: Sequence[str] | None = None,
        timeout: float = 5.0,
    ) -> CommandResult:
        if key is None and key_code is None:
            raise ValueError("key_press requires either key or key_code.")

        payload: dict[str, Any] = {"action": "keyPress"}
        if key is not None:
            payload["key"] = key
        if key_code is not None:
            payload["keyCode"] = key_code
        if modifiers:
            payload["modifiers"] = list(modifiers)

        result = self.manager.send_command(payload, timeout=timeout)
        if not result.ok:
            raise DaemonError(result.message)
        return result
