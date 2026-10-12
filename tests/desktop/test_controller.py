"""Qt ownership tests; injected observations are exclusively synthetic."""

import sys
import threading

import pytest
from PySide6.QtCore import QObject, QThread, QTimer, Slot

from firmavex.desktop.controller import DesktopController, _ACTIVE_LOCK, _ACTIVE_THREADS
from firmavex.product.errors import ProductError
from firmavex.product.supervisor import Supervisor


def synthetic(**values):
    return {"measurement_mode": "synthetic_test", **values}


def worker_event(sequence, kind="progress", **values):
    return {
        "schema_version": 1,
        "request_id": "synthetic-desktop-test",
        "sequence": sequence,
        "kind": kind,
        "payload": synthetic(**values),
    }


class FakeSupervisor:
    def __init__(self, action):
        self.action = action

    def execute(self, command, payload, *, cancel_event, event_callback):
        return self.action(command, payload, cancel_event, event_callback)


def controller_for(action):
    return DesktopController(_supervisor_factory=lambda: FakeSupervisor(action))


def collect(controller):
    values = {"events": [], "results": [], "errors": [], "busy": [], "idle": []}
    controller.event.connect(values["events"].append)
    controller.result.connect(values["results"].append)
    controller.error.connect(values["errors"].append)
    controller.busy_changed.connect(values["busy"].append)
    controller.idle.connect(lambda: values["idle"].append(True))
    return values


def wait_idle(qtbot, controller, timeout=3000):
    qtbot.waitUntil(lambda: not controller.busy, timeout=timeout)


def test_initial_idle_and_noop_cancel(qtbot):
    controller = controller_for(lambda *args: synthetic())
    assert controller.busy is False
    assert controller.cancel() is False
    assert controller.shutdown() is True


def test_normal_job_publishes_exact_result_after_cleanup(qtbot):
    cleaned = threading.Event()
    expected = synthetic(success=True, state="completed", attempted_executions=2)

    def action(command, payload, cancel, callback):
        assert command == "run"
        assert payload == {"config": "project.json", "output_dir": "new-run"}
        callback(worker_event(1, "accepted"))
        callback(worker_event(2, attempted_executions=2))
        cleaned.set()  # Simulates Supervisor returning only after cleanup.
        return expected

    controller = controller_for(action)
    values = collect(controller)
    controller.result.connect(lambda _: values.setdefault("cleaned_at_result", []).append(cleaned.is_set()))
    assert controller.start("run", {"config": "project.json", "output_dir": "new-run"})
    wait_idle(qtbot, controller)
    assert values["results"] == [expected]
    assert [event["sequence"] for event in values["events"]] == [1, 2]
    assert values["busy"] == [True, False]
    assert values["idle"] == [True]
    assert values["cleaned_at_result"] == [True]
    assert not values["errors"]


def test_gui_timer_stays_responsive_during_blocking_job(qtbot):
    entered = threading.Event()
    release = threading.Event()
    ticks = []

    def action(*args):
        entered.set()
        assert release.wait(2)
        return synthetic(success=True)

    controller = controller_for(action)
    timer = QTimer()
    timer.setInterval(5)
    timer.timeout.connect(lambda: ticks.append(True))
    timer.start()
    try:
        assert controller.start("doctor", {})
        qtbot.waitUntil(lambda: entered.is_set() and len(ticks) >= 4)
        assert controller.busy
    finally:
        release.set()
        wait_idle(qtbot, controller)
        timer.stop()


def test_double_start_never_dispatches_a_second_job(qtbot):
    release = threading.Event()
    invocations = []

    def action(command, *args):
        invocations.append(command)
        assert release.wait(2)
        return synthetic()

    controller = controller_for(action)
    values = collect(controller)
    try:
        assert controller.start("run", {})
        assert not controller.start("doctor", {})
        assert controller.busy
        assert values["busy"] == [True]
    finally:
        release.set()
        wait_idle(qtbot, controller)
    assert invocations == ["run"]
    assert values["busy"] == [True, False]


def test_cancel_is_thread_safe_and_cleanup_precedes_idle(qtbot):
    entered = threading.Event()
    cleaned = threading.Event()
    error = ProductError("cancelled", "Stopped", {"partial_result": synthetic(attempted_executions=1)})

    def action(command, payload, cancel, callback):
        entered.set()
        assert cancel.wait(2)
        cleaned.set()
        raise error

    controller = controller_for(action)
    values = collect(controller)
    controller.idle.connect(lambda: values.setdefault("cleaned_at_idle", []).append(cleaned.is_set()))
    assert controller.start("run", {})
    qtbot.waitUntil(entered.is_set)
    assert controller.cancel()
    assert controller.cancel()  # Cancellation request is idempotent.
    wait_idle(qtbot, controller)
    assert values["errors"] == [{**error.to_dict(), "exit_code": 130}]
    assert values["cleaned_at_idle"] == [True]
    assert values["results"] == []
    assert values["busy"] == [True, False]


def test_shutdown_requests_cancel_without_blocking_and_then_becomes_idle(qtbot):
    entered = threading.Event()
    cancellation_seen = threading.Event()
    cleanup_release = threading.Event()

    def action(command, payload, cancel, callback):
        entered.set()
        assert cancel.wait(2)
        cancellation_seen.set()
        assert cleanup_release.wait(2)
        return synthetic(success=False, outcome="cancelled")

    controller = controller_for(action)
    values = collect(controller)
    try:
        assert controller.start("run", {})
        qtbot.waitUntil(entered.is_set)
        assert controller.shutdown() is False
        qtbot.waitUntil(cancellation_seen.is_set)
        assert controller.busy
        assert values["idle"] == []
    finally:
        cleanup_release.set()
        wait_idle(qtbot, controller)
    assert controller.shutdown() is True
    assert values["results"][0]["outcome"] == "cancelled"


def test_original_product_error_and_administrator_diagnostics_are_preserved(qtbot):
    expected = ProductError("cleanup_failure", "Debugger cleanup failed", {"stderr": "diagnostic", "pids": [42]})

    def action(*args):
        raise expected

    controller = controller_for(action)
    values = collect(controller)
    controller.start("run", {})
    wait_idle(qtbot, controller)
    assert values["errors"] == [{**expected.to_dict(), "exit_code": 1}]
    assert not values["results"]
    assert values["busy"] == [True, False]


@pytest.mark.parametrize("exception", [RuntimeError("thread exploded"), KeyboardInterrupt("cancel"), SystemExit(9)])
def test_unexpected_background_exception_is_structured_and_restores_idle(qtbot, exception):
    def action(*args):
        raise exception

    controller = controller_for(action)
    values = collect(controller)
    controller.start("doctor", {})
    wait_idle(qtbot, controller)
    record = values["errors"][0]
    assert record["details"]["exception_type"] == type(exception).__name__
    assert record["details"]["diagnostic"] == str(exception)
    assert record["exit_code"] == (130 if isinstance(exception, (KeyboardInterrupt, SystemExit)) else 1)
    assert values["busy"] == [True, False]
    assert values["idle"] == [True]


def test_supervisor_factory_failure_is_structured(qtbot):
    def broken_factory():
        raise OSError("cannot initialize supervisor")

    controller = DesktopController(_supervisor_factory=broken_factory)
    values = collect(controller)
    controller.start("doctor", {})
    wait_idle(qtbot, controller)
    assert values["errors"][0]["details"]["exception_type"] == "OSError"


@pytest.mark.parametrize("command", ["cancel", "shutdown", "unknown", None, ["run"]])
def test_unsupported_job_is_rejected_before_admission(qtbot, command):
    called = []
    controller = controller_for(lambda *args: called.append(True))
    values = collect(controller)
    assert controller.start(command, {}) is False
    assert values["errors"][0]["category"] == "protocol_error"
    assert values["busy"] == []
    assert called == []


@pytest.mark.parametrize("payload", [None, [], {"value": float("nan")}, {"value": object()}])
def test_malformed_payload_never_dispatches(qtbot, payload):
    controller = controller_for(lambda *args: pytest.fail("Malformed job was dispatched"))
    values = collect(controller)
    assert controller.start("run", payload) is False
    assert values["errors"][0]["category"] == "protocol_error"
    assert not controller.busy


def test_submission_payload_is_independent_of_caller_mutation(qtbot):
    entered = threading.Event()
    release = threading.Event()
    observed = []

    def action(command, payload, *args):
        entered.set()
        assert release.wait(2)
        observed.append(payload)
        return synthetic()

    controller = controller_for(action)
    payload = {"nested": {"values": [1, 2]}}
    try:
        controller.start("run", payload)
        qtbot.waitUntil(entered.is_set)
        payload["nested"]["values"].append(3)
    finally:
        release.set()
        wait_idle(qtbot, controller)
    assert observed == [{"nested": {"values": [1, 2]}}]


def test_progress_is_copied_before_worker_reuses_its_record(qtbot):
    def action(command, payload, cancel, callback):
        event = worker_event(1, inputs=[1, 2])
        callback(event)
        event["payload"]["inputs"].append(3)
        return synthetic()

    controller = controller_for(action)
    values = collect(controller)
    controller.start("run", {})
    wait_idle(qtbot, controller)
    assert values["events"][0]["payload"]["inputs"] == [1, 2]


def test_all_public_updates_arrive_on_controller_owner_thread(qtbot):
    observed_threads = []
    execution_threads = []

    class Receiver(QObject):
        @Slot(dict)
        def record(self, _):
            observed_threads.append(QThread.currentThread())

        @Slot(bool)
        def busy(self, _):
            observed_threads.append(QThread.currentThread())

        @Slot()
        def idle(self):
            observed_threads.append(QThread.currentThread())

    def action(command, payload, cancel, callback):
        execution_threads.append(QThread.currentThread())
        callback(worker_event(1))
        return synthetic()

    controller = controller_for(action)
    receiver = Receiver()
    controller.event.connect(receiver.record)
    controller.result.connect(receiver.record)
    controller.error.connect(receiver.record)
    controller.busy_changed.connect(receiver.busy)
    controller.idle.connect(receiver.idle)
    controller.start("doctor", {})
    wait_idle(qtbot, controller)
    assert len(observed_threads) == 5
    assert all(thread == controller.thread() for thread in observed_threads)
    assert execution_threads[0] != controller.thread()


def test_failed_service_result_is_preserved_without_success_relabeling(qtbot):
    expected = synthetic(success=False, aborted=True, outcome="infrastructure_aborted", triggering_input=None)
    controller = controller_for(lambda *args: expected)
    values = collect(controller)
    controller.start("run", {})
    wait_idle(qtbot, controller)
    assert values["results"] == [expected]
    assert values["results"][0]["success"] is False
    assert values["results"][0]["aborted"] is True


@pytest.mark.parametrize("record", [None, [], "result"])
def test_nonobject_result_fails_closed(qtbot, record):
    controller = controller_for(lambda *args: record)
    values = collect(controller)
    controller.start("doctor", {})
    wait_idle(qtbot, controller)
    assert values["errors"][0]["category"] == "protocol_error"
    assert values["results"] == []


@pytest.mark.parametrize("nested", [False, True])
def test_synthetic_factory_cannot_claim_real_firmware(qtbot, nested):
    real = {"measurement_mode": "real_firmware"}
    result = synthetic(evidence=real) if nested else real
    controller = controller_for(lambda *args: result)
    values = collect(controller)
    controller.start("run", {})
    wait_idle(qtbot, controller)
    assert values["errors"][0]["category"] == "test_boundary_error"
    assert values["results"] == []


def test_real_label_in_injected_progress_is_rejected(qtbot):
    def action(command, payload, cancel, callback):
        record = worker_event(1)
        record["payload"]["measurement_mode"] = "real_firmware"
        callback(record)
        return synthetic()

    controller = controller_for(action)
    values = collect(controller)
    controller.start("run", {})
    wait_idle(qtbot, controller)
    assert values["errors"][0]["category"] == "test_boundary_error"
    assert values["events"] == []


def test_new_job_uses_a_fresh_cancellation_event(qtbot):
    events = []

    def action(command, payload, cancel, callback):
        events.append(cancel)
        if len(events) == 1:
            assert cancel.wait(2)
        else:
            assert not cancel.is_set()
        return synthetic()

    controller = controller_for(action)
    controller.start("run", {})
    controller.cancel()
    wait_idle(qtbot, controller)
    controller.start("doctor", {})
    wait_idle(qtbot, controller)
    assert events[0] is not events[1]


def test_job_started_from_busy_change_does_not_receive_stale_idle(qtbot):
    second_release = threading.Event()
    calls = []
    idle = []

    def action(command, *args):
        calls.append(command)
        if command == "validate":
            assert second_release.wait(2)
        return synthetic()

    controller = controller_for(action)
    controller.idle.connect(lambda: idle.append(True))

    def followup(busy):
        if not busy and len(calls) == 1:
            assert controller.start("validate", {})

    controller.busy_changed.connect(followup)
    try:
        controller.start("doctor", {})
        qtbot.waitUntil(lambda: calls == ["doctor", "validate"])
        assert controller.busy
        assert idle == []
    finally:
        second_release.set()
        wait_idle(qtbot, controller)
    assert idle == [True]


def test_nonowner_calls_are_rejected_without_state_mutation(qtbot):
    controller = controller_for(lambda *args: synthetic())
    failures = []

    def other_thread():
        try:
            controller.start("doctor", {})
        except RuntimeError as exc:
            failures.append(str(exc))

    thread = threading.Thread(target=other_thread)
    thread.start()
    thread.join(timeout=1)
    assert failures == ["DesktopController methods must run on its owning Qt thread."]
    assert not controller.busy


def test_destroyed_controller_requests_cleanup_without_destroying_active_thread(qtbot):
    entered = threading.Event()
    cleaned = threading.Event()

    def action(command, payload, cancel, callback):
        entered.set()
        assert cancel.wait(2)
        cleaned.set()
        return synthetic()

    controller = controller_for(action)
    controller.start("run", {})
    qtbot.waitUntil(entered.is_set)
    with qtbot.waitSignal(controller.destroyed, timeout=2000):
        controller.deleteLater()
    qtbot.waitUntil(cleaned.is_set)

    def no_active_threads():
        with _ACTIVE_LOCK:
            return not _ACTIVE_THREADS

    qtbot.waitUntil(no_active_threads)


def test_actual_host_worker_transport_and_cleanup_remain_off_gui_thread(qtbot):
    # This is a real Python subprocess transport test, not a firmware run.
    source = (
        "import sys,json; m=json.loads(sys.stdin.readline()); "
        "print(json.dumps({'schema_version':1,'request_id':m['request_id'],"
        "'sequence':1,'kind':'result','payload':{'measurement_mode':'synthetic_test',"
        "'success':True}}),flush=True)"
    )
    controller = DesktopController(
        _supervisor_factory=lambda: Supervisor([sys.executable, "-u", "-c", source], cancellation_grace=1)
    )
    values = collect(controller)
    controller.start("doctor", {})
    wait_idle(qtbot, controller, timeout=5000)
    assert values["results"] == [synthetic(success=True)]
    assert values["errors"] == []
    assert values["busy"] == [True, False]
