"""Compatibility-gate logic only; synthetic digests are not execution evidence."""

from types import SimpleNamespace
import json
import pytest
from firmavex.backends import qualification


@pytest.fixture
def windows(monkeypatch):
    monkeypatch.setattr(qualification, "os", SimpleNamespace(name="nt", environ={}))
    monkeypatch.setattr(qualification.platform, "machine", lambda: "AMD64")


def test_empty_catalog_cannot_enable_native_windows(windows, monkeypatch):
    resource = SimpleNamespace(
        joinpath=lambda name: SimpleNamespace(
            read_text=lambda **kwargs: json.dumps({"schema_version": 1, "profiles": []})
        )
    )
    monkeypatch.setattr(qualification, "files", lambda package: resource)
    with pytest.raises(RuntimeError, match="not passed"):
        qualification.require_windows_qualification("riscv32-virt")


def test_candidate_is_explicit_and_not_a_catalog_entry(windows, monkeypatch):
    qualification.os.environ["FIRMAVEX_QUALIFY_BACKENDS"] = "1"
    monkeypatch.setattr(
        qualification,
        "files",
        lambda *args: pytest.fail("Candidate does not imply a catalog entry"),
    )
    qualification.require_windows_qualification("riscv32-virt")


def test_catalog_requires_every_selected_digest(windows, monkeypatch):
    candidate = {
        "system": "Windows",
        "architecture": "x86_64",
        "profile": "riscv32-virt",
        "tools": {
            "qemu-system-riscv32": {"sha256": "a" * 64},
            "gdb-multiarch": {"sha256": "b" * 64},
        },
    }
    resource = SimpleNamespace(
        joinpath=lambda name: SimpleNamespace(
            read_text=lambda **kwargs: json.dumps(
                {"schema_version": 1, "profiles": [candidate]}
            )
        )
    )
    monkeypatch.setattr(qualification, "files", lambda package: resource)
    monkeypatch.setattr(
        qualification,
        "find_many",
        lambda names: {name: name for name in names},
    )
    monkeypatch.setattr(
        qualification,
        "file_identity",
        lambda path: {
            "sha256": "a" * 64 if path == "qemu-system-riscv32" else "b" * 64
        },
    )
    qualification.require_windows_qualification("riscv32-virt")
    monkeypatch.setattr(
        qualification, "file_identity", lambda path: {"sha256": "c" * 64}
    )
    with pytest.raises(RuntimeError, match="not passed"):
        qualification.require_windows_qualification("riscv32-virt")


def test_catalog_checks_real_file_bytes_with_discovery_path_strings(
    windows, tmp_path, monkeypatch
):
    """The production discovery API returns strings, never Selection objects."""
    import hashlib

    paths = {}
    expected = {}
    for name in ("qemu-system-riscv32", "gdb-multiarch"):
        path = tmp_path / name
        data = ("synthetic gate test, not runtime evidence: " + name).encode()
        path.write_bytes(data)
        paths[name] = str(path)
        expected[name] = {"sha256": hashlib.sha256(data).hexdigest()}
    record = {
        "schema_version": 1,
        "profiles": [
            {
                "system": "Windows",
                "architecture": "x86_64",
                "profile": "riscv32-virt",
                "tools": expected,
            }
        ],
    }
    resource = SimpleNamespace(
        joinpath=lambda name: SimpleNamespace(
            read_text=lambda **kwargs: json.dumps(record)
        )
    )
    monkeypatch.setattr(qualification, "files", lambda package: resource)
    monkeypatch.setattr(qualification, "find_many", lambda names: paths)
    qualification.require_windows_qualification("riscv32-virt")
    (tmp_path / "gdb-multiarch").write_bytes(b"changed")
    with pytest.raises(RuntimeError, match="not passed"):
        qualification.require_windows_qualification("riscv32-virt")
