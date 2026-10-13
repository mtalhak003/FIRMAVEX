"""Desktop entry point; Qt is optional until this entry point is selected."""

from __future__ import annotations

import sys
import argparse
import os
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="firmavex-desktop", description="FIRMAVEX Desktop — configured firmware testing on QEMU mps2-an385")
    parser.add_argument("--project", type=Path, help="Open an existing desktop project; do not execute firmware.")
    parser.add_argument("--smoke-test", action="store_true", help="Open and close the UI without firmware execution.")
    args = parser.parse_args(argv)
    if sys.platform.startswith("linux") and not any(os.environ.get(key) for key in ("DISPLAY", "WAYLAND_DISPLAY", "QT_QPA_PLATFORM")):
        print("No graphical display is available. Use a Linux desktop/WSLg session, or QT_QPA_PLATFORM=offscreen for automated GUI checks.", file=sys.stderr)
        return 2
    try:
        from PySide6.QtCore import QCoreApplication, QTimer
        from PySide6.QtWidgets import QApplication
        from .window import MainWindow
    except ModuleNotFoundError as exc:
        if exc.name and exc.name.startswith("PySide6"):
            print("FIRMAVEX Desktop needs PySide6. Install with: python -m pip install 'firmavex-desktop[desktop]'", file=sys.stderr)
            return 2
        raise
    QCoreApplication.setOrganizationName("FIRMAVEX")
    QCoreApplication.setApplicationName("FIRMAVEX Desktop")
    application = QApplication.instance() or QApplication([sys.argv[0]])
    window = MainWindow()
    window.show()
    if args.project is not None:
        window.open_project(args.project)
    if args.smoke_test:
        # No tools, example build, or firmware dispatch is admitted by smoke.
        QTimer.singleShot(100, window.close)
    elif args.project is None and not (window.data_root / "first-launch.json").exists():
        QTimer.singleShot(0, window.show_setup)
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
