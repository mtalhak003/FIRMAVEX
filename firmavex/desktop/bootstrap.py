"""Frozen executable routing. Worker mode must run before importing Qt."""
import sys


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if args == ["--backend-child"]:
        from firmavex.backends.launcher import main as child
        return child()
    if args and args[0] == "--firmavex-backends":
        from firmavex.backends.cli import main as backends
        return backends(args[1:])
    if args == ["--firmavex-worker"]:
        from firmavex.product.worker import main as worker
        return worker()
    if args and args[0] == "--firmavex-cli":
        from firmavex.product.cli import main as cli
        return cli(args[1:])
    if args and args[0] == "--firmavex-runtime":
        from firmavex.product.runtime_pack import main as runtime
        return runtime(args[1:])
    from firmavex.desktop.app import main as desktop
    return desktop(args)


if __name__ == "__main__":
    raise SystemExit(main())
