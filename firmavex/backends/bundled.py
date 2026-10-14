"""Integrity-checked MIT RV32 example, prepared without a compiler or execution.

The application package is the trust root. Checksums do not authenticate a
modified installation or provide an OS sandbox.
"""

import base64
import hashlib
from importlib.resources import files
import json
from pathlib import Path
from firmavex.product.tools import file_identity

_IMAGE_SHA256 = "a032837af7682279bdf5c8002161a880a4470aaa869ec917602a21e13e79e464"


def catalog():
    resource = files("firmavex.backends").joinpath("examples")
    manifest = json.loads(resource.joinpath("image.json").read_text(encoding="utf-8"))
    if (
        type(manifest) is not dict
        or type(manifest.get("schema_version")) is not int
        or manifest.get("schema_version") != 1
        or manifest.get("kind") != "firmavex_riscv_builtin_image"
        or manifest.get("license") != "MIT"
        or manifest.get("profile") != "riscv32-virt"
        or manifest.get("image_sha256") != _IMAGE_SHA256
    ):
        raise ValueError("Invalid bundled RISC-V example catalog")
    if (
        type(manifest.get("image_base64")) is not str
        or len(manifest["image_base64"]) > 2 * 1024 * 1024
        or set(manifest.get("sources", {})) != {"riscv.c", "riscv.S", "riscv.ld"}
    ):
        raise ValueError("Invalid bundled image inventory")
    for name, expected in manifest["sources"].items():
        if hashlib.sha256(resource.joinpath(name).read_bytes()).hexdigest() != expected:
            raise ValueError("Bundled RISC-V source checksum mismatch")
    image = base64.b64decode(manifest["image_base64"], validate=True)
    if not image or hashlib.sha256(image).hexdigest() != _IMAGE_SHA256:
        raise ValueError("Bundled RISC-V image checksum mismatch")
    return manifest, image


def validate_builtin_riscv(path):
    manifest, _ = catalog()
    identity = file_identity(path)
    if identity["sha256"] != manifest["image_sha256"]:
        raise ValueError(
            "RISC-V image is not the verified bundled example; acknowledge a trusted project instead"
        )
    return identity


def prepare_builtin_riscv(output, *, cancel_event=None):
    if cancel_event is not None and cancel_event.is_set():
        raise KeyboardInterrupt("Example preparation cancelled")
    manifest, image = catalog()
    output = Path(output).expanduser().absolute()
    output.mkdir(parents=True, exist_ok=False)
    if cancel_event is not None and cancel_event.is_set():
        raise KeyboardInterrupt("Example preparation cancelled; no guest execution")
    path = output / "firmware.elf"
    path.write_bytes(image)
    identity = validate_builtin_riscv(path)
    provenance = {k: v for k, v in manifest.items() if k != "image_base64"}
    provenance.update(
        compiler_required=False, locally_compiled=False, firmware_executed=False
    )
    (output / "image-provenance.json").write_text(
        json.dumps(provenance, sort_keys=True, indent=2) + "\n"
    )
    return {
        "schema_version": 1,
        "profile": "riscv32-virt",
        "source": str(path),
        "firmware": identity,
        "compiler_required": False,
        "firmware_executed": False,
    }
