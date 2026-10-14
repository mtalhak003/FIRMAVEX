"""Real bounded local-interface examples; no executor injection or research campaign."""

import argparse
import json
from pathlib import Path
import sys
import subprocess
import time

from firmavex.backends.api import Request, request_to_dict
from firmavex.product.local import LocalSession
from firmavex.product.supervisor import Supervisor
from tools.universal_desktop_ci import verify_completed, _verify_cleanup


def call(session, command, payload):
    identifier = session.submit(command, payload, timeout_seconds=300)
    deadline = time.monotonic() + 340
    while session.status(identifier)["state"] in {"running", "cancellation_requested"}:
        if time.monotonic() > deadline:
            session.cancel(identifier)
            raise TimeoutError("Local interface qualification deadline exceeded")
        time.sleep(0.02)
    result = session.result(identifier)
    session.forget(identifier)
    if result["error"] is not None:
        raise RuntimeError(json.dumps(result["error"]))
    return result["result"]


def qualify(output, engine=None):
    root = Path(output).absolute()
    root.mkdir(parents=True, exist_ok=False)
    argv = [str(Path(engine).absolute()), "--firmavex-worker"] if engine else None
    # Exercise the actual source/frozen pipe gateway as well as the Python API.
    from firmavex.product.protocol import encode_json_object, decode_json_object

    gateway = (
        [str(Path(engine).absolute()), "--firmavex-local"]
        if engine
        else [sys.executable, "-m", "firmavex.product.local_stdio"]
    )
    negotiated_pipe = subprocess.run(
        gateway,
        input=encode_json_object(
            {
                "interface_version": 1,
                "request_id": "handshake",
                "operation": "negotiate",
                "payload": {},
            }
        ),
        capture_output=True,
        timeout=30,
    )
    assert negotiated_pipe.returncode == 0, negotiated_pipe.stderr
    response = decode_json_object(negotiated_pipe.stdout)
    assert response["interface_version"] == 1 and response["ok"] is True
    assert response["payload"]["network_listener"] is False
    records = []
    with LocalSession(supervisor=Supervisor(worker_argv=argv)) as session:
        negotiated = call(session, "capabilities", {})
        assert (
            negotiated["policy"]["sandboxed"] is False
            and negotiated["network_listener"] is False
        )
        for profile in ("cortex-m3-mps2", "riscv32-virt", "verilog-icarus"):
            prepared = call(
                session,
                "backend_prepare",
                {"profile": profile, "output_dir": str(root / (profile + "-example"))},
            )
            request = Request(
                profile,
                Path(prepared["source"]),
                (2, 1) if profile == "riscv32-virt" else (),
            )
            run = root / (profile + "-run")
            observed = call(
                session,
                "backend_execute",
                {
                    "request": request_to_dict(request),
                    "output_dir": str(run),
                    "trust": "trusted_example",
                },
            )
            expected = "passed" if profile == "verilog-icarus" else "triggered"
            verify_completed(observed, profile, expected)
            reopened = call(session, "backend_inspect", {"run_dir": str(run)})
            assert reopened == observed
            replay = call(
                session,
                "backend_reproduce",
                {
                    "run_dir": str(run),
                    "output_dir": str(root / (profile + "-replay")),
                    "trust": "trusted_example",
                },
            )
            assert replay["status"] == observed["status"]
            call(
                session,
                "backend_export",
                {"run_dir": str(run), "output_dir": str(root / (profile + "-export"))},
            )
            records.append(
                {
                    "profile": profile,
                    "status": observed["status"],
                    "measurement_mode": observed["evidence"]["measurement_mode"],
                    "reopened": True,
                    "reproduced": True,
                    "exported": True,
                    "cleanup_verified": observed["evidence"]["cleanup_verified"],
                }
            )
        loop = root / "cancel-testbench.v"
        loop.write_text(
            'module testbench; initial begin $display("local simulation started"); forever #1; end endmodule'
        )
        job = session.submit(
            "backend_execute",
            {
                "request": request_to_dict(Request("verilog-icarus", loop)),
                "output_dir": str(root / "cancel-run"),
                "trust": "trusted_project",
            },
            timeout_seconds=30,
        )
        deadline = time.monotonic() + 35
        while not any(
            event["stage"] == "simulation_output"
            for event in session.status(job)["events"]
        ):
            assert session.status(job)["state"] == "running", session.result(job)
            assert (
                time.monotonic() < deadline
            ), "Actual simulation output was not observed"
            time.sleep(0.02)
        session.cancel(job)
        while session.status(job)["state"] in {"running", "cancellation_requested"}:
            assert time.monotonic() < deadline
            time.sleep(0.02)
        cancelled = session.result(job)
        assert cancelled["result"]["status"] == "cancelled", cancelled
        _verify_cleanup(cancelled["result"])
        records.append(
            {
                "profile": "verilog-icarus",
                "case": "local-interface-cancellation",
                "status": "cancelled",
                "cleanup_verified": True,
                "cancelled_after": "actual simulation output",
            }
        )
    result = {
        "schema_version": 1,
        "kind": "firmavex_local_interface_native_examples",
        "frozen_worker": bool(engine),
        "observations": records,
    }
    (root / "qualification.json").write_text(
        json.dumps(result, sort_keys=True, indent=2) + "\n"
    )
    print(
        "::notice title=Local interface native examples::"
        + json.dumps(result, sort_keys=True)
    )
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--engine", type=Path)
    args = parser.parse_args(argv)
    try:
        qualify(args.output, args.engine)
    except Exception as exc:
        error = json.dumps(
            {
                "type": type(exc).__name__,
                "message": str(exc),
                "details": getattr(exc, "details", {}),
            },
            sort_keys=True,
            default=str,
        )[-10000:]
        print(
            "::error title=Local interface qualification::"
            + error.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
