"""Explicit maintainer build of the MIT example; never a firmware execution."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import subprocess

from firmavex.product.tools import _resolve, _probe, file_identity


def build(output, work):
    source = Path('firmavex/product/resources/example').resolve()
    work = Path(work).resolve()
    work.mkdir(parents=True, exist_ok=True)
    compiler = _resolve('arm-none-eabi-gcc', None)
    flags = ['-mcpu=cortex-m3', '-mthumb', '-g', '-O0', '-ffreestanding', '-nostdlib', '-Wl,--build-id=none', f'-ffile-prefix-map={source}=/FIRMAVEX-example', f'-fdebug-prefix-map={source}=/FIRMAVEX-example', f'-ffile-prefix-map={Path(compiler).parent.parent}=/FIRMAVEX-toolchain', f'-fdebug-prefix-map={Path(compiler).parent.parent}=/FIRMAVEX-toolchain']
    subprocess.run([compiler, *flags, '-T', str(source/'linker.ld'), str(source/'startup.c'), str(source/'main.c'), '-o', str(work/'example.elf')], cwd=source, stdin=subprocess.DEVNULL, check=True)
    image = (work/'example.elf').read_bytes()
    data = {'schema_version': 1, 'kind': 'firmavex_product_example_image', 'license': 'MIT', 'image_sha256': hashlib.sha256(image).hexdigest(), 'image_base64': base64.b64encode(image).decode(), 'sources': {n: hashlib.sha256((source/n).read_bytes()).hexdigest() for n in ['main.c','startup.c','linker.ld']}, 'compiler': {'version': _probe([compiler,'--version']).stdout.splitlines()[0], 'sha256': file_identity(compiler)['sha256']}, 'flags': [s.replace(str(source), 'SOURCE').replace(str(Path(compiler).parent.parent), 'TOOLCHAIN') for s in flags]}
    Path(output).write_text(json.dumps(data, sort_keys=True, indent=2)+'\n', encoding='utf-8')
    print(data['image_sha256'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--work', required=True)
    args = parser.parse_args()
    build(args.output, args.work)
