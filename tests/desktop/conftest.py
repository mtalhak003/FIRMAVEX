"""Desktop checks require the explicit GUI test extra, never fake Qt widgets."""
import importlib.util
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
os.environ.setdefault('PYTEST_QT_API','pyside6')

# A CLI-only installation can still run the unchanged research/product suites.
# Explicit GUI validation installs .[gui-test]; missing Qt is never called a
# passing GUI test or substituted with a dummy implementation.
collect_ignore_glob = ['test_*.py'] if importlib.util.find_spec('PySide6') is None or importlib.util.find_spec('pytestqt') is None else []
