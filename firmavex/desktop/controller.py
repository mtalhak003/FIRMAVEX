"""Responsive Qt ownership of the existing supervised product worker.

The GUI never runs firmware services in its own process.  A job's blocking
``Supervisor.execute`` call lives in a QThread, while every public signal is
emitted by the controller on its owning Qt thread.  A terminal result is not
published until the supervisor has returned from its process cleanup.
"""

from __future__ import annotations

import copy
import threading
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QThread, Qt, Signal, Slot

from firmavex.product.errors import ProductError
from firmavex.product.protocol import COMMANDS, decode_command, encode_command
from firmavex.product.supervisor import Supervisor


# An accidentally destroyed view must not destroy a still-running QThread.
# Its cancellation event is set on controller destruction; the independent
# reference lasts until the supervised worker has finished cleanup.  Normal
# window shutdown should instead wait for the controller's idle signal.
_ACTIVE_THREADS: set[QThread] = set()
_ACTIVE_LOCK = threading.Lock()


def _reject_real_test_labels(value: Any) -> None:
    """Keep an injected synthetic supervisor from claiming firmware evidence."""
    if type(value) is dict:
        if value.get("measurement_mode") == "real_firmware":
            raise ProductError(
                "test_boundary_error",
                "An injected desktop supervisor cannot claim real firmware execution.",
                {"measurement_mode": "synthetic_test"},
            )
        for item in value.values():
            _reject_real_test_labels(item)
    elif type(value) is list:
        for item in value:
            _reject_real_test_labels(item)


def _error_record(exc: BaseException) -> dict[str, Any]:
    if isinstance(exc, ProductError):
        record = copy.deepcopy(exc.to_dict())
        record["exit_code"] = 130 if exc.category == "cancelled" else 1
        return record
    if isinstance(exc, (KeyboardInterrupt, SystemExit)):
        return {
            "category": "cancelled",
            "message": "Execution was interrupted. Inspect saved results before restarting.",
            "details": {"exception_type": type(exc).__name__, "diagnostic": str(exc)},
            "exit_code": 130,
        }
    return {
        "category": "desktop_worker_failure",
        "message": "The background execution controller failed.",
        "details": {"exception_type": type(exc).__name__, "diagnostic": str(exc)},
        "exit_code": 1,
    }


class _ExecutionThread(QThread):
    progress = Signal(dict)

    def __init__(
        self,
        command: str,
        payload: dict[str, Any],
        cancel_event: threading.Event,
        supervisor_factory: Callable[[], Supervisor],
        *,
        synthetic: bool,
    ) -> None:
        super().__init__()
        self.command = command
        self.payload = payload
        self.cancel_event = cancel_event
        self.supervisor_factory = supervisor_factory
        self.synthetic = synthetic
        self.terminal: tuple[str, dict[str, Any]] | None = None
        self.setObjectName("FIRMAVEX supervised execution")

    def run(self) -> None:
        try:
            supervisor = self.supervisor_factory()

            def progress(message: dict[str, Any]) -> None:
                if type(message) is not dict:
                    raise ProductError("protocol_error", "Worker event must be an object.")
                snapshot = copy.deepcopy(message)
                if self.synthetic:
                    _reject_real_test_labels(snapshot)
                self.progress.emit(snapshot)

            final = supervisor.execute(
                self.command,
                self.payload,
                cancel_event=self.cancel_event,
                event_callback=progress,
            )
            if type(final) is not dict:
                raise ProductError("protocol_error", "Worker result must be an object.")
            snapshot = copy.deepcopy(final)
            if self.synthetic:
                _reject_real_test_labels(snapshot)
            # Failed/aborted records remain failed/aborted.  Receiving a final
            # result means the record is available, not that testing succeeded.
            self.terminal = ("result", snapshot)
        except BaseException as exc:
            # These exceptions occur in this private thread, rather than the
            # application's main thread.  Normal worker cancellation already
            # persists its record and cleans resources before arriving here.
            self.terminal = ("error", _error_record(exc))


class DesktopController(QObject):
    """One asynchronous supervised job at a time, owned by the GUI thread.

    ``result`` carries the exact final service record, including failed result
    fields.  ``error`` carries category/message/details and an exit_code (130
    for cancellation).  ``event`` forwards ordered worker envelopes.  The
    private ``_supervisor_factory`` is a synthetic-test seam; production always
    constructs the existing Supervisor and therefore its separate worker.
    """

    event = Signal(dict)
    result = Signal(dict)
    error = Signal(dict)
    busy_changed = Signal(bool)
    idle = Signal()

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        _supervisor_factory: Callable[[], Supervisor] | None = None,
    ) -> None:
        super().__init__(parent)
        self._supervisor_factory = _supervisor_factory or Supervisor
        self._synthetic = _supervisor_factory is not None
        self._busy = False
        self._thread: _ExecutionThread | None = None
        self._cancel_event: threading.Event | None = None

    @property
    def busy(self) -> bool:
        return self._busy

    def _require_owner_thread(self) -> None:
        if QThread.currentThread() != self.thread():
            raise RuntimeError("DesktopController methods must run on its owning Qt thread.")

    @Slot(str, dict, result=bool)
    def start(self, command: str, payload: dict[str, Any]) -> bool:
        self._require_owner_thread()
        if self._busy:
            return False
        try:
            # Use the established transport validator and an independent JSON
            # snapshot, so callers cannot mutate a queued job's configuration.
            if type(command) is not str or command not in COMMANDS or command in {"cancel", "shutdown"}:
                raise ProductError("protocol_error", "Unsupported desktop job command.")
            values = decode_command(encode_command("desktop", command, payload))["payload"]
        except ProductError as exc:
            self.error.emit(_error_record(exc))
            return False
        cancellation = threading.Event()
        task = _ExecutionThread(
            command, values, cancellation, self._supervisor_factory, synthetic=self._synthetic
        )
        task.progress.connect(self._forward_event, Qt.ConnectionType.QueuedConnection)
        task.finished.connect(self._finished, Qt.ConnectionType.QueuedConnection)
        self.destroyed.connect(cancellation.set)

        def release() -> None:
            with _ACTIVE_LOCK:
                _ACTIVE_THREADS.discard(task)

        task.finished.connect(release, Qt.ConnectionType.DirectConnection)
        task.finished.connect(task.deleteLater)
        with _ACTIVE_LOCK:
            _ACTIVE_THREADS.add(task)
        self._thread = task
        self._cancel_event = cancellation
        self._busy = True
        self.busy_changed.emit(True)
        task.start()
        return True

    @Slot(result=bool)
    def cancel(self) -> bool:
        self._require_owner_thread()
        if not self._busy or self._cancel_event is None:
            return False
        self._cancel_event.set()
        return True

    @Slot(result=bool)
    def shutdown(self) -> bool:
        """Request cancellation without blocking; True means already idle."""
        self._require_owner_thread()
        if self._busy:
            self.cancel()
            return False
        return True

    @Slot(dict)
    def _forward_event(self, message: dict[str, Any]) -> None:
        self.event.emit(message)

    @Slot()
    def _finished(self) -> None:
        task = self._thread
        if task is None or self.sender() != task:
            return
        self._thread = None
        cancellation = self._cancel_event
        self._cancel_event = None
        if cancellation is not None:
            self.destroyed.disconnect(cancellation.set)
        terminal = task.terminal
        if terminal is None:
            terminal = (
                "error",
                _error_record(ProductError("desktop_worker_failure", "Background job ended without a final record.")),
            )
        kind, value = terminal
        if kind == "result":
            self.result.emit(value)
        else:
            self.error.emit(value)
        self._busy = False
        self.busy_changed.emit(False)
        # A receiver may start another job in response to busy_changed(False).
        # Do not report idle for a newly admitted active job.
        if not self._busy:
            self.idle.emit()
