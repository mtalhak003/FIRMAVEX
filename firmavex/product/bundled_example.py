"""Verified product-owned image; copying it never compiles or runs firmware."""
from importlib.resources import files
import base64
import hashlib
import json
from pathlib import Path

from .errors import ProductError


def prepare_example(output_dir, *, cancel_event=None, event_callback=None):
    if cancel_event is not None and cancel_event.is_set():
        raise KeyboardInterrupt('Example preparation cancelled.')
    resource = files('firmavex.product').joinpath('resources/example/image.json')
    data = json.loads(resource.read_text(encoding='utf-8'))
    if not isinstance(data, dict) or type(data.get('schema_version')) is not int or data.get('schema_version') != 1 or data.get('kind') != 'firmavex_product_example_image' or data.get('license') != 'MIT':
        raise ProductError('example_integrity_failure', 'Unsupported built-in example manifest.')
    if not isinstance(data.get('image_base64'), str) or len(data['image_base64']) > 2 * 1024**2 or not isinstance(data.get('sources'), dict) or set(data['sources']) != {'main.c', 'startup.c', 'linker.ld'}:
        raise ProductError('example_integrity_failure', 'Built-in image/source inventory is incomplete.')
    try:
        image = base64.b64decode(data['image_base64'], validate=True)
    except (ValueError, KeyError) as exc:
        raise ProductError('example_integrity_failure', 'Malformed built-in image.') from exc
    if not 0 < len(image) <= 1024 * 1024 or hashlib.sha256(image).hexdigest() != data['image_sha256']:
        raise ProductError('example_integrity_failure', 'Built-in firmware checksum does not match.')
    for name, expected in data['sources'].items():
        if name not in {'main.c', 'startup.c', 'linker.ld'} or hashlib.sha256(files('firmavex.product').joinpath('resources/example/' + name).read_bytes()).hexdigest() != expected:
            raise ProductError('example_integrity_failure', 'Built-in firmware source identity does not match.')
    output = Path(output_dir).expanduser().absolute()
    try:
        output.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise ProductError('output_exists', 'Choose a new directory for the example.') from exc
    if cancel_event is not None and cancel_event.is_set():
        raise KeyboardInterrupt('Example preparation cancelled; no firmware executed.')
    firmware = output / 'example.elf'
    firmware.write_bytes(image)
    from .example import example_configuration
    configuration = example_configuration()
    config = output / 'project.json'
    config.write_text(json.dumps(configuration, indent=2) + '\n', encoding='utf-8')
    from .config import load_config
    from .firmware import inspect_elf
    validated = inspect_elf(load_config(config))
    provenance = {key: value for key, value in data.items() if key != 'image_base64'}
    provenance.update({'origin': 'bundled_verified_image', 'locally_compiled': False, 'firmware_executed': False})
    (output / 'image-provenance.json').write_text(json.dumps(provenance, sort_keys=True, indent=2) + '\n', encoding='utf-8')
    return {'schema_version': 1, 'success': True, 'config_file': str(config), 'firmware_file': str(firmware),
            'firmware': validated, 'provenance': provenance, 'compiler_required': False, 'firmware_executed': False}
