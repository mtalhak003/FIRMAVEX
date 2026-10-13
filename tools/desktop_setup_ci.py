"""Native Windows qualification of the actual publisher-install path (no mocks)."""
import json
import sys
from firmavex.product.runtime_setup import install_vendor_runtime
from firmavex.product.runtime_pack import generation_history, runtime_root, rollback
from firmavex.product.tools import discover


def main():
    try:
        result = install_vendor_runtime(event_callback=lambda row: print(json.dumps(row), flush=True))
        tools = discover()
        rows = generation_history()
        assert len(rows) == 1 and rows[0]['integrity'] == 'verified'
        assert tools.compiler is None
        restored = rollback(result['generation'])
        assert restored['success']
        print('::notice title=Actual Windows runtime installation::' + json.dumps({'runtime_root': str(runtime_root()), 'tools': tools.to_dict(), 'activation': result}, sort_keys=True))
        return 0
    except Exception as exc:
        text = (repr(exc) + ' ' + json.dumps(getattr(exc, 'details', {}), default=str))[-6000:]
        print('::error title=Actual vendor runtime installation failed::' + text.replace('%','%25').replace('\n','%0A').replace('\r','%0D'))
        return 1


if __name__ == '__main__':
    sys.exit(main())
