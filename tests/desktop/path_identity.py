"""Existing-path identity assertions, never application admission policy."""
from pathlib import Path


def assert_same_path(actual, expected):
    # stat-based identity handles Windows 8.3 and macOS /var aliases. Missing,
    # malformed and unreadable paths raise; there is no spelling-only fallback.
    assert Path(actual).samefile(expected), (actual, expected)
