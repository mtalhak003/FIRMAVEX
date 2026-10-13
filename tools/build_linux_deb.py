"""Ubuntu/Debian application package, depending on vendor-managed QEMU/GDB."""
import argparse
from pathlib import Path
import shutil
import subprocess
import tempfile


def build(application, output):
    application, output = Path(application), Path(output)
    if not (application / 'FIRMAVEX-Desktop').is_file():
        raise ValueError('Build the actual desktop application first.')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='firmavex-deb-') as temporary:
        root = Path(temporary)
        shutil.copytree(application, root / 'opt/firmavex', symlinks=True)
        (root / 'DEBIAN').mkdir()
        (root / 'DEBIAN/control').write_text('Package: firmavex-desktop\nVersion: 0.3.0~dev1\nArchitecture: amd64\nMaintainer: mtalhak003 <mtalhak003@gmail.com>\nDepends: libegl1, libgl1, libopengl0, libxkbcommon-x11-0, libxcb-cursor0, qemu-system-arm, gdb-multiarch\nSection: devel\nPriority: optional\nDescription: Configured Cortex-M3 firmware testing in QEMU\n Symbolized compatible ELF only. No arbitrary board or hardware support.\n')
        menu = root / 'usr/share/applications'; menu.mkdir(parents=True)
        shutil.copyfile('packaging/FIRMAVEX.desktop', menu / 'FIRMAVEX.desktop')
        notices = root / 'usr/share/doc/firmavex-desktop'; notices.mkdir(parents=True)
        shutil.copyfile('LICENSE', notices / 'copyright')
        # Packaging must not inherit a developer's restrictive umask.
        root.chmod(0o755)
        for path in root.rglob('*'):
            if path.is_dir() and not path.is_symlink():
                path.chmod(0o755)
            elif path.is_file() and not path.is_symlink():
                path.chmod(0o755 if path.stat().st_mode & 0o111 else 0o644)
        subprocess.run(['dpkg-deb', '--root-owner-group', '--build', str(root), str(output.resolve())], check=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('application')
    parser.add_argument('output')
    args = parser.parse_args()
    build(args.application, args.output)
