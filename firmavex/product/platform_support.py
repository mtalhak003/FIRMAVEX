"""Narrow native runtime admission, independently identified by discovery.

Windows adapter qualification: Actions run 38278936642, six actual ARM tests.
This profile pins selected executables, not their entire DLL dependency closure.
"""
import os
import platform
import re

from .errors import ProductError

WINDOWS_PROFILE_VERSION = 1
WINDOWS_PROFILE_ID = 'msys2-ucrt64-qemu11.1.2-gdb18.1-v1'
WINDOWS_EXECUTABLES = {
    'qemu': ('QEMU emulator version 11.1.2', '1247e03f58f2e845ff516e0cc951b67d0ee5dd5d6bcbe89faedbec692641b244'),
    'gdb': ('GNU gdb (GDB) 18.1', 'f867205234b5c61ad53bbb70db25462566b1742b409eb345f7f0178fd388f236'),
}


def _qualification_details(identities, machine):
    """Failure-only projection, never raw tool output, paths or extra metadata.

    Unknown version formats are omitted rather than truncating potentially
    private text. This diagnostic does not participate in the admission decision.
    """
    patterns = {
        'qemu': r'QEMU emulator version [0-9]{1,6}(?:\.[0-9]{1,6}){1,3}',
        'gdb': r'GNU gdb \(GDB\) [0-9]{1,6}(?:\.[0-9]{1,6}){1,3}',
    }
    architectures = {'amd64': 'x86_64', 'x86_64': 'x86_64', 'arm64': 'arm64',
                     'aarch64': 'arm64', 'x86': 'x86', 'i386': 'x86', 'i686': 'x86'}
    machine = machine.lower() if type(machine) is str and len(machine) <= 16 else ''
    identities = identities if type(identities) is dict else {}
    tools = {}
    for name, (version, digest) in WINDOWS_EXECUTABLES.items():
        identity = identities.get(name)
        identity = identity if type(identity) is dict else {}
        observed = {}
        for field, pattern in (('version', patterns[name]), ('sha256', r'[0-9a-f]{64}')):
            value = identity.get(field)
            observed[field] = (value if type(value) is str and len(value) <= 128
                               and re.fullmatch(pattern, value) else None)
        expected = {'version': version, 'sha256': digest}
        tools[name] = {'expected': expected, 'observed': observed,
                       'matches': {field: observed[field] == expected[field]
                                   if observed[field] is not None else None
                                   for field in expected}}
    return {'schema_version': 1, 'required_profile': WINDOWS_PROFILE_ID,
            'profile_version': WINDOWS_PROFILE_VERSION,
            'host_architecture': architectures.get(machine, 'unknown'), 'tools': tools}


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
                           {'required_profile': WINDOWS_PROFILE_ID, 'profile_version': WINDOWS_PROFILE_VERSION,
                            'qualification': _qualification_details(tools.identities, platform.machine())})
