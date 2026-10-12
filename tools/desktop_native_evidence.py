"""Read-only CI qualification summary, without raw debugger diagnostics."""
import argparse
import json
from pathlib import Path
import platform
import sqlite3

from firmavex.product.services import inspect_run


def capture(root):
    attempts = []
    results = {}
    for name, count in [('search', 10), ('reproduction', 3)]:
        directory = Path(root) / name
        inspected = inspect_run(directory)
        if inspected.get('success') is False:
            raise ValueError('Archive inspection failed.')
        result = json.loads((directory / 'result.json').read_text(encoding='utf-8'))
        if result['measurement_mode'] != 'real_firmware' or result['triggering_input'] != [2, 1] or result['accounting']['attempted_executions'] != count or result['accounting']['infrastructure_failures'] != 0:
            raise ValueError('Unexpected actual firmware outcome/accounting.')
        connection = sqlite3.connect('file:' + str(directory / 'run.sqlite3') + '?mode=ro', uri=True)
        try:
            records = [json.loads(row[0]) for row in connection.execute('select record from attempts order by sequence')]
        finally:
            connection.close()
        if len(records) != count:
            raise ValueError('Missing execution receipts.')
        for record in records:
            evidence = record['evidence']
            if evidence['measurement_mode'] != 'real_firmware' or not all(evidence[key] is True for key in ['guest_dispatched', 'input_injected', 'completion_reached', 'cleanup_verified']):
                raise ValueError('Receipt does not establish real completion/cleanup.')
            attempts.append(evidence)
        results[name] = {'outcome': result['outcome'], 'attempted_executions': count}
    return {'schema_version': 1, 'kind': 'firmavex_native_example_qualification',
            'host': {'os': platform.system(), 'architecture': platform.machine()},
            'results': results, 'real_receipts': len(attempts),
            'tools': attempts[0]['tools'], 'firmware': attempts[0]['firmware'],
            'scope': 'Independent example only; not arbitrary firmware/platform qualification.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    summary = capture(args.directory)
    print('::notice title=Native firmware qualification::' + json.dumps(summary, sort_keys=True))
