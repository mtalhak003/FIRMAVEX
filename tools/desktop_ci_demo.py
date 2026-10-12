"""Run the existing CLI demo, preserving exit status and exposing CI errors."""
import argparse
from contextlib import redirect_stdout
import io
import json

from firmavex.product.cli import main as cli


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', required=True)
    args = parser.parse_args(argv)
    output = io.StringIO()
    with redirect_stdout(output):
        status = cli(['demo', '--output-dir', args.output_dir])
    text = output.getvalue()
    print(text, end='')
    if status:
        try:
            result = json.loads(text.splitlines()[-1])
            message = json.dumps(result.get('error', result), sort_keys=True)[-6000:]
        except (ValueError, IndexError):
            message = text[-6000:]
        message = message.replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')
        print('::error title=Native supervised demonstration failure::' + message)
    return status


if __name__ == '__main__':
    raise SystemExit(main())
