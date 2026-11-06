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


@pytest.fixture
def windows_gate(monkeypatch):
    # Replace only this module's OS reference, not pathlib's process-wide OS.
    monkeypatch.setattr(support, 'os', SimpleNamespace(name='nt'))
    monkeypatch.setattr(support, 'platform', SimpleNamespace(machine=lambda: 'AMD64'))


@pytest.mark.parametrize('name,field,value', [
    ('qemu', 'version', 'QEMU emulator version 11.1.3'),
    ('qemu', 'sha256', '0' * 64),
    ('gdb', 'version', 'GNU gdb (GDB) 18.2'),
    ('gdb', 'sha256', '0' * 64),
])
def test_rejection_reports_both_tools_and_exact_mismatching_field(windows_gate, name, field, value):
    tools = qualified_tools()
    tools.identities[name][field] = value
    with pytest.raises(ProductError) as caught:
        support.require_native_support(tools)
    assert caught.value.category == 'unsupported_platform'
    details = caught.value.details['qualification']
    assert details['host_architecture'] == 'x86_64'
    assert details['required_profile'] == support.WINDOWS_PROFILE_ID
    for key, (version, digest) in support.WINDOWS_EXECUTABLES.items():
        row = details['tools'][key]
        assert row['expected'] == {'version': version, 'sha256': digest}
        assert row['observed'] == tools.identities[key]
        for attribute, matched in row['matches'].items():
            assert matched is (not (key == name and attribute == field))


@pytest.mark.parametrize('missing', ['qemu', 'gdb', 'both', 'version', 'sha256'])
def test_missing_identity_is_explicitly_unavailable_and_still_rejected(windows_gate, missing):
    tools = qualified_tools()
    if missing == 'both': tools.identities.clear()
    elif missing in ('qemu', 'gdb'): tools.identities.pop(missing)
    else: tools.identities['qemu'].pop(missing)
    with pytest.raises(ProductError) as caught:
        support.require_native_support(tools)
    rows = caught.value.details['qualification']['tools']
    for name in ('qemu', 'gdb'):
        for field in ('version', 'sha256'):
            if field not in tools.identities.get(name, {}):
                assert rows[name]['observed'][field] is None
                assert rows[name]['matches'][field] is None


@pytest.mark.parametrize('identities', [None, [], {'qemu': None}, {'qemu': []}],
                         ids=['null-map', 'list-map', 'null-entry', 'list-entry'])
def test_inherited_malformed_identity_container_behavior(windows_gate, monkeypatch, identities):
    # Discovery normally constructs dictionaries. This documents the inherited
    # error for noncanonical containers; Batch 23A does not broaden admission.
    monkeypatch.setattr(support, '_qualification_details',
                        lambda *a: pytest.fail('Malformed containers fail before diagnostics'))
    with pytest.raises(AttributeError, match='get'):
        support.require_native_support(SimpleNamespace(identities=identities))


def test_success_does_not_construct_failure_diagnostic(windows_gate, monkeypatch):
    monkeypatch.setattr(support, '_qualification_details', lambda *a: pytest.fail('success diagnostic'))
    assert support.require_native_support(qualified_tools()) is None


def test_non_windows_does_not_construct_failure_diagnostic(monkeypatch):
    monkeypatch.setattr(support, 'os', SimpleNamespace(name='posix'))
    monkeypatch.setattr(support, '_qualification_details', lambda *a: pytest.fail('non-Windows diagnostic'))
    assert support.require_native_support(SimpleNamespace(identities={})) is None


@pytest.mark.parametrize('value', [
    'https://user:password@private.invalid/?token=secret',
    'QEMU emulator version 11.1.3\nAuthorization: secret',
    'GNU gdb (GDB) 18.1 /home/private/secret',
    'QEMU emulator version 11.1.3-secret',
    'x' * 10000, True, 123, [], {},
], ids=['url', 'multiline', 'private-path', 'suffix', 'oversized', 'bool', 'integer', 'list', 'dict'])
def test_diagnostic_omits_unsafe_values_and_unrelated_metadata(value):
    import json
    identities = {name: {'version': value, 'sha256': value, 'path': '/private/secret',
                         'environment': {'TOKEN': 'secret'}} for name in ('qemu', 'gdb')}
    identities['compiler'] = {'version': 'secret'}
    details = support._qualification_details(identities, value)
    assert details['host_architecture'] == 'unknown'
    assert set(details['tools']) == {'qemu', 'gdb'}
    assert all(row['observed'] == {'version': None, 'sha256': None}
               for row in details['tools'].values())
    assert 'secret' not in json.dumps(details)


def test_batch23a_preserves_original_qualified_executable_identities():
    assert support.WINDOWS_PROFILE_ID == 'msys2-ucrt64-qemu11.1.2-gdb18.1-v1'
    assert support.WINDOWS_EXECUTABLES == {
        'qemu': ('QEMU emulator version 11.1.2',
                 '1247e03f58f2e845ff516e0cc951b67d0ee5dd5d6bcbe89faedbec692641b244'),
        'gdb': ('GNU gdb (GDB) 18.1',
                'f867205234b5c61ad53bbb70db25462566b1742b409eb345f7f0178fd388f236'),
    }
