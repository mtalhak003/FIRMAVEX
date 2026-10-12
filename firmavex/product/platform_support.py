"""Narrow native runtime admission, independently identified by discovery.

Windows adapter qualification: Actions run 38278936642, six actual ARM tests.
This profile pins selected executables, not their entire DLL dependency closure.
"""
import os
import platform

from .errors import ProductError

WINDOWS_PROFILE_VERSION = 1
WINDOWS_PROFILE_ID = 'msys2-ucrt64-qemu11.1.2-gdb18.1-v1'
WINDOWS_EXECUTABLES = {
    'qemu': ('QEMU emulator version 11.1.2', '1247e03f58f2e845ff516e0cc951b67d0ee5dd5d6bcbe89faedbec692641b244'),
    'gdb': ('GNU gdb (GDB) 18.1', 'f867205234b5c61ad53bbb70db25462566b1742b409eb345f7f0178fd388f236'),
}


def windows_profile(tools, *, machine=None):
    if (platform.machine() if machine is None else machine).lower() not in {'amd64', 'x86_64'}:
        return None
    for name, (version, digest) in WINDOWS_EXECUTABLES.items():
        identity = tools.identities.get(name, {})
        if identity.get('version') != version or identity.get('sha256') != digest:
            return None
    return WINDOWS_PROFILE_ID


def require_native_support(tools):
    if os.name == 'nt' and windows_profile(tools) is None:
        raise ProductError('unsupported_platform',
                           'Windows execution requires the checksum-qualified MSYS2 UCRT64 QEMU 11.1.2 / GDB 18.1 runtime. Other Windows runtimes remain gated.',
                           {'required_profile': WINDOWS_PROFILE_ID, 'profile_version': WINDOWS_PROFILE_VERSION})
