"""Ubuntu/Debian desktop package with vendor-managed QEMU/GDB/Icarus."""
import argparse
from pathlib import Path
import shutil
import subprocess
import tempfile
import re
from firmavex import __version__


def build(application, output):
    application, output = Path(application), Path(output)
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:\.dev\d+)?', __version__):
        raise ValueError('Unsupported product version')
    deb_version = __version__.replace('.dev', '~dev')
    if not (application / 'FIRMAVEX-Desktop').is_file():
        raise ValueError('Build the actual desktop application first.')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='firmavex-deb-') as temporary:
        root = Path(temporary)
        shutil.copytree(application, root / 'opt/firmavex', symlinks=True)
        (root / 'DEBIAN').mkdir()
        (root / 'DEBIAN/control').write_text(f'Package: firmavex-desktop\nVersion: {deb_version}\nArchitecture: amd64\nMaintainer: mtalhak003 <mtalhak003@gmail.com>\nDepends: libegl1, libgl1, libopengl0, libxkbcommon-x11-0, libxcb-cursor0, qemu-system-arm, qemu-system-misc, gdb-multiarch, iverilog\nSection: devel\nPriority: optional\nDescription: Configured embedded firmware and HDL testing\n Trusted compatible Cortex-M3 and RV32 ELF, and self-contained Verilog testbenches.\n No arbitrary board, BIN, hardware testing or verified hostile-workload sandbox.\n')
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
        subprocess.run(['dpkg-deb', '-Zxz', '--root-owner-group', '--build', str(root), str(output.resolve())], check=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('application')
    parser.add_argument('output')
    args = parser.parse_args()
    build(args.application, args.output)
