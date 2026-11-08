"""Synthetic archive contracts only; no fixture here is native execution evidence."""
import hashlib
import json
from pathlib import Path
import stat
import struct
import subprocess
import sys
import zipfile

import pytest

from tools import windows_candidate_evidence as evidence
from tools.windows_runtime_candidate import CANDIDATE, PACKAGES

REVISION, RUN = 'a' * 40, '123'


def encoded(value):
    return (json.dumps(value, sort_keys=True) + '\n').encode()


@pytest.fixture
def records(monkeypatch):
    """Invented unit fixture, never supplied as an actual campaign/CI archive."""
    image = b'\x7fELFsynthetic unit-test image; not executable firmware'
    digest = hashlib.sha256(image).hexdigest()
    # Explicit synthetic trust anchor; real verifier uses the source-owned image manifest.
    monkeypatch.setattr(evidence, '_bundled_image_identity', lambda: {
        'image_sha256': digest, 'manifest_sha256': 'c'*64})
    tools = {n: {'version': v, 'sha256': h, 'size_bytes': 100} for n, (v, h) in CANDIDATE.items()}
    vendor = {'bin/qemu-system-arm.exe': {'sha256': tools['qemu']['sha256'], 'size_bytes': 100},
              'bin/gdb-multiarch.exe': {'sha256': tools['gdb']['sha256'], 'size_bytes': 100},
              'share/licenses/fixture/COPYING': {'sha256': 'b' * 64, 'size_bytes': 10}}
    members = {'acquisition/packages.txt': '\n'.join(f'{n} {v}' for n, v in PACKAGES.items()).encode(),
               'acquisition/signature-policy.txt': b'PackageRequired\nPackageTrustedOnly\n',
               'source-probe/vendor-files.json': encoded(vendor),
               'source-probe/example/example.elf': image,
               'source-probe/example/image-provenance.json': encoded({'image_sha256': digest,
                    'origin': 'bundled_verified_image', 'locally_compiled': False})}
    cases, plan = [], []
    for inputs, failure in [([2, 1], 1), ([2, 0], 0)]:
        for symbol, observed in [('product_failure', failure), ('initialized_data', 0x13579bdf)]:
            triggered = symbol == 'initialized_data' or bool(failure)
            name = f'{symbol}-({inputs[0]}, {inputs[1]})'
            cases.append((name, 1, 1, int(triggered), False, 1 if triggered else None))
            plan.append((f'{symbol}-{inputs[0]}-{inputs[1]}', inputs, observed, triggered, None))
    cases.extend([('enumerative-search', 10, 16, 1, False, 10), ('reproduction', 3, 3, 3, False, 1),
                  ('timeout', 1, 2, 0, True, None), ('cancel', 1, 2, 0, True, None)])
    plan.extend(('enumerative-search', [i//4, i%4], int(i==9), i==9, None) for i in range(10))
    plan.extend(('reproduction', [2, 1], 1, True, None) for _ in range(3))
    plan.extend([('timeout', [2, 1], None, False, 'timeout'), ('cancel', [2, 1], None, False, 'cancelled')])
    for i, (case, inputs, observed, triggered, fault) in enumerate(plan, 1):
        runtime = {'schema_version': 1, 'backend': 'qemu-mps2-an385-gdb', 'attempt_id': f'{i:032x}',
                   'inputs': inputs, 'tools': {'identities': tools},
                   'firmware': {'sha256': digest, 'size_bytes': len(image)},
                   'firmware_validation': {'firmware_sha256': digest, 'elf': {'target': 'mps2-an385'}},
                   'guest_dispatched': True, 'input_injected': True, 'completion_reached': not bool(fault),
                   'cleanup_verified': True, 'duration_seconds': 0.1,
                   'cleanup': {'success': True, 'errors': [], 'processes': [
                       {'name': n, 'pid': p, 'reaped': True, 'return_code': 0,
                        'windows_identity': {'terminated': True, 'wait_status': 0, 'creation_time': p}}
                       for n, p in [('qemu', 1), ('gdb', 2)]]}}
        if fault:
            runtime.update(error_category=fault, classification='interrupted' if fault == 'cancelled' else 'infrastructure_failure',
                           measurement_mode='unverified_runtime_observation')
        else:
            runtime.update(measurement_mode='real_firmware', observed_value=observed, failure_condition_observed=triggered,
                           classification='configured_failure_observed' if triggered else 'completed_without_configured_failure',
                           observation={'success': True, 'ready_reached': True, 'completion_reached': True,
                                        'observed_value': observed, 'triggered': triggered,
                                        'inputs_read_back': dict(zip(['product_inputs[0]', 'product_inputs[1]'], inputs))})
        members[f'source-probe/candidate-receipt-{i:02}.json'] = encoded(
            {'candidate_only': True, 'production_qualified': False, 'case': case, 'runtime': runtime})
    report = {'schema_version': 1, 'kind': 'firmavex_windows_runtime_candidate',
              'candidate_only': True, 'production_qualified': False, 'status': 'candidate_source_probe_passed',
              'source_revision': REVISION, 'run_id': RUN, 'host': {'os': 'Windows', 'architecture': 'x86_64'},
              'candidate_expected': {n: {'version': v, 'sha256': h} for n, (v, h) in CANDIDATE.items()},
              'tools': tools, 'packages': PACKAGES, 'signature_policy': ['PackageRequired', 'PackageTrustedOnly'],
              'production_rejection': {'required_profile': evidence.WINDOWS_PROFILE_ID},
              'vendor_inventory_sha256': hashlib.sha256(members['source-probe/vendor-files.json']).hexdigest(),
              'cases': []}
    for name, count, budget, triggers, aborted, first in cases:
        report['cases'].append({'name': name, 'accounting': {
            'attempted_executions': count, 'execution_budget': budget, 'successful_executions': 0 if aborted else count,
            'infrastructure_failures': int(aborted), 'failure_triggering_executions': triggers,
            'budget_remaining': budget-count, 'aborted': aborted, 'failure_found': bool(triggers),
            'budget_exhausted': budget == count, 'first_failure_execution': first,
            'time_to_first_failure_seconds': None if first is None else 0.1}})
    members['source-probe/candidate-report.json'] = encoded(report)
    members['source-probe/candidate-resource.json'] = encoded({'candidate_only': True, 'production_qualified': False,
        'firmware_executed': False, 'requested_limit_bytes': 128*1024**2, 'allocation_bytes': 256*1024**2,
        'exit_code': 1, 'cleanup': [{'pid': 10, 'returncode': 1, 'reaped': True}]})
    groups = [list(evidence.REQUIRED_TESTS.items())[:4], list(evidence.REQUIRED_TESTS.items())[6:],
              list(evidence.REQUIRED_TESTS.items())[4:6]]
    for i, group in enumerate(groups):
        names = [(name, f'{name}[{index}]') for name, count in group for index in range(count)]
        body = ''.join(f'<testcase classname="{evidence.REQUIRED_MODULES[base]}" name="{name}"/>' for base, name in names)
        members[f'test-diagnostics/fixture-{i}/pytest.xml'] = (
            f'<testsuites><testsuite tests="{len(names)}" failures="0" errors="0" skipped="0">{body}</testsuite></testsuites>').encode()
    return members


def archive(tmp_path, records, extras=()):
    path = tmp_path / 'synthetic-candidate-fixture.zip'
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as stream:
        for name, value in records.items(): stream.writestr(name, value)
        for name, value in extras: stream.writestr(name, value)
    return path


def verify(path, **overrides):
    expected = dict(expected_sha256=hashlib.sha256(path.read_bytes()).hexdigest(), expected_revision=REVISION, expected_run_id=RUN)
    expected.update(overrides)
    return evidence.verify_archive(path, **expected)


def change(records, name, update):
    value = json.loads(records[name]); update(value); records[name] = encoded(value)


def test_consistent_synthetic_archive_is_read_only_and_never_qualified(tmp_path, records):
    path = archive(tmp_path, records)
    before = path.read_bytes()
    result = verify(path)
    assert result['validation'] == 'passed', result
    assert result['production_qualified'] is False and result['candidate_only'] is True
    assert 'native execution authenticity' in result['not_proven']
    assert result['attempt_receipts'] == 19 and result['successful_observations'] == 17
    assert result['infrastructure_failures'] == 2 and result['junit']['passed'] == 17
    assert list(tmp_path.iterdir()) == [path] and path.read_bytes() == before


@pytest.mark.parametrize('field,value', [('expected_sha256', '0'*64), ('expected_revision', 'b'*40),
    ('expected_run_id', '999'), ('expected_sha256', 'INVALID'), ('expected_revision', 'bad'), ('expected_run_id', 123)])
def test_caller_expected_identities_are_mandatory(tmp_path, records, field, value):
    assert verify(archive(tmp_path, records), **{field:value})['validation'] == 'failed'


@pytest.mark.parametrize('field,value', [('production_qualified', True), ('candidate_only', False),
    ('status', 'candidate_preflight_only'), ('host', {'os':'Linux','architecture':'x86_64'}), ('schema_version', True)])
def test_report_labels_and_completion_fail_closed(tmp_path, records, field, value):
    change(records, 'source-probe/candidate-report.json', lambda r:r.update({field:value}))
    assert verify(archive(tmp_path, records))['validation'] == 'failed'


@pytest.mark.parametrize('name', ['source-probe/candidate-receipt-19.json','source-probe/candidate-resource.json',
    'acquisition/packages.txt','source-probe/vendor-files.json','test-diagnostics/fixture-1/pytest.xml'])
def test_missing_evidence_is_not_reconstructed(tmp_path, records, name):
    del records[name]
    assert verify(archive(tmp_path, records))['validation'] == 'failed'


@pytest.mark.parametrize('kind', ['duplicate-attempt','wrong-input','bad-tool','fake-firmware','cleanup','native-cleanup',
    'partial','synthetic','bool-observation','cancel-as-success','fault-real-mode','success-infra','success-error',
    'accounting','signature','package','manifest'])
def test_contradictory_evidence_is_rejected(tmp_path, records, kind):
    name = 'source-probe/candidate-receipt-01.json'
    if kind=='duplicate-attempt':
        change(records,'source-probe/candidate-receipt-02.json',lambda r:r['runtime'].update(attempt_id=f'{1:032x}'))
    elif kind=='wrong-input': change(records,name,lambda r:r['runtime'].update(inputs=[0,0]))
    elif kind=='bad-tool': change(records,name,lambda r:r['runtime']['tools']['identities']['qemu'].update(sha256='0'*64))
    elif kind=='fake-firmware': change(records,name,lambda r:r['runtime']['firmware'].update(sha256='0'*64))
    elif kind=='cleanup': change(records,name,lambda r:r['runtime']['cleanup'].update(success=False))
    elif kind=='native-cleanup': change(records,name,lambda r:r['runtime']['cleanup']['processes'][0]['windows_identity'].update(terminated=False))
    elif kind=='partial': change(records,name,lambda r:r['runtime'].update(completion_reached=False))
    elif kind=='synthetic': change(records,name,lambda r:r['runtime'].update(measurement_mode='synthetic_test'))
    elif kind=='bool-observation': change(records,name,lambda r:r['runtime']['observation'].update(observed_value=True))
    elif kind=='cancel-as-success': change(records,'source-probe/candidate-receipt-19.json',lambda r:r['runtime'].update(classification='completed'))
    elif kind=='fault-real-mode': change(records,'source-probe/candidate-receipt-19.json',lambda r:r['runtime'].update(measurement_mode='real_firmware'))
    elif kind=='success-infra': change(records,name,lambda r:r['runtime'].update(classification='infrastructure_failure'))
    elif kind=='success-error': change(records,name,lambda r:r['runtime'].update(error_category='timeout'))
    elif kind=='accounting': change(records,'source-probe/candidate-report.json',lambda r:r['cases'][-1]['accounting'].update(attempted_executions=0))
    elif kind=='signature': records['acquisition/signature-policy.txt']=b'PackageOptional PackageTrustedOnly'
    elif kind=='package': records['acquisition/packages.txt']=records['acquisition/packages.txt'].replace(b'11.1.3-1',b'11.1.4-1')
    else: records['source-probe/vendor-files.json'] += b' '
    assert verify(archive(tmp_path, records))['validation'] == 'failed'


@pytest.mark.parametrize('kind', ['failure','skip-critical','summary','doctype','utf16-doctype','utf32-doctype','wrong-module','duplicate','malformed'])
def test_junit_is_verified_not_inferred_from_a_green_job(tmp_path, records, kind):
    name='test-diagnostics/fixture-2/pytest.xml'; data=records[name]
    if kind=='failure': data=data.replace(b'/>',b'><failure>fixture</failure></testcase>',1)
    elif kind=='skip-critical': data=data.replace(b'/>',b'><skipped/></testcase>',1).replace(b'skipped="0"',b'skipped="1"')
    elif kind=='summary': data=data.replace(b'tests="2"',b'tests="999"')
    elif kind=='doctype': data=b'<!DOCTYPE foo [<!ENTITY x "bad">]>'+data
    elif kind in {'utf16-doctype','utf32-doctype'}:
        data=('<!DOCTYPE foo [<!ENTITY x "bad">]>'+data.decode()).encode('utf-16' if kind=='utf16-doctype' else 'utf-32')
    elif kind=='wrong-module': data=data.replace(b'tests.product.test_windows_runtime_candidate',b'unrelated.fixture')
    elif kind=='duplicate': records['test-diagnostics/fixture-1/pytest.xml']=data
    else: data=b'not xml'
    records[name]=data
    assert verify(archive(tmp_path, records))['validation'] == 'failed'


@pytest.mark.parametrize('name', ['../escape','/absolute','C:/drive','source-probe/../escape','source-probe\\escape',
    'source-probe/./same','evidence/forbidden','source-probe/control\nname'])
def test_archive_paths_are_rejected_without_extraction(tmp_path, records, name):
    result=verify(archive(tmp_path,records,[(name,b'never extracted')]))
    assert result['validation']=='failed' and result['failures'][0]['code'] in {'unsafe_member_name','unexpected_archive_root'}


def test_archive_symlinks_and_duplicates_are_rejected(tmp_path, records):
    link=zipfile.ZipInfo('source-probe/link'); link.create_system=3
    link.external_attr=(stat.S_IFLNK|0o777)<<16
    assert verify(archive(tmp_path,records,[(link,b'/outside')]))['failures'][0]['code']=='nonregular_archive_member'
    with pytest.warns(UserWarning): path=archive(tmp_path,records,[('source-probe/candidate-report.json',b'{}')])
    assert verify(path)['failures'][0]['code']=='duplicate_archive_member'


def test_duplicate_json_and_nonfinite_are_rejected(tmp_path, records):
    records['source-probe/candidate-report.json']=b'{"candidate_only":true,"candidate_only":true}'
    assert verify(archive(tmp_path,records))['failures'][0]['code']=='duplicate_json_field'
    records['source-probe/candidate-report.json']=b'{"value":NaN}'
    assert verify(archive(tmp_path,records))['failures'][0]['code']=='nonfinite_json'
    records['source-probe/candidate-report.json']=b'{"value":1e999}'
    assert verify(archive(tmp_path,records))['failures'][0]['code']=='nonfinite_json'


def test_additional_product_junit_is_reported_without_profile_promotion(tmp_path, records):
    records['test-diagnostics/product-source/pytest.xml'] = b'<testsuite tests="1" failures="0" errors="0" skipped="0"><testcase classname="product.paths" name="rejection"/></testsuite>'
    records['test-diagnostics/product-frozen/pytest.xml'] = records['test-diagnostics/product-source/pytest.xml']
    result = verify(archive(tmp_path, records))
    assert result['validation'] == 'passed', result
    assert result['junit']['selections'] == 5 and result['junit']['passed'] == 19
    assert result['additional_product_records_reviewed'] is False and result['production_qualified'] is False


@pytest.mark.parametrize('bound', ['MAX_ARCHIVE','MAX_MEMBER','MAX_MEMBERS'])
def test_archive_resource_bounds(tmp_path, records, monkeypatch, bound):
    path=archive(tmp_path,records)
    monkeypatch.setattr(evidence,bound,1)
    assert verify(path)['validation']=='failed'


def test_corrupt_compressed_member_returns_failed_report(tmp_path, records):
    path = archive(tmp_path, records)
    data = bytearray(path.read_bytes())
    with zipfile.ZipFile(path) as source:
        first = source.infolist()[0]
    filename, extra = struct.unpack_from('<HH', data, first.header_offset + 26)
    body = first.header_offset + 30 + filename + extra
    data[body] ^= 0xff
    path.write_bytes(data)
    assert verify(path)['validation'] == 'failed'


def test_self_consistent_unapproved_image_is_rejected(tmp_path, records):
    image = b'\x7fELFsubstituted synthetic image'
    digest = hashlib.sha256(image).hexdigest()
    records['source-probe/example/example.elf'] = image
    change(records, 'source-probe/example/image-provenance.json', lambda r:r.update(image_sha256=digest))
    for i in range(1, 20):
        def replace(value):
            value['runtime']['firmware'].update(sha256=digest, size_bytes=len(image))
            value['runtime']['firmware_validation']['firmware_sha256'] = digest
        change(records, f'source-probe/candidate-receipt-{i:02}.json', replace)
    assert verify(archive(tmp_path, records))['failures'][0]['code'] == 'firmware_identity_mismatch'


def test_real_trusted_manifest_identity_matches_bundled_payload():
    import base64
    data = evidence.files('firmavex.product').joinpath('resources/example/image.json').read_bytes()
    manifest = json.loads(data)
    assert evidence._bundled_image_identity() == {
        'image_sha256': hashlib.sha256(base64.b64decode(manifest['image_base64'], validate=True)).hexdigest(),
        'manifest_sha256': hashlib.sha256(data).hexdigest()}


def test_cli_failure_is_nonzero_and_does_not_expose_raw_payload(tmp_path, records):
    path=archive(tmp_path,records)
    result=subprocess.run([sys.executable,'-m','tools.windows_candidate_evidence',str(path),
        '--sha256','0'*64,'--revision',REVISION,'--run-id',RUN],
        cwd=Path(__file__).resolve().parents[2],capture_output=True,text=True,timeout=20)
    assert result.returncode==1
    report=json.loads(result.stdout)
    assert report['production_qualified'] is False and report['failures']==[{'code':'archive_digest_mismatch'}]
