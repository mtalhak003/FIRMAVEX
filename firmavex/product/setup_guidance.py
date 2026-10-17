"""Offline first-run guidance; descriptive, never runtime qualification."""


def instructions(host):
    system, arch = host.get('os'), host.get('arch')
    common = ('No Python or compiler is needed for the built-in example. '
              'Check runtime after installation or repair. A capability check does not execute a target. '
              'Keep projects and results in your own folder outside the application/runtime directories. '
              'After dependencies are installed, local testing needs no account or internet connection.')
    if system == 'windows' and arch == 'x86_64':
        platform = ('Windows x64: choose Install / repair runtime and authorize the direct MSYS2 publisher download. '
                    'If inventory verification fails, inspect generations and roll back to a verified generation, '
                    'or repair using the publisher. Never disable signature checks. Downloads require internet.')
    elif system == 'linux' and arch == 'x86_64':
        platform = ('Ubuntu x64: use the Debian installer so the system package manager installs QEMU, '
                    'GDB Multiarch and Icarus. If dependencies are missing, reopen the package in the system '
                    'software installer and repair dependencies. The portable archive does not install runtimes. '
                    'Automatic vendor download in this wizard is Windows-only; trusted offline packs are optional.')
    elif system == 'macos':
        platform = ('macOS Apple Silicon: desktop preview only. Unified native execution is unsupported '
                    'because memory-resource admission fails. Installing tools cannot remove this restriction. '
                    'Do not bypass resource controls. The application is unsigned/unnotarized.')
    else:
        platform = ('This OS/CPU combination has no native qualification. Do not infer support from '
                    'a successful tool version check. Review the supported-platform matrix.')
    return platform + '\n\n' + common
