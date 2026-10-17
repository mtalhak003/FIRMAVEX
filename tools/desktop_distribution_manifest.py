"""Record the built application's actual file inventory and build environment."""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import subprocess
from firmavex import __version__


def capture(directory):
    directory = Path(directory)
    if not directory.is_dir() or directory.is_symlink():
        raise ValueError('Select an actual application directory.')
    files = {}
    for path in sorted(directory.rglob('*')):
        if path.is_symlink():
            # macOS framework links are part of the bundle; record link identity.
            files[path.relative_to(directory).as_posix()] = {'symlink_target': str(path.readlink())}
        elif path.is_file() and path.name != 'distribution-manifest.json':
            files[path.relative_to(directory).as_posix()] = {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'size_bytes': path.stat().st_size}
    return {'schema_version': 1, 'kind': 'firmavex_application_distribution',
            'application_version': __version__,
            'git_revision': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
            'dirty': bool(subprocess.check_output(['git', 'status', '--porcelain'], text=True)),
            'host': {'os': platform.system(), 'architecture': platform.machine(), 'python': platform.python_version()},
            'dependencies': {name: importlib.metadata.version(name) for name in ['PyInstaller', 'PySide6', 'shiboken6', 'pyelftools']},
            'signing': 'not_developer_signed_or_notarized',
            'firmware_qualification': 'not_established_by_packaging', 'files': files}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    (args.directory / 'distribution-manifest.json').write_text(json.dumps(capture(args.directory), sort_keys=True, indent=2) + '\n', encoding='utf-8')
