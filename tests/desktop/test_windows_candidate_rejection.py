"""Native candidate GUI admission checks, not positive firmware qualification."""
import json
import os
from pathlib import Path
import sys

import pytest


def test_native_windows_candidate_gui_rejection(qtbot):
    if os.environ.get('FIRMAVEX_RUN_WINDOWS_CANDIDATE') != '1':
        pytest.skip('Explicit native Windows candidate workflow required')
    if sys.platform != 'win32': pytest.fail('GUI candidate qualification requires native Windows')
    from firmavex.desktop.projects import DesktopProject
    from firmavex.desktop.window import MainWindow
    from firmavex.product.config import load_config
    from tools import windows_candidate_product as product
    context, _, evidence, tools = product.prepared_context(
        Path(os.environ['FIRMAVEX_CANDIDATE_VENDOR']),
        Path(os.environ['FIRMAVEX_CANDIDATE_ROOT'])/'source-probe')
    directory = evidence/'product-gui'; directory.mkdir(exist_ok=False)
    config = load_config(product.prepare_project(directory, tools))
    project = DesktopProject.create(directory/'project', config.firmware, config)
    window = MainWindow(data_root=directory/'application-data')
    qtbot.addWidget(window); window.show()
    try:
        window.open_project(project.root)
        qtbot.waitUntil(lambda: window.project is not None and not window.busy, timeout=15000)
        window.start_run()
        qtbot.waitUntil(lambda: not window.busy and 'unsupported_platform' in window.status_label.text(), timeout=60000)
        rejected = product.rejection_details(json.loads(window.validation_text.toPlainText()))
        assert window.result_record is None and not window.reproduce_button.isEnabled()
        assert window.attempts_table.rowCount() == 0
        assert 'Charged attempts: 0' in window.accounting_label.text()
        assert not list((project.root/'runs').rglob('*.sqlite*'))
        assert not list((project.root/'runs').rglob('result.json'))
        product.candidate._save(directory/'gui-admission.json', {
            **context, 'schema_version': 1, 'kind': 'firmavex_candidate_gui_admission',
            'candidate_only': True, 'production_qualified': False,
            'status': 'candidate_gui_admission_rejection_passed', 'firmware_execution': 'not_admitted',
            'charged_attempts': 0, 'scope': 'native GUI rejection only; no positive execution qualification',
            'rejection': rejected, 'worker_idle_after_cleanup': not window.controller.busy})
    finally:
        if window.busy:
            window.controller.cancel()
            qtbot.waitUntil(lambda: not window.busy, timeout=20000)
        window.close()
