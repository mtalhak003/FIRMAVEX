"""Contract tests plus actual tools; never promote mocks to qualification."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
import time
import pytest
from firmavex.backends import Limits, Request, execute, inspect_run, profiles
from firmavex.backends.process import Processes, Cancelled
from firmavex.backends.cli import main

EXAMPLES = Path(__file__).resolve().parents[2] / "firmavex/backends/examples"


def required(*names):
    missing = [name for name in names if not shutil.which(name)]
    if missing:
        if os.environ.get("FIRMAVEX_REQUIRE_BACKENDS") == "1":
            pytest.fail(str(missing))
        pytest.skip("Missing real tools: " + ",".join(missing))
    if os.name != "posix":
        pytest.skip("New native Windows paths not qualified")


@pytest.mark.parametrize("limit", [0, -1, float("nan"), float("inf"), True, 3601])
def test_invalid_limit(limit):
    with pytest.raises(ValueError):
        Limits(limit)


@pytest.mark.parametrize("values", [(True, 1), (-1, 1), (2**32, 1), (1,), [1, 2]])
def test_invalid_vector(values):
    with pytest.raises(ValueError):
        Request("riscv32-virt", Path("x"), values)


def test_profiles_are_distinct():
    assert profiles["verilog-icarus"].capabilities.input_kind == "source-testbench"
    assert profiles["riscv32-virt"].capabilities.input_kind == "uint32-vector"
    assert not any(p.capabilities.sandboxed for p in profiles.values())
    assert main(["profiles"]) == 0


def test_fresh_directory_only(tmp_path):
    with pytest.raises(FileExistsError):
        execute(Request("verilog-icarus", Path("x")), tmp_path)


def test_missing_source_persists_failure(tmp_path):
    result = execute(Request("verilog-icarus", tmp_path / "missing"), tmp_path / "out")
    assert result["status"] == "infrastructure_failure"
    assert inspect_run(tmp_path / "out") == result


def test_unknown_accounting(tmp_path):
    (tmp_path / "admission.json").write_text('{"attempt_id":"x"}')
    assert inspect_run(tmp_path)["status"] == "incomplete"
    assert "unknown" in inspect_run(tmp_path)["evidence"]["accounting"]


def test_precancel(tmp_path):
    required("iverilog", "vvp")
    cancel = threading.Event()
    cancel.set()
    result = execute(
        Request("verilog-icarus", EXAMPLES / "counter.v"), tmp_path / "out", cancel
    )
    assert result["status"] == "cancelled"
    assert result["evidence"]["cleanup"] == []


@pytest.mark.parametrize("kind", ["pass", "fail", "invalid", "timeout", "cancel"])
def test_real_hdl(tmp_path, kind):
    required("iverilog", "vvp")
    source = tmp_path / "input.v"
    text = (EXAMPLES / "counter.v").read_text()
    if kind == "fail":
        text = text.replace("count===3", "count===4")
    if kind == "invalid":
        text = "module testbench; broken syntax endmodule"
    if kind in {"timeout", "cancel"}:
        text = "module testbench; initial forever #1; endmodule"
    source.write_text(text)
    cancel = threading.Event()
    timer = threading.Timer(0.4, cancel.set) if kind == "cancel" else None
    if timer:
        timer.start()
    try:
        result = execute(
            Request("verilog-icarus", source, limits=Limits(0.8)),
            tmp_path / "out",
            cancel,
        )
    finally:
        if timer:
            timer.cancel()
            timer.join()
    assert (
        result["status"]
        == {
            "pass": "passed",
            "fail": "triggered",
            "invalid": "invalid_input",
            "timeout": "infrastructure_failure",
            "cancel": "cancelled",
        }[kind]
    ), result
    assert result["evidence"]["cleanup_verified"]
    assert all(p["reaped"] for p in result["evidence"]["cleanup"])
    if kind in {"pass", "fail"}:
        assert result["evidence"]["measurement_mode"] == "real_simulation"
        assert result["evidence"]["artifacts"][0]["sha256"]
        assert inspect_run(tmp_path / "out") == result


@pytest.fixture
def rv_image(tmp_path):
    required("riscv64-unknown-elf-gcc", "qemu-system-riscv32", "gdb-multiarch")
    image = tmp_path / "example.elf"
    command = [
        "riscv64-unknown-elf-gcc",
        "-march=rv32im",
        "-mabi=ilp32",
        "-g",
        "-O0",
        "-ffreestanding",
        "-nostdlib",
        "-Wl,--build-id=none",
        "-T",
        str(EXAMPLES / "riscv.ld"),
        str(EXAMPLES / "riscv.S"),
        str(EXAMPLES / "riscv.c"),
        "-o",
        str(image),
    ]
    subprocess.run(command, check=True, capture_output=True)
    return image


@pytest.mark.parametrize(
    "values,expected", [((0, 0), "passed"), ((2, 1), "triggered"), ((2, 0), "passed")]
)
def test_actual_riscv(rv_image, tmp_path, values, expected):
    result = execute(Request("riscv32-virt", rv_image, values), tmp_path / "out")
    assert result["status"] == expected, result
    assert result["evidence"]["observation"]["inputs_read_back"] == dict(
        zip(("input_a", "input_b"), values)
    )
    assert result["evidence"]["completion_observed"]
    assert result["evidence"]["cleanup_verified"]
    assert inspect_run(tmp_path / "out") == result


def test_riscv_cancellation(rv_image, tmp_path):
    cancel = threading.Event()
    cancel.set()
    result = execute(
        Request("riscv32-virt", rv_image, (2, 1)), tmp_path / "out", cancel
    )
    assert result["status"] == "cancelled"
    assert not result["evidence"]["completion_observed"]


def test_reject_non_riscv(tmp_path):
    source = tmp_path / "bad.elf"
    source.write_bytes(b"not elf")
    result = execute(Request("riscv32-virt", source, (0, 0)), tmp_path / "out")
    assert result["status"] == "infrastructure_failure"
    assert "real_firmware" not in json.dumps(result)


def test_reject_external_hdl_operations(tmp_path):
    source = tmp_path / "a.v"
    source.write_text('module testbench; initial $system("touch x"); endmodule')
    result = execute(Request("verilog-icarus", source), tmp_path / "out")
    assert result["status"] == "infrastructure_failure"
    assert not (tmp_path / "out/x").exists()


@pytest.mark.parametrize("profile", ["riscv32-virt", "verilog-icarus"])
def test_reproduction_export(tmp_path, profile):
    from firmavex.backends.examples import prepare
    from firmavex.backends.report import reproduce, export

    required(
        *(
            ("riscv64-unknown-elf-gcc", "qemu-system-riscv32", "gdb-multiarch")
            if profile == "riscv32-virt"
            else ("iverilog", "vvp")
        )
    )
    prepare(profile, tmp_path / "build")
    source = (
        tmp_path
        / "build"
        / ("firmware.elf" if profile == "riscv32-virt" else "counter.v")
    )
    request = Request(profile, source, (2, 1) if profile == "riscv32-virt" else ())
    original = execute(request, tmp_path / "run")
    replay = reproduce(tmp_path / "run", tmp_path / "replay")
    assert replay["outcome_matches"]
    assert replay["result"]["evidence"]["cleanup_verified"]
    exported = export(tmp_path / "run", tmp_path / "report")
    assert exported["status"] == "exported"
    assert "hardware validation" in (tmp_path / "report/REPORT.md").read_text()
    assert inspect_run(tmp_path / "run") == original
    snapshot = (
        tmp_path
        / "run"
        / ("firmware.elf" if profile == "riscv32-virt" else "testbench.v")
    )
    snapshot.write_bytes(b"changed")
    with pytest.raises(ValueError, match="no longer matches"):
        reproduce(tmp_path / "run", tmp_path / "bad-replay")
    assert not (tmp_path / "bad-replay").exists()


@pytest.mark.parametrize("exception", [KeyboardInterrupt, SystemExit])
def test_interruption_persisted_and_reraised(tmp_path, monkeypatch, exception):
    from firmavex.backends.implementations import IcarusBackend

    def interrupt(*args):
        raise exception("control flow")

    monkeypatch.setattr(IcarusBackend, "execute", interrupt)
    with pytest.raises(exception):
        execute(Request("verilog-icarus", Path("x")), tmp_path / "out")
    assert inspect_run(tmp_path / "out")["status"] == "cancelled"
    assert exception.__name__ in inspect_run(tmp_path / "out")["evidence"]["error"]


def test_cleanup_error_not_masked(tmp_path, monkeypatch):
    required("iverilog", "vvp")
    original = Processes.close

    def failing(self):
        original(self)
        raise RuntimeError("injected cleanup failure")

    monkeypatch.setattr(Processes, "close", failing)
    result = execute(
        Request("verilog-icarus", EXAMPLES / "counter.v"), tmp_path / "out"
    )
    assert result["status"] == "infrastructure_failure"
    assert "cleanup failure" in result["evidence"]["error"]


def test_cleanup_error_does_not_replace_cancellation(tmp_path, monkeypatch):
    from firmavex.backends.implementations import finish

    class Broken:
        def close(self):
            raise RuntimeError("cleanup")

    primary = KeyboardInterrupt("original")
    assert finish(Broken(), primary) is False
    assert "Cleanup failed" in primary.__notes__[0]


@pytest.mark.parametrize(
    "source",
    [
        'module testbench; initial $dumpfile("/tmp/escape.vcd"); endmodule',
        'module testbench; initial $readmemh("x",x); endmodule',
    ],
)
def test_reject_unowned_artifacts(tmp_path, source):
    path = tmp_path / "a.v"
    path.write_text(source)
    result = execute(Request("verilog-icarus", path), tmp_path / "out")
    assert result["status"] == "infrastructure_failure"
    assert result["evidence"].get("measurement_mode") != "real_simulation"


def test_process_output_limit(tmp_path):
    import sys

    processes = Processes(threading.Event(), Limits(log_bytes=1024))
    try:
        with pytest.raises(RuntimeError, match="Output limit"):
            processes.run([sys.executable, "-c", 'print("a"*10000)'], tmp_path)
    finally:
        processes.close()
    assert all(p["reaped"] for p in processes.cleanup)


def test_real_arm_adapter(tmp_path):
    required("qemu-system-arm", "arm-none-eabi-gdb")
    from firmavex.product.services import prepare_example_project

    prepared = prepare_example_project(tmp_path / "example")
    config = tmp_path / "example/project.json"
    # Existing data format and established evaluator/search are delegated.
    result = execute(Request("cortex-m3-mps2", config), tmp_path / "out")
    assert result["status"] not in {"infrastructure_failure", "invalid_output"}, result
    legacy = result["evidence"]["legacy_result"]
    assert legacy["triggering_input"] == [2, 1], legacy


@pytest.mark.parametrize("cancelled", [True, False])
def test_real_riscv_missing_completion_not_triggered(tmp_path, cancelled):
    required("riscv64-unknown-elf-gcc", "qemu-system-riscv32", "gdb-multiarch")
    source = tmp_path / "loop.c"
    source.write_text(
        (EXAMPLES / "riscv.c")
        .read_text()
        .replace("    benchmark_complete();", "    failure_flag = 1;")
    )
    image = tmp_path / "loop.elf"
    subprocess.run(
        [
            "riscv64-unknown-elf-gcc",
            "-march=rv32im",
            "-mabi=ilp32",
            "-g",
            "-O0",
            "-ffreestanding",
            "-nostdlib",
            "-T",
            str(EXAMPLES / "riscv.ld"),
            str(EXAMPLES / "riscv.S"),
            str(source),
            "-o",
            str(image),
        ],
        check=True,
        capture_output=True,
    )
    cancel = threading.Event()
    timer = threading.Timer(0.4, cancel.set) if cancelled else None
    if timer:
        timer.start()
    try:
        result = execute(
            Request("riscv32-virt", image, (2, 1), Limits(0.8)),
            tmp_path / "out",
            cancel,
        )
    finally:
        if timer:
            timer.cancel()
            timer.join()
    assert result["status"] == (
        "cancelled" if cancelled else "infrastructure_failure"
    ), result
    assert not result["evidence"]["completion_observed"]
    assert result["evidence"]["cleanup_verified"]
    assert all(p["reaped"] for p in result["evidence"]["cleanup"])
    assert result["evidence"]["process_logs"]


def test_arm_limits_not_silently_ignored():
    with pytest.raises(ValueError, match="ARM limits"):
        Request("cortex-m3-mps2", Path("x"), limits=Limits(3))


def test_reproducible_local_riscv_build(tmp_path):
    required("riscv64-unknown-elf-gcc")
    from firmavex.backends.examples import prepare

    first = prepare("riscv32-virt", tmp_path / "first build")
    second = prepare("riscv32-virt", tmp_path / "second build")
    assert first["firmware"]["sha256"] == second["firmware"]["sha256"]
    assert not first["execution_performed"]


def test_wire_roundtrip_and_strict_fields():
    from firmavex.backends.api import request_from_dict, request_to_dict

    request = Request("riscv32-virt", Path("firmware.elf"), (2, 1))
    record = request_to_dict(request)
    assert request_from_dict(record) == request
    with pytest.raises(ValueError):
        request_from_dict({**record, "unknown": 1})
    with pytest.raises(ValueError):
        request_from_dict({**record, "schema_version": True})
    with pytest.raises(ValueError):
        request_from_dict({**record, "limits": {"unknown": 1}})


@pytest.mark.parametrize(
    "text",
    [
        'module testbench; initial begin $display("FIRMAVEX_TEST_RESULT=PASS"); $display("FIRMAVEX_TEST_RESULT=FAIL"); $finish; end endmodule',
        "module testbench; initial $finish; endmodule",
    ],
)
def test_real_hdl_ambiguous_output(tmp_path, text):
    required("iverilog", "vvp")
    path = tmp_path / "a.v"
    path.write_text(text)
    result = execute(Request("verilog-icarus", path), tmp_path / "out")
    assert result["status"] == "invalid_output"
    assert result["evidence"]["cleanup_verified"]


def test_frozen_execution_explicitly_blocked(tmp_path, monkeypatch):
    import sys

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    processes = Processes(threading.Event(), Limits())
    with pytest.raises(RuntimeError, match="frozen launcher"):
        processes.spawn([sys.executable, "-c", "pass"], tmp_path)
    assert not processes.children


def test_owned_descendant_cleanup(tmp_path):
    if os.name != "posix":
        pytest.skip("POSIX ownership test")
    import sys

    cancel = threading.Event()
    processes = Processes(cancel, Limits(0.5))
    code = 'import subprocess,sys,time; p=subprocess.Popen([sys.executable,"-c","import time; time.sleep(30)"]); print(p.pid,flush=True); time.sleep(30)'
    try:
        with pytest.raises(TimeoutError):
            processes.run([sys.executable, "-c", code], tmp_path)
        descendant = int(processes.children[0][1].text().strip())
    finally:
        processes.close()
    assert all(p["reaped"] for p in processes.cleanup)
    if Path("/proc").exists():
        state = Path(f"/proc/{descendant}/stat")
        assert not state.exists() or state.read_text().split()[2] == "Z"


def test_persistence_error_preserves_original_interrupt(tmp_path, monkeypatch):
    from firmavex.backends import engine
    from firmavex.backends.implementations import IcarusBackend

    original = engine._write

    def broken(path, record):
        if path.name == "result.json":
            raise OSError("disk unavailable")
        original(path, record)

    def interrupt(*args):
        raise KeyboardInterrupt("original cancellation")

    monkeypatch.setattr(engine, "_write", broken)
    monkeypatch.setattr(IcarusBackend, "execute", interrupt)
    with pytest.raises(KeyboardInterrupt, match="original cancellation") as captured:
        execute(Request("verilog-icarus", Path("x")), tmp_path / "out")
    assert "disk unavailable" in captured.value.__notes__[0]
    assert inspect_run(tmp_path / "out")["status"] == "incomplete"


def test_total_deadline_not_reset_between_tools(tmp_path):
    if os.name != "posix":
        pytest.skip("POSIX limits")
    import sys

    processes = Processes(threading.Event(), Limits(0.3))
    try:
        processes.run([sys.executable, "-c", "import time;time.sleep(.15)"], tmp_path)
        with pytest.raises(TimeoutError):
            processes.run(
                [sys.executable, "-c", "import time;time.sleep(.25)"], tmp_path
            )
    finally:
        processes.close()


def test_actual_compatibility_is_not_execution(tmp_path):
    required("iverilog", "vvp")
    from firmavex.backends.compatibility import check

    result = check("verilog-icarus")
    assert result["status"] == "tools_available"
    assert result["guest_execution_performed"] is False
    assert "not established" in result["native_qualification"]
    assert result["tools"]["iverilog"]["identity"]["sha256"]


def test_drain_setup_failure_still_owns_and_reaps_child(tmp_path, monkeypatch):
    if os.name != "posix":
        pytest.skip("POSIX ownership")
    import sys
    from firmavex.backends import process

    original = process._Drain
    calls = 0

    def broken(stream, limit):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("reader setup failed")
        return original(stream, limit)

    monkeypatch.setattr(process, "_Drain", broken)
    processes = Processes(threading.Event(), Limits())
    try:
        with pytest.raises(RuntimeError, match="reader setup failed"):
            processes.spawn(
                [sys.executable, "-c", "import time;time.sleep(30)"], tmp_path
            )
    finally:
        processes.close()
    child = processes.children[0][0]
    assert child.poll() is not None
    assert child.stdout.closed and child.stderr.closed


@pytest.mark.parametrize(
    "status,expected", [("unsupported_platform", 1), ("tools_available", 0)]
)
def test_cli_readiness_exit_status(monkeypatch, status, expected):
    from firmavex.backends import compatibility

    monkeypatch.setattr(compatibility, "check", lambda profile: {"status": status})
    assert main(["doctor", "verilog-icarus"]) == expected
