"""Publish bounded native tool capability evidence, not firmware qualification."""
import json
import platform

from firmavex.product.errors import ProductError
from firmavex.product.tools import discover


def main():
    try:
        result = {'host': {'os': platform.system(), 'architecture': platform.machine()},
                  'tools': discover(require_compiler=True).to_dict(),
                  'firmware_qualification': 'not_established_by_capability_probe'}
    except ProductError as error:
        # These are trusted host tool probes, not private firmware diagnostics.
        message = json.dumps(error.to_dict(), sort_keys=True)[-3500:]
        message = message.replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')
        print('::error title=Native runtime capability failure::' + message)
        return 1
    print('::notice title=Native runtime tool identities::' + json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
