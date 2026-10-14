"""Separate additive headless frontend; legacy firmavex CLI remains intact."""

import argparse
import json
from pathlib import Path
import threading
from .api import Limits, Request, profiles
from .engine import execute_trusted, inspect_run


def main(argv=None):
    parser = argparse.ArgumentParser(prog="firmavex-backend")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("profiles")
    doctor = sub.add_parser("doctor")
    doctor.add_argument("profile", choices=profiles)
    build = sub.add_parser("prepare-example")
    build.add_argument("profile", choices=("riscv32-virt", "verilog-icarus"))
    build.add_argument("--output", required=True)
    build.add_argument("--builtin", action="store_true", help="Use the verified compiler-free catalog")
    for name in ("export", "reproduce"):
        item = sub.add_parser(name)
        item.add_argument("run")
        item.add_argument("--output", required=True)
        if name == "reproduce": item.add_argument("--trust", choices=("trusted_example","trusted_project","untrusted"), default="untrusted")
    inspect = sub.add_parser("inspect")
    inspect.add_argument("output")
    run = sub.add_parser("execute")
    run.add_argument("profile", choices=profiles)
    run.add_argument("source", type=Path)
    run.add_argument("--values", type=int, nargs="*", default=[])
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--timeout", type=float, default=10)
    run.add_argument("--trust", choices=("trusted_example","trusted_project","untrusted"), default="untrusted")
    args = parser.parse_args(argv)
    try:
        if args.command == "profiles":
            result = {name: profile.to_dict() for name, profile in profiles.items()}
        elif args.command == "doctor":
            from .compatibility import check

            result = check(args.profile)
        elif args.command == "prepare-example":
            from .examples import prepare

            import sys
            if args.builtin or getattr(sys,"frozen",False):
                from firmavex.product.backend_services import prepare as prepare_builtin
                result = prepare_builtin(args.profile,args.output)
            else:
                result = prepare(args.profile, args.output)
        elif args.command in {"export", "reproduce"}:
            from .report import export, reproduce

            if args.command == "reproduce":
                from firmavex.product.backend_services import reproduce as trusted_reproduce
                result = trusted_reproduce(args.run,args.output,trust=args.trust)
            else:
                result = export(args.run,args.output)
        elif args.command == "inspect":
            result = inspect_run(args.output)
        else:
            result = execute_trusted(
                Request(
                    args.profile, args.source, tuple(args.values), Limits(args.timeout)
                ),
                args.output, trust=args.trust,
            )
        print(json.dumps(result, sort_keys=True, indent=2))
        if result.get("status") == "cancelled":
            return 130
        return (
            1
            if result.get("status")
            in {
                "infrastructure_failure",
                "invalid_input",
                "invalid_output",
                "interrupted",
                "incomplete",
                "unsupported_platform",
            }
            else 0
        )
    except RuntimeError as exc:
        print(json.dumps({"status": "infrastructure_failure", "error": str(exc)}))
        return 1
    except (ValueError, OSError) as exc:
        print(json.dumps({"status": "invalid_input", "error": str(exc)}))
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
