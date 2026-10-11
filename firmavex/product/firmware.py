"""Conservative static validation for the one supported QEMU Cortex-M3 target.

These checks establish a supported image shape, not peripheral compatibility,
successful execution, atomic snapshots, or hardware validation.
"""

import hashlib
import io
import os
from pathlib import Path
import struct

from elftools.elf.elffile import ELFFile
from elftools.elf.sections import ARMAttributesSection, SymbolTableSection

from firmavex.product.config import BINDING, ProductConfig
from firmavex.product.errors import ProductError


FLASH = (0, 4 * 1024 * 1024)
RAM = (0x20000000, 0x20400000)
MAX_IMAGE_BYTES = 64 * 1024 * 1024


def _reject(message: str) -> None:
    raise ProductError("unsupported_firmware", message)


def _fingerprint(stat) -> tuple:
    return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)


def _read_image(path: Path) -> tuple[bytes, dict, tuple]:
    try:
        before = path.stat()
        if not path.is_file() or not 0 < before.st_size <= MAX_IMAGE_BYTES:
            _reject("Firmware must be a regular, nonempty ELF no larger than 64 MiB.")
        digest = hashlib.sha256()
        pieces = []
        with path.open("rb") as stream:
            opened = os.fstat(stream.fileno())
            while chunk := stream.read(1024 * 1024):
                pieces.append(chunk)
                digest.update(chunk)
                if sum(map(len, pieces)) > MAX_IMAGE_BYTES:
                    _reject("Firmware grew beyond the 64 MiB validation limit.")
            finished = os.fstat(stream.fileno())
        after = path.stat()
    except OSError as exc:
        raise ProductError("invalid_firmware", f"Cannot read firmware: {exc}") from exc
    if not (_fingerprint(before) == _fingerprint(opened) == _fingerprint(finished) == _fingerprint(after)):
        raise ProductError("artifact_changed", "Firmware changed during validation.")
    data = b"".join(pieces)
    return data, {"path": str(path), "firmware_sha256": digest.hexdigest(),
                  "size_bytes": len(data)}, _fingerprint(after)


def _contains(region: tuple[int, int], address: int, size: int) -> bool:
    return size > 0 and region[0] <= address < address + size <= region[1]


def _cpu_attributes(elf: ELFFile) -> dict:
    section = elf.get_section_by_name(".ARM.attributes")
    if not isinstance(section, ARMAttributesSection):
        _reject("Required .ARM.attributes Cortex-M3 metadata is missing.")
    # Bound every declared attribute scope before the library's iterators run.
    # The supported GCC output has a single aeabi vendor; rejecting other
    # layouts avoids accepting incomplete or nonadvancing length fields.
    raw = section.data()
    if len(raw) < 10 or raw[0] != ord("A"):
        _reject("Malformed ARM attribute section.")
    length = struct.unpack_from("<I", raw, 1)[0]
    if length != len(raw) - 1 or raw[5:11] != b"aeabi\0":
        _reject("Only one complete aeabi ARM attribute subsection is supported.")
    cursor = 11
    while cursor < len(raw):
        # The supported file/section/symbol scope tags are single-byte ULEB.
        if raw[cursor] not in (1, 2, 3) or cursor + 5 > len(raw):
            _reject("Malformed ARM attribute scope.")
        scope_length = struct.unpack_from("<I", raw, cursor + 1)[0]
        if scope_length < 5 or cursor + scope_length > len(raw):
            _reject("Malformed ARM attribute scope length.")
        cursor += scope_length
    attrs = {}
    for sub in section.iter_subsections("aeabi"):
        for scope in sub.iter_subsubsections("TAG_FILE"):
            for attr in scope.iter_attributes():
                if attr.tag in {"TAG_CPU_NAME", "TAG_CPU_ARCH", "TAG_CPU_ARCH_PROFILE"}:
                    if attr.tag in attrs and attrs[attr.tag] != attr.value:
                        _reject("Conflicting ARM CPU attributes.")
                    attrs[attr.tag] = attr.value
    name = attrs.get("TAG_CPU_NAME")
    if isinstance(name, bytes):
        name = name.decode("ascii", errors="strict")
    # ARM ABI attributes: arch 10 = v7; profile ASCII 'M' = microcontroller.
    if attrs.get("TAG_CPU_ARCH") != 10 or attrs.get("TAG_CPU_ARCH_PROFILE") != ord("M"):
        _reject("Firmware must declare ARM v7-M; other Cortex-M architectures are unsupported.")
    # GCC commonly emits architecture name "7-M" for -mcpu=cortex-m3.
    if type(name) is not str or name.lower() not in {"cortex-m3", "7-m"}:
        _reject("Firmware must declare Cortex-M3-compatible ARMv7-M CPU attributes.")
    return {"cpu_name": name, "cpu_arch": "ARMv7-M"}


def _resolved_type(die):
    seen = set()
    while die.tag in {"DW_TAG_typedef", "DW_TAG_const_type", "DW_TAG_volatile_type",
                      "DW_TAG_restrict_type"}:
        if die.offset in seen or "DW_AT_type" not in die.attributes:
            _reject("Unsupported recursive or incomplete variable type.")
        seen.add(die.offset)
        die = die.get_DIE_from_attribute("DW_AT_type")
    return die


def _object_shape(die) -> tuple[bool, int]:
    """Only uint32 scalars and fixed, one-dimensional uint32 arrays."""
    if "DW_AT_type" not in die.attributes:
        _reject("Required variable has no debug type information.")
    kind = _resolved_type(die.get_DIE_from_attribute("DW_AT_type"))
    array = kind.tag == "DW_TAG_array_type"
    count = 1
    if array:
        dimensions = [child for child in kind.iter_children() if child.tag == "DW_TAG_subrange_type"]
        if len(dimensions) != 1:
            _reject("Only one-dimensional input/status arrays are supported.")
        dim = dimensions[0].attributes
        if "DW_AT_lower_bound" in dim and dim["DW_AT_lower_bound"].value != 0:
            _reject("Array lower bounds must be zero.")
        if "DW_AT_count" in dim:
            count = dim["DW_AT_count"].value
        elif "DW_AT_upper_bound" in dim:
            count = dim["DW_AT_upper_bound"].value + 1
        else:
            _reject("Arrays must have a fixed debug-information length.")
        if type(count) is not int or count <= 0:
            _reject("Array length must be a positive fixed integer.")
        if "DW_AT_type" not in kind.attributes:
            _reject("Array element type is missing.")
        kind = _resolved_type(kind.get_DIE_from_attribute("DW_AT_type"))
    if (kind.tag != "DW_TAG_base_type"
            or kind.attributes.get("DW_AT_byte_size") is None
            or kind.attributes["DW_AT_byte_size"].value != 4
            or kind.attributes.get("DW_AT_encoding") is None
            or kind.attributes["DW_AT_encoding"].value != 7):
        _reject("Inputs and failure values must be unsigned 32-bit scalar/array elements.")
    return array, count


def _variables(elf: ELFFile, needed: set[str]) -> dict:
    if not elf.has_dwarf_info():
        _reject("DWARF variable types are required; build symbolized firmware with -g.")
    variables = {}
    for cu in elf.get_dwarf_info().iter_CUs():
        for die in cu.iter_DIEs():
            if die.tag != "DW_TAG_variable" or "DW_AT_name" not in die.attributes:
                continue
            name = die.attributes["DW_AT_name"].value.decode("utf-8", errors="strict")
            declaration = die.attributes.get("DW_AT_declaration")
            if name in needed and not (declaration is not None and declaration.value):
                shape = _object_shape(die)
                if name in variables:
                    _reject(f"Ambiguous debug variable name: {name}.")
                variables[name] = shape
    if needed - variables.keys():
        _reject("Missing debug variable types: " + ", ".join(sorted(needed - variables.keys())))
    return variables


def _inspect(data: bytes, config: ProductConfig) -> dict:
    elf = ELFFile(io.BytesIO(data))
    if (elf.elfclass != 32 or not elf.little_endian or elf.header["e_machine"] != "EM_ARM"
            or elf.header["e_type"] != "ET_EXEC"):
        _reject("Only little-endian ARM ELF32 executable images are supported; BIN is unsupported.")
    attributes = _cpu_attributes(elf)
    loads = [segment for segment in elf.iter_segments()
             if segment["p_type"] == "PT_LOAD" and segment["p_memsz"]]
    if not loads:
        _reject("Firmware has no loadable segments.")
    regions, physical_regions = [], []
    for segment in loads:
        vaddr, paddr, memsz, filesz = (segment[key] for key in ("p_vaddr", "p_paddr", "p_memsz", "p_filesz"))
        if filesz > memsz or segment["p_offset"] + filesz > len(data):
            _reject("Invalid or truncated loadable segment.")
        if not (_contains(FLASH, vaddr, memsz) or _contains(RAM, vaddr, memsz)):
            _reject("Firmware segment exceeds the mps2-an385 FLASH/RAM map.")
        if filesz and not (_contains(FLASH, paddr, filesz) or _contains(RAM, paddr, filesz)):
            _reject("Firmware load address exceeds the supported memory map.")
        if filesz and any(paddr < old[1] and old[0] < paddr + filesz for old in physical_regions):
            _reject("Overlapping initialized physical load segments are unsupported.")
        if filesz:
            physical_regions.append((paddr, paddr + filesz))
        if any(vaddr < old[1] and old[0] < vaddr + memsz for old in regions):
            _reject("Overlapping loadable virtual segments are unsupported.")
        regions.append((vaddr, vaddr + memsz))
    executable = lambda address: any((segment["p_flags"] & 1)
        and segment["p_vaddr"] <= address < segment["p_vaddr"] + segment["p_memsz"]
        for segment in loads)
    entry = elf.header["e_entry"]
    if not entry & 1 or not _contains(FLASH, entry & ~1, 2) or not executable(entry & ~1):
        _reject("Entry must be a Thumb address in executable FLASH.")
    vectors = next((segment for segment in loads if segment["p_paddr"] == 0 and segment["p_filesz"] >= 8), None)
    if vectors is None:
        _reject("An initialized reset vector table at FLASH address zero is required.")
    sp, reset = struct.unpack_from("<II", data, vectors["p_offset"])
    if not RAM[0] < sp <= RAM[1] or sp % 8 or reset != entry:
        _reject("Reset vectors must contain an aligned RAM stack and the Thumb entry point.")
    bindings = (*config.input_symbols, config.failure_symbol)
    bases = {BINDING.fullmatch(name).group(1) for name in bindings}
    needed_symbols = bases | {config.ready_breakpoint, config.completion_breakpoint}
    symbols = {}
    for section in elf.iter_sections():
        if not isinstance(section, SymbolTableSection):
            continue
        for symbol in section.iter_symbols():
            if symbol["st_shndx"] == "SHN_UNDEF" or symbol.name not in needed_symbols:
                continue
            if symbol.name in symbols and (symbols[symbol.name] is None
                                          or dict(symbol.entry) != dict(symbols[symbol.name].entry)):
                # Reject ambiguity only for configured names below.
                symbols[symbol.name] = None
            else:
                symbols[symbol.name] = symbol
    funcs = {}
    for name in (config.ready_breakpoint, config.completion_breakpoint):
        symbol = symbols.get(name)
        if (symbol is None or symbol["st_info"]["type"] != "STT_FUNC"
                or not executable(symbol["st_value"] & ~1)):
            _reject(f"Required breakpoint function is missing or nonexecutable: {name}.")
        funcs[name] = symbol["st_value"] & ~1
    if len(set(funcs.values())) != 2:
        _reject("Input-ready and completion functions must have distinct addresses.")
    shapes = _variables(elf, bases)
    result_bindings, addresses = {}, set()
    for binding in bindings:
        match = BINDING.fullmatch(binding)
        name, index = match.groups()
        symbol = symbols.get(name)
        array, count = shapes[name]
        if (symbol is None or symbol["st_info"]["type"] != "STT_OBJECT"
                or symbol["st_size"] != count * 4
                or (array and index is None) or (not array and index is not None)):
            _reject(f"Binding must resolve to a typed uint32 scalar/array element: {binding}.")
        offset = int(index) if index is not None else 0
        if offset >= count:
            _reject(f"Input/status array index is out of bounds: {binding}.")
        address = symbol["st_value"] + offset * 4
        if (address % 4 or not _contains(RAM, address, 4)
                or not any((segment["p_flags"] & 2) and segment["p_vaddr"] <= address
                           and address + 4 <= segment["p_vaddr"] + segment["p_memsz"] for segment in loads)):
            _reject(f"Binding must occupy aligned writable RAM: {binding}.")
        if address in addresses:
            _reject("Input/failure bindings alias the same memory location.")
        addresses.add(address)
        result_bindings[binding] = {"address": address, "size_bytes": 4,
                                    "object": name, "element_index": offset if array else None}
    return {"format": "ELF32", "architecture": "ARM", "endianness": "little",
            "target": "mps2-an385", "entry": entry, **attributes,
            "initial_stack_pointer": sp, "functions": funcs, "bindings": result_bindings,
            "load_segments": [{key: segment[key] for key in
                ("p_vaddr", "p_paddr", "p_memsz", "p_filesz", "p_flags")} for segment in loads]}


def inspect_elf(config: ProductConfig) -> dict:
    if type(config) is not ProductConfig:
        raise ProductError("invalid_configuration", "A canonical ProductConfig is required.")
    data, identity, fingerprint = _read_image(config.firmware)
    try:
        metadata = _inspect(data, config)
    except ProductError:
        raise
    except Exception as exc:
        # Malformed external metadata can raise library-specific exceptions.
        # Control-flow exceptions still propagate rather than becoming data.
        raise ProductError("unsupported_firmware", f"Malformed or unsupported ELF metadata: {exc}") from exc
    try:
        if _fingerprint(config.firmware.stat()) != fingerprint:
            raise ProductError("artifact_changed", "Firmware changed while validating captured metadata.")
    except OSError as exc:
        raise ProductError("artifact_changed", "Firmware disappeared during validation.") from exc
    return {**identity, "elf": metadata, "consistency": {"status": "stable_observed", "atomic": False},
            "limitations": ["Static checks do not establish peripheral compatibility or successful execution.",
                            "Only mps2-an385 Cortex-M3 symbolized ELF firmware is supported.",
                            "This is not a filesystem snapshot or hardware validation."]}
