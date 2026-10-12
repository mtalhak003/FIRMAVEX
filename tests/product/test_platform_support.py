from types import SimpleNamespace

import pytest
from firmavex.product import platform_support as support
from firmavex.product.errors import ProductError


def qualified_tools():
    return SimpleNamespace(identities={name: {'version': version, 'sha256': digest}
                                      for name, (version, digest) in support.WINDOWS_EXECUTABLES.items()})


def test_qualified_profile_is_exact_and_versioned():
    assert support.windows_profile(qualified_tools(), machine='AMD64') == support.WINDOWS_PROFILE_ID
    assert support.WINDOWS_PROFILE_VERSION == 1


@pytest.mark.parametrize('name', ['qemu', 'gdb'])
@pytest.mark.parametrize('field', ['version', 'sha256'])
def test_version_alone_or_checksum_alone_cannot_open_gate(name, field):
    tools = qualified_tools()
    tools.identities[name][field] = 'different'
    assert support.windows_profile(tools, machine='x86_64') is None


@pytest.mark.parametrize('machine', ['arm64', 'x86', 'unknown'])
def test_other_architectures_remain_gated(machine):
    assert support.windows_profile(qualified_tools(), machine=machine) is None


def test_gate_fails_closed_before_any_dispatch(monkeypatch):
    monkeypatch.setattr(support.os, 'name', 'nt')
    monkeypatch.setattr(support.platform, 'machine', lambda: 'AMD64')
    with pytest.raises(ProductError) as caught:
        support.require_native_support(SimpleNamespace(identities={}))
    assert caught.value.category == 'unsupported_platform'
    support.require_native_support(qualified_tools())
