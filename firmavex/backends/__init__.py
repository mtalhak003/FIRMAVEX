"""Offline, headless backend contract; independent of frozen research protocols."""

from .api import Backend, Capabilities, Limits, Request, Result, TargetProfile, profiles
from .engine import execute, inspect_run

__all__ = [
    "Backend",
    "Capabilities",
    "Limits",
    "Request",
    "Result",
    "TargetProfile",
    "profiles",
    "execute",
    "inspect_run",
]
