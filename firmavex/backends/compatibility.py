"""Actual, offline capability probes; availability is not native qualification."""

from .tools import readiness


def check(profile):
    return readiness(profile)
