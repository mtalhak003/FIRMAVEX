from dataclasses import replace
import hashlib
import io
from pathlib import Path
import re
import shutil
import struct
import subprocess

from elftools.elf.elffile import ELFFile
import pytest

from firmavex.product.config import load_config
from firmavex.product.errors import ProductError
from firmavex.product.example import build_example
from firmavex.product.firmware import inspect_elf
import firmavex.product.firmware as module


@pytest.fixture(scope="module")
def built_example(tmp_path_factory):
    compiler = shutil.which("arm-none-eabi-gcc")
    if compiler is None:
        pytest.skip("ARM GCC is required for real ELF compilation validation")
    directory = tmp_path_factory.mktemp("product elf with spaces") / "example"
    result = build_example(directory, compiler=compiler)
    return load_config(result["config"]), result


@pytest.fixture
def image(built_example, tmp_path):
    config, _ = built_example
    firmware = tmp_path / "test.elf"
    firmware.write_bytes(config.firmware.read_bytes())
    return replace(config, firmware=firmware)


def edit(config, callback):
    data = bytearray(config.firmware.read_bytes())
    callback(data, ELFFile(io.BytesIO(data)))
    config.firmware.write_bytes(data)


def test_real_compiled_example_identity_and_writable_bindings(built_example):
    config, build = built_example
    result = inspect_elf(config)
    assert result["firmware_sha256"] == hashlib.sha256(config.firmware.read_bytes()).hexdigest()
    assert result["firmware_sha256"] == build["build"]["firmware"]["sha256"]
    assert result["path"] == str(config.firmware)
    assert result["elf"]["target"] == "mps2-an385"
    assert result["elf"]["cpu_arch"] == "ARMv7-M"
    assert result["elf"]["bindings"]["product_inputs[1]"]["address"] == (
        result["elf"]["bindings"]["product_inputs[0]"]["address"] + 4)
    assert result["consistency"] == {"status": "stable_observed", "atomic": False}
    assert "successful execution" in result["limitations"][0]


@pytest.mark.parametrize("offset,value", [(4, 2), (5, 2), (18, 62), (16, 3)])
def test_wrong_elf_class_endianness_machine_or_type(image, offset, value):
    edit(image, lambda data, elf: data.__setitem__(offset, value))
    with pytest.raises(ProductError) as error:
        inspect_elf(image)
    assert error.value.category == "unsupported_firmware"


@pytest.mark.parametrize("data", [b"", b"raw BIN firmware", b"\x7fELF\x01\x01"])
def test_bin_empty_and_truncated_images_rejected(image, data):
    image.firmware.write_bytes(data)
    with pytest.raises(ProductError):
        inspect_elf(image)


def test_absent_image_is_structured_error(image):
    image.firmware.unlink()
    with pytest.raises(ProductError) as error:
        inspect_elf(image)
    assert error.value.category == "invalid_firmware"


@pytest.mark.parametrize("entry", [0, 0x20000001, 0x400001])
def test_entry_requires_thumb_executable_flash(image, entry):
    edit(image, lambda data, elf: struct.pack_into("<I", data, 24, entry))
    with pytest.raises(ProductError, match="Entry"):
        inspect_elf(image)


@pytest.mark.parametrize("stack,reset", [(0x20000004, None), (0x30000000, None), (None, 0)])
def test_reset_vector_and_stack_rejected(image, stack, reset):
    def change(data, elf):
        load = next(s for s in elf.iter_segments() if s["p_type"] == "PT_LOAD" and s["p_paddr"] == 0)
        if stack is not None:
            struct.pack_into("<I", data, load["p_offset"], stack)
        if reset is not None:
            struct.pack_into("<I", data, load["p_offset"] + 4, reset)
    edit(image, change)
    with pytest.raises(ProductError, match="Reset vectors"):
        inspect_elf(image)


@pytest.mark.parametrize("field,value", [(8, 0x10000000), (12, 0x10000000), (20, 0x80000000)])
def test_segment_memory_and_loading_boundaries(image, field, value):
    edit(image, lambda data, elf: struct.pack_into("<I", data, elf.header["e_phoff"] + field, value))
    with pytest.raises(ProductError, match="segment|load address"):
        inspect_elf(image)


def test_rejects_m4_architecture_attribute(image):
    def change(data, elf):
        section = elf.get_section_by_name(".ARM.attributes")
        start, length = section["sh_offset"], section["sh_size"]
        pos = bytes(data[start:start + length]).index(b"\x06\x0a\x07M")
        data[start + pos + 1] = 13
    edit(image, change)
    with pytest.raises(ProductError, match="v7-M"):
        inspect_elf(image)


def test_missing_arm_attributes_rejected(image):
    def change(data, elf):
        section = elf.get_section_by_name(".ARM.attributes")
        start = section["sh_offset"]
        data[start] = ord("B")
    edit(image, change)
    with pytest.raises(ProductError):
        inspect_elf(image)


def test_nonadvancing_arm_attribute_scope_rejected(image):
    def change(data, elf):
        section = elf.get_section_by_name(".ARM.attributes")
        struct.pack_into("<I", data, section["sh_offset"] + 12, 0)
    edit(image, change)
    with pytest.raises(ProductError, match="scope length"):
        inspect_elf(image)


@pytest.mark.parametrize("changes", [
    {"ready_breakpoint": "unknown_ready"},
    {"completion_breakpoint": "unknown_complete"},
    {"input_symbols": ("product_inputs[2]",)},
    {"input_symbols": ("product_inputs",)},
    {"input_symbols": ("product_failure[0]",)},
    {"failure_symbol": "unknown_failure"},
])
def test_missing_functions_and_wrong_binding_shapes(image, changes):
    with pytest.raises(ProductError):
        inspect_elf(replace(image, **changes))


def symbol_edit(config, name, field, value):
    def change(data, elf):
        symbols = elf.get_section_by_name(".symtab")
        index = next(i for i, symbol in enumerate(symbols.iter_symbols()) if symbol.name == name)
        struct.pack_into("<I", data, symbols["sh_offset"] + index * symbols["sh_entsize"] + field, value)
    edit(config, change)


def test_aliases_cannot_select_input_and_failure_same_address(image):
    metadata = inspect_elf(image)
    address = metadata["elf"]["bindings"]["product_inputs[0]"]["address"]
    symbol_edit(image, "product_failure", 4, address)
    with pytest.raises(ProductError, match="alias"):
        inspect_elf(image)


def test_breakpoint_function_aliases_rejected(image):
    address = inspect_elf(image)["elf"]["functions"]["product_input_ready"]
    symbol_edit(image, "product_complete", 4, address | 1)
    with pytest.raises(ProductError, match="distinct addresses"):
        inspect_elf(image)


@pytest.mark.parametrize("address", [0x100, 0x20000001, 0x20400000])
def test_input_address_requires_aligned_writable_ram(image, address):
    symbol_edit(image, "product_inputs", 4, address)
    with pytest.raises(ProductError, match="aligned writable RAM"):
        inspect_elf(image)


def test_symbol_size_must_agree_with_debug_type(image):
    symbol_edit(image, "product_inputs", 8, 4)
    with pytest.raises(ProductError, match="typed uint32"):
        inspect_elf(image)


def test_overlapping_initialized_physical_loads_rejected(image):
    def change(data, elf):
        index = next(i for i, segment in enumerate(elf.iter_segments())
                     if segment["p_type"] == "PT_LOAD" and segment["p_vaddr"] >= 0x20000000)
        struct.pack_into("<I", data, elf.header["e_phoff"] + index * elf.header["e_phentsize"] + 12, 0)
    edit(image, change)
    with pytest.raises(ProductError, match="physical load"):
        inspect_elf(image)


def test_oversized_image_rejected_without_reading(image):
    with image.firmware.open("r+b") as stream:
        stream.truncate(module.MAX_IMAGE_BYTES + 1)
    with pytest.raises(ProductError, match="64 MiB"):
        inspect_elf(image)


@pytest.mark.parametrize("replacement", ["uint16_t product_inputs[2]", "int32_t product_inputs[2]",
                                          "uint32_t product_inputs[1][2]"])
def test_dwarf_rejects_wrong_signedness_element_width_and_dimension(built_example, tmp_path, replacement):
    _, build = built_example
    source_dir = Path(build["output_dir"])
    for name in ("main.c", "startup.c", "linker.ld"):
        (tmp_path / name).write_bytes((source_dir / name).read_bytes())
    main = tmp_path / "main.c"
    main.write_text(main.read_text().replace("uint32_t product_inputs[2]", replacement))
    # The multidimensional variant is valid firmware C with matching accesses.
    if "[1][2]" in replacement:
        main.write_text(re.sub(r"product_inputs\[([01])\](?!\[)",
                               lambda match: f"product_inputs[0][{match.group(1)}]", main.read_text()))
    output = tmp_path / "typed.elf"
    command = [build["build"]["compiler"]["path"], "-mcpu=cortex-m3", "-mthumb", "-g", "-O0",
               "-ffreestanding", "-nostdlib", "-T", str(tmp_path / "linker.ld"),
               str(tmp_path / "startup.c"), str(main), "-o", str(output)]
    subprocess.run(command, check=True, capture_output=True, timeout=30)
    with pytest.raises(ProductError, match="unsigned 32-bit|one-dimensional"):
        inspect_elf(replace(built_example[0], firmware=output))


def test_mid_hash_file_change_rejected_as_consistency_failure(image, monkeypatch):
    original_factory = hashlib.sha256
    changed = False
    class ChangingDigest:
        def __init__(self):
            self.digest = original_factory()
        def update(self, data):
            nonlocal changed
            self.digest.update(data)
            if not changed:
                changed = True
                original = image.firmware.read_bytes()
                image.firmware.write_bytes(original[:-1] + bytes([original[-1] ^ 1]))
        def hexdigest(self):
            return self.digest.hexdigest()
    monkeypatch.setattr(module.hashlib, "sha256", ChangingDigest)
    with pytest.raises(ProductError) as error:
        inspect_elf(image)
    assert error.value.category == "artifact_changed"


def test_change_after_hash_during_metadata_validation_rejected(image, monkeypatch):
    original = module._inspect
    def changing_inspect(data, config):
        result = original(data, config)
        config.firmware.write_bytes(data[:-1] + bytes([data[-1] ^ 1]))
        return result
    monkeypatch.setattr(module, "_inspect", changing_inspect)
    with pytest.raises(ProductError) as error:
        inspect_elf(image)
    assert error.value.category == "artifact_changed"


def test_canonical_configuration_required(image):
    with pytest.raises(ProductError, match="canonical"):
        inspect_elf(object())
