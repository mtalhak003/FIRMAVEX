"""User-requested vendor installation, not redistribution of vendor binaries.

Windows obtains the pinned MSYS2 bootstrap directly from the publisher, then
uses the vendor's signed package repository. No signature verification is disabled.
A local relocatable UCRT64 snapshot retains the vendor's license notices.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
import time
import urllib.parse
import urllib.request
import uuid
import zipfile

from .errors import ProductError
from .runtime_pack import host, runtime_root, install, safe_name, MAX_BYTES, MAX_FILES
from .tools import file_identity

BOOTSTRAP = {
    'schema_version': 1, 'publisher': 'MSYS2', 'release': '2026-09-27',
    'url': 'https://github.com/msys2/msys2-installer/releases/download/2026-09-27/msys2-base-x86_64-20260927.sfx.exe',
    'sha256': 'ad336cccfda47758b5e15cda993fbba421115cb0b126697daef1ee4dfe37209f',
    'source': 'https://github.com/msys2/msys2-installer',
    'license_information': 'https://www.msys2.org/docs/licenses/',
}
PACKAGES = ('mingw-w64-ucrt-x86_64-qemu', 'mingw-w64-ucrt-x86_64-gdb-multiarch',
            'mingw-w64-ucrt-x86_64-iverilog')


def _cancelled(cancel):
    if cancel is not None and cancel.is_set():
        raise KeyboardInterrupt('Runtime setup cancelled; the previous runtime remains selected.')


def _progress(callback, stage, message):
    if callback is not None:
        callback({'type': 'runtime_setup', 'stage': stage, 'message': message, 'firmware_executed': False})


def _download(destination, cancel, callback):
    digest = hashlib.sha256()
    count = 0
    request = urllib.request.Request(BOOTSTRAP['url'], headers={'User-Agent': 'FIRMAVEX-runtime-setup/1'})
    with urllib.request.urlopen(request, timeout=30) as response, destination.open('xb') as stream:
        url = urllib.parse.urlparse(response.geturl())
        if url.scheme != 'https' or url.hostname not in {'github.com', 'release-assets.githubusercontent.com', 'objects.githubusercontent.com'}:
            raise ProductError('runtime_download_failed', 'The vendor redirected to an unexpected download origin.')
        while chunk := response.read(1024 * 1024):
            _cancelled(cancel)
            count += len(chunk)
            if count > 512 * 1024**2:
                raise ProductError('runtime_download_failed', 'Vendor bootstrap exceeds the download limit.')
            stream.write(chunk)
            digest.update(chunk)
            _progress(callback, 'download', f'Downloaded {count // 1024**2} MiB from MSYS2.')
    if digest.hexdigest() != BOOTSTRAP['sha256'] or file_identity(destination)['sha256'] != BOOTSTRAP['sha256']:
        raise ProductError('runtime_integrity_failure', 'The vendor bootstrap checksum does not match. Nothing was executed.')


def _run(command, *, cancel, callback, stage, env=None, timeout=900):
    from .runtime import _spawn, _cleanup
    _cancelled(cancel)
    # _spawn already isolates stdin and keeps children in the owned worker job.
    process, stdout, stderr = _spawn(command, env=env)
    original = None
    try:
        deadline = time.monotonic() + timeout
        while process.poll() is None:
            _cancelled(cancel)
            if time.monotonic() >= deadline:
                raise ProductError('runtime_setup_timeout', f'{stage} exceeded its bounded installation time.')
            time.sleep(0.05)
        stdout.thread.join(timeout=2)
        stderr.thread.join(timeout=2)
        if process.returncode:
            raise ProductError('runtime_vendor_install_failed', f'{stage} failed; the existing runtime was not replaced.',
                               {'return_code': process.returncode, 'stdout': stdout.text(), 'stderr': stderr.text()})
        return stdout.text()
    except BaseException as exc:
        original = exc
        raise
    finally:
        cleanup = _cleanup([(stage, process, stdout, stderr)], original)
        if not cleanup['success'] and original is None:
            raise ProductError('cleanup_failure', 'Runtime installation process cleanup failed.', cleanup)


def snapshot_runtime(directory, archive, *, packages, cancel=None):
    """Local snapshot only: licenses and vendor package inventory are retained."""
    directory = Path(directory)
    files = {}
    license_paths = []
    size = 0
    members = []
    omitted_other_machines = []
    omitted_development_files = []
    for path in sorted(directory.rglob('*')):
        _cancelled(cancel)
        if path.is_symlink():
            raise ProductError('runtime_snapshot_failed', 'The native runtime contains a symbolic link; snapshot needs a publisher-specific relocation audit.')
        if not path.is_file():
            continue
        name = safe_name(path.relative_to(directory).as_posix())
        # MSYS2's QEMU package contains many independent machine executables.
        # Retain the ARM and RV32 desktop engines, all shared libraries,
        # modules, Icarus subtools, data and notices. Other guest engines are
        # omitted. The schema-1 ARM tool map remains unchanged; additional
        # backend tools are discoverable only through the verified inventory.
        if name.startswith('bin/qemu-system-') and name.endswith('.exe') and name not in {'bin/qemu-system-arm.exe', 'bin/qemu-system-riscv32.exe'}:
            omitted_other_machines.append(name)
            continue
        if name.startswith(('include/', 'lib/pkgconfig/', 'lib/cmake/', 'share/doc/', 'share/man/', 'share/info/', 'share/aclocal/', 'share/icons/', 'share/themes/', 'share/gtk-doc/', 'share/help/')) or (name.startswith('lib/') and name.endswith(('.a', '.la'))) or (name.startswith('lib/python') and '/test/' in name):
            omitted_development_files.append(name)
            continue
        members.append((name, path))
        size += path.stat().st_size
        if size > MAX_BYTES or len(members) > MAX_FILES - 1:
            raise ProductError('runtime_snapshot_failed', 'The runtime dependency snapshot exceeds supported limits.', {'size_bytes': size, 'files': len(members), 'maximum_bytes': MAX_BYTES, 'maximum_files': MAX_FILES - 1, 'last_member': name})
        files[name] = file_identity(path)['sha256']
        if name.startswith('share/licenses/'):
            license_paths.append(name)
    if not license_paths:
        raise ProductError('runtime_license_missing', 'Vendor license notices are absent; activation is refused.')
    inventory_name = 'FIRMAVEX-VENDOR-PACKAGES.json'
    inventory = json.dumps({'schema_version': 1, 'vendor': BOOTSTRAP, 'installed_packages': packages,
                            'distribution_model': 'direct_vendor_download_then_local_snapshot',
                            'omitted_other_machine_executables': omitted_other_machines,
                            'omitted_development_files': omitted_development_files,
                            'source_recipes': 'https://github.com/msys2/MINGW-packages'}, sort_keys=True, indent=2).encode()
    files[inventory_name] = hashlib.sha256(inventory).hexdigest()
    data = {'schema_version': 1, 'id': 'msys2-ucrt64-qemu11.1.2-gdb18.1-local-v1', 'host': host(),
            'tools': {'qemu': 'bin/qemu-system-arm.exe', 'gdb': 'bin/gdb-multiarch.exe'}, 'files': files,
            'licenses': license_paths,
            'source_offer': 'Components were obtained directly from MSYS2 signed repositories. Original notices retained. Vendor source/recipes: https://github.com/msys2/MINGW-packages . This local snapshot is not a FIRMAVEX redistribution or a complete corresponding-source archive.'}
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=1) as target:
        target.writestr('runtime.json', json.dumps(data, sort_keys=True))
        target.writestr(inventory_name, inventory)
        for name, path in members:
            _cancelled(cancel)
            target.write(path, name)
            if file_identity(path)['sha256'] != files[name]:
                raise ProductError('runtime_snapshot_failed', 'Vendor files changed during snapshot.')
    return file_identity(archive)['sha256']



def _remove_private_tree(work):
    """Only clear read-only attributes inside this newly owned temporary tree."""
    work = Path(work)
    def read_only(operation, filename, info):
        error = info[1]
        selected = Path(filename)
        if not isinstance(error, PermissionError) or selected.is_symlink() or (hasattr(selected, 'is_junction') and selected.is_junction()):
            raise error
        try:
            selected.resolve().relative_to(work.resolve())
        except ValueError:
            raise error
        selected.chmod(selected.stat().st_mode | stat.S_IWRITE)
        operation(filename)
    shutil.rmtree(work, onerror=read_only)

def install_vendor_runtime(*, cancel_event=None, event_callback=None, root=None):
    if host() != {'os': 'windows', 'arch': 'x86_64'}:
        raise ProductError('runtime_provider_unavailable', 'Automatic vendor setup currently supports native x86-64 Windows only. Use verified existing tools or a trusted offline runtime pack on this platform.')
    root = Path(root) if root is not None else runtime_root()
    root.mkdir(parents=True, exist_ok=True)
    if root.is_symlink():
        raise ProductError('runtime_setup_failed', 'Runtime storage cannot be a symbolic link.')
    # No package-manager updates touch a pre-existing/global MSYS2 installation.
    work = Path(tempfile.mkdtemp(prefix='vendor-setup-', dir=root))
    result = None
    environment = None
    msys = work / 'msys64'
    try:
        _progress(event_callback, 'download', 'Downloading the checksum-pinned MSYS2 bootstrap directly from its publisher.')
        bootstrap = work / 'msys2-bootstrap.exe'
        _download(bootstrap, cancel_event, event_callback)
        _cancelled(cancel_event)
        _progress(event_callback, 'extract', 'Preparing a private MSYS2 installation.')
        _run([str(bootstrap), '-y', '-o' + str(work)], cancel=cancel_event, callback=event_callback, stage='bootstrap extraction')
        msys = work / 'msys64'
        bash = msys / 'usr/bin/bash.exe'
        (msys / 'home/firmavex-setup').mkdir(parents=True, exist_ok=True)
        environment = {**os.environ, 'HOME': str(msys / 'home/firmavex-setup').replace('\\', '/'), 'USERPROFILE': str(msys / 'home/firmavex-setup'), 'MSYSTEM': 'UCRT64', 'CHERE_INVOKING': '1', 'MSYS2_PATH_TYPE': 'strict'}
        _progress(event_callback, 'packages', 'Updating the private vendor package manager; signatures remain required.')
        # Core MSYS2 updates can terminate the updating shell; the second invocation
        # completes the supported two-stage upgrade before runtime installation.
        _run([str(bash), '--login', '-c', 'pacman -Syu --noconfirm'], cancel=cancel_event, callback=event_callback, env=environment, stage='vendor core update')
        _run([str(bash), '--login', '-c', 'pacman -Syu --noconfirm'], cancel=cancel_event, callback=event_callback, env=environment, stage='vendor update completion')
        _run([str(bash), '--login', '-c', 'pacman -S --needed --noconfirm ' + ' '.join(PACKAGES)], cancel=cancel_event, callback=event_callback, env=environment, stage='signed runtime package installation')
        packages = _run([str(bash), '--login', '-c', 'pacman -Q'], cancel=cancel_event, callback=event_callback, env=environment, stage='vendor inventory')
        _progress(event_callback, 'snapshot', 'Retaining runtime dependencies, license notices and package identities.')
        archive = work / 'runtime-local.zip'
        digest = snapshot_runtime(msys / 'ucrt64', archive, packages=packages, cancel=cancel_event)
        _cancelled(cancel_event)
        _progress(event_callback, 'verify', 'Verifying the relocatable runtime and native compatibility before activation.')
        result = install(archive, digest, root=root, cancel_event=cancel_event)
        result.update({'vendor': BOOTSTRAP, 'distribution_model': 'direct_vendor_installation', 'compiler_required': False, 'firmware_executed': False})
        _progress(event_callback, 'complete', 'Verified runtime activated. User projects and previous generations were preserved.')
        return result
    finally:
        original = __import__('sys').exception()
        try:
            if (msys / 'usr/bin/gpgconf.exe').is_file() and environment is not None:
                # Pacman's agent belongs to this private keyring, never the user's.
                _run([str(msys / 'usr/bin/bash.exe'), '--login', '-c', 'gpgconf --homedir /etc/pacman.d/gnupg --kill all'],
                     cancel=None, callback=event_callback, env=environment, stage='private vendor agent cleanup', timeout=30)
            _remove_private_tree(work)
        except BaseException as cleanup:
            if original is None:
                raise ProductError('runtime_cleanup_failed', 'Temporary vendor installation could not be removed.', {'path': str(work), 'error': str(cleanup), 'activated_generation': result.get('generation') if result else None}) from cleanup
            original.add_note('Vendor temporary cleanup failed: ' + repr(cleanup))
