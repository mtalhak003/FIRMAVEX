"""Console frontend for the product foundation; execution uses a worker."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .errors import ProductError


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="firmavex", description="Firmware testing foundation for symbolized Cortex-M3 ELF on QEMU mps2-an385.")
    commands = root.add_subparsers(dest="command", required=True)
    desktop = commands.add_parser("desktop", help="Launch the optional PySide6 desktop application.")
    desktop.add_argument("--project")
    desktop.add_argument("--smoke-test", action="store_true", help=argparse.SUPPRESS)
    commands.add_parser("doctor", help="Check real runtime tools and capabilities.")
    validate = commands.add_parser("validate", help="Validate a firmware project before execution.")
    validate.add_argument("config")
    build = commands.add_parser("build-example", help="Build the independent product example without running it.")
    build.add_argument("--output-dir", required=True)
    run = commands.add_parser("run", help="Run the configured search in a supervised worker.")
    run.add_argument("config")
    run.add_argument("--output-dir", required=True)
    inspect = commands.add_parser("inspect", help="Inspect existing results without firmware execution.")
    inspect.add_argument("run_dir")
    recover = commands.add_parser("recover", help="Explicitly mark an abandoned job interrupted; do not dispatch firmware.")
    recover.add_argument("run_dir")
    restart = commands.add_parser("restart", help="Start a new full search linked to an interrupted run; completed jobs are not rerun automatically.")
    restart.add_argument("run_dir")
    restart.add_argument("--output-dir", required=True)
    reproduce = commands.add_parser("reproduce", help="Replay a saved trigger in a fresh result directory.")
    reproduce.add_argument("run_dir")
    reproduce.add_argument("--output-dir", required=True)
    reproduce.add_argument("--attempts", type=int, default=3)
    export = commands.add_parser("export", help="Export existing records and an understandable report.")
    export.add_argument("run_dir")
    export.add_argument("--output-dir", required=True)
    demo = commands.add_parser("demo", help="Build and run the bounded independent product demonstration.")
    demo.add_argument("--output-dir", required=True)
    builtin = commands.add_parser("demo-builtin", help="Run the verified built-in image without a compiler.")
    builtin.add_argument("--output-dir", required=True)
    prepared = commands.add_parser("prepare-example", help="Copy the verified built-in image without execution or compilation.")
    prepared.add_argument("--output-dir", required=True)
    commands.add_parser("setup-runtime", help="Guided signed-vendor runtime setup (Windows x86-64).")
    commands.add_parser("runtime-history", help="Verify recorded runtime generations.")
    rolled = commands.add_parser("rollback-runtime", help="Activate a verified historical runtime.")
    rolled.add_argument("generation")
    commands.add_parser("worker", help=argparse.SUPPRESS)
    return root


def _progress(event: dict[str, Any]) -> None:
    if event["kind"] == "progress":
        print(json.dumps(event, sort_keys=True, allow_nan=False), file=sys.stderr, flush=True)


def _exit_status(result: dict[str, Any]) -> int:
    # Observation outcomes may be successful without discovering a failure.
    status = result.get("status", result.get("outcome", result.get("classification")))
    if status in {"cancelled", "interrupted"}:
        return 130
    if status in {"infrastructure_failure", "infrastructure_aborted", "evidence_incomplete", "invalid_output", "aborted"}:
        return 1
    if result.get("aborted") is True or result.get("success") is False:
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "desktop":
            try:
                from firmavex.desktop.app import main as desktop_main
            except ModuleNotFoundError as exc:
                if exc.name and exc.name.startswith("PySide6"):
                    raise ProductError("missing_dependency", "Install the desktop extra with python -m pip install 'firmavex-desktop[desktop]'.") from exc
                raise
            desktop_args = []
            if args.project:
                desktop_args.extend(["--project", args.project])
            if args.smoke_test:
                desktop_args.append("--smoke-test")
            return desktop_main(desktop_args)
        if args.command == "worker":
            from .worker import main as worker_main
            return worker_main()
        if args.command == "build-example":
            from .example import build_example
            result = build_example(args.output_dir)
        else:
            from .supervisor import Supervisor
            payload: dict[str, Any] = {}
            if args.command in {"validate", "run"}:
                payload["config"] = args.config
            if args.command in {"inspect", "reproduce", "export", "recover", "restart"}:
                payload["run_dir"] = args.run_dir
            if hasattr(args, "output_dir"):
                payload["output_dir"] = args.output_dir
            if args.command == "reproduce":
                if not 1 <= args.attempts <= 100:
                    raise ProductError("configuration_error", "Reproduction attempts must be from 1 to 100.")
                payload["attempts"] = args.attempts
            if args.command == "rollback-runtime":
                payload["generation"] = args.generation
            operation = {"demo-builtin": "demo_builtin", "prepare-example": "prepare_example", "setup-runtime": "setup_runtime", "runtime-history": "runtime_history", "rollback-runtime": "rollback_runtime"}.get(args.command, args.command)
            result = Supervisor().execute(operation, payload, event_callback=_progress)
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return _exit_status(result)
    except ProductError as exc:
        print(json.dumps({"success": False, "error": exc.to_dict()}, sort_keys=True, allow_nan=False))
        return 130 if exc.category == "cancelled" else 1
    except KeyboardInterrupt:
        print(json.dumps({"success": False, "error": {"category": "cancelled", "message": "Cancelled. Inspect persisted results before restarting.", "details": {}}}))
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
