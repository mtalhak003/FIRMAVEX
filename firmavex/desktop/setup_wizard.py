"""First-user setup. Host capability checks never masquerade as guest execution."""
from pathlib import Path
import json

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (QWizard, QWizardPage, QVBoxLayout, QLabel,
                              QPushButton, QCheckBox, QComboBox)

from firmavex.product.runtime_pack import host


class RuntimePage(QWizardPage):
    def __init__(self, wizard):
        super().__init__()
        self._setup = wizard
        self.setTitle('2. Check or install the execution runtime')
        layout = QVBoxLayout(self)
        self.status = QLabel('Check QEMU and ARM-capable GDB. Firmware is not executed by setup checks.')
        self.status.setWordWrap(True)
        self.status.setAccessibleName('Runtime readiness and setup progress')
        layout.addWidget(self.status)
        self.check = QPushButton('Check existing runtime')
        self.check.clicked.connect(wizard.check)
        layout.addWidget(self.check)
        self.consent = QCheckBox('Download MSYS2 from its publisher and use signed vendor packages. Retain license notices and preserve my projects/results.')
        self.consent.setAccessibleName('Authorize vendor runtime installation')
        self.consent.setToolTip('No vendor binaries are hosted by FIRMAVEX. The bootstrap has a pinned SHA-256; package signatures remain required.')
        layout.addWidget(self.consent)
        self.install = QPushButton('Install / repair runtime automatically')
        self.install.setEnabled(False)
        self.install.clicked.connect(wizard.install)
        layout.addWidget(self.install)
        self.consent.toggled.connect(wizard.refresh)
        self.offline = QPushButton('Import a trusted offline runtime pack…')
        self.offline.clicked.connect(wizard.main_window.install_runtime_pack)
        layout.addWidget(self.offline)
        self.history = QPushButton('Inspect installed generations')
        self.history.clicked.connect(wizard.history)
        layout.addWidget(self.history)
        self.generations = QComboBox()
        self.generations.setAccessibleName('Verified historical runtime generation')
        layout.addWidget(self.generations)
        self.restore = QPushButton('Roll back to selected verified runtime')
        self.restore.setEnabled(False)
        self.restore.clicked.connect(wizard.restore)
        layout.addWidget(self.restore)
        if host() != {'os': 'windows', 'arch': 'x86_64'}:
            self.consent.setEnabled(False)
            self.install.setToolTip('Automatic vendor installation is not qualified on this platform. Existing tools and verified offline packs remain supported.')
        layout.addStretch()

    def isComplete(self):
        return self._setup.ready and not self._setup.main_window.busy


class SetupWizard(QWizard):
    def __init__(self, window):
        super().__init__(window)
        self.main_window = window
        self.ready = False
        self.pending_check = False
        self.pending_reject = False
        self.setWindowTitle('FIRMAVEX first-launch setup')
        self.setMinimumSize(680, 520)
        self.setOption(QWizard.NoBackButtonOnStartPage)
        intro = QWizardPage()
        intro.setTitle('1. Understand firmware compatibility')
        layout = QVBoxLayout(intro)
        text = QLabel('FIRMAVEX tests compatible symbolized Cortex-M3 ELF firmware on QEMU mps2-an385.\n\nRaw BIN, arbitrary boards/peripherals and physical hardware are not supported.\n\nThe built-in example requires no compiler or Python commands. Setup does not run guest firmware; you explicitly start testing after creating a project.\n\nCurrent installers are unsigned/unnotarized development candidates.')
        text.setWordWrap(True)
        text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(text)
        self.addPage(intro)
        self.runtime = RuntimePage(self)
        self.addPage(self.runtime)
        final = QWizardPage()
        final.setTitle('3. Create a compiler-free example project')
        layout = QVBoxLayout(final)
        label = QLabel('Finish to open a verified example project. Then choose Start testing.\n\nAfter the configured condition is observed, reproduce the exact input and export its report. Results stay in your user-owned project directory.\n\nA completed test does not establish hardware validation or prove firmware safe.')
        label.setWordWrap(True)
        layout.addWidget(label)
        self.example = QCheckBox('Create the verified built-in example project')
        self.example.setChecked(True)
        layout.addWidget(self.example)
        self.addPage(final)
        window.controller.result.connect(self._runtime_result)
        window.controller.error.connect(self._runtime_error)
        window.controller.event.connect(self._runtime_event)
        window.controller.busy_changed.connect(self.refresh)
        window.controller.idle.connect(self.idle)
        self.currentIdChanged.connect(self.refresh)
        self.setButtonText(QWizard.FinishButton, 'Finish setup')
        self.refresh()

    @Slot()
    @Slot(bool)
    @Slot(int)
    def refresh(self, unused=None):
        idle = not self.main_window.busy
        self.runtime.check.setEnabled(idle)
        self.runtime.offline.setEnabled(idle)
        self.runtime.history.setEnabled(idle)
        self.runtime.restore.setEnabled(idle and self.runtime.generations.count() > 0)
        self.runtime.install.setEnabled(idle and self.runtime.consent.isChecked() and host() == {'os': 'windows', 'arch': 'x86_64'})
        self.runtime.completeChanged.emit()

    @Slot()
    def check(self):
        self.ready = False
        self.runtime.status.setText('Checking actual tool capabilities…')
        self.main_window.check_tools()
        self.refresh()

    @Slot()
    def install(self):
        if self.main_window.busy or not self.runtime.consent.isChecked() or host() != {'os': 'windows', 'arch': 'x86_64'}:
            return
        self.ready = False
        self.runtime.status.setText('Installing into private per-user storage; existing projects and runtime generations are retained.')
        self.main_window._start('setup_runtime', {})

    @Slot()
    def history(self):
        self.main_window._start('runtime_history', {})

    @Slot()
    def restore(self):
        generation = self.runtime.generations.currentData()
        if generation:
            self.ready = False
            self.main_window._start('rollback_runtime', {'generation': generation})

    @Slot(dict)
    def _runtime_result(self, result):
        command = self.main_window._job
        if command == 'doctor':
            self.ready = result.get('success') is True and result.get('native_execution') != 'unsupported'
            self.runtime.status.setText('Runtime capabilities passed. Guest execution will be verified separately.' if self.ready else 'This runtime is not admitted on the current platform.')
        elif command in {'setup_runtime', 'rollback_runtime'}:
            self.pending_check = True
            self.runtime.status.setText('Runtime activation completed. Checking selected tools next…')
        elif command == 'runtime_history':
            self.runtime.generations.clear()
            errors = []
            for row in result.get('generations', []):
                if row.get('integrity') == 'verified':
                    self.runtime.generations.addItem(row.get('pack_id', '') + (' (active)' if row.get('active') else '') + ' — ' + row['generation'][:8], row['generation'])
                else:
                    errors.append(row.get('error', 'Invalid runtime record'))
            self.runtime.status.setText('Verified generations listed. ' + ('Integrity failures: ' + '; '.join(errors) if errors else 'Projects/results are not removed by rollback.'))
        self.refresh()

    @Slot(dict)
    def _runtime_error(self, error):
        self.ready = False
        category = error.get('category', 'setup_error')
        message = error.get('message', 'Setup failed.')
        hints = {'missing_dependency': 'Use automatic installation on Windows or import a trusted offline pack.',
                 'unsupported_platform': 'This runtime build needs native qualification; do not bypass its gate.',
                 'runtime_integrity_failure': 'The download was rejected. No unverified program was executed.',
                 'runtime_provider_unavailable': 'This platform does not yet have a qualified automatic provider.'}
        self.runtime.status.setText(category.replace('_', ' ').capitalize() + ': ' + message + '\n' + hints.get(category, 'The diagnostic details remain available in the main window.'))
        self.refresh()

    @Slot(dict)
    def _runtime_event(self, event):
        payload = event.get('payload', {})
        if payload.get('type') == 'runtime_setup':
            self.runtime.status.setText(payload.get('message', payload.get('stage', 'Runtime setup')))

    @Slot()
    def idle(self):
        if self.pending_reject:
            self.pending_reject = False
            super().reject()
            return
        if self.pending_check:
            self.pending_check = False
            self.check()
        self.refresh()

    def accept(self):
        if not self.ready or self.main_window.busy:
            return
        from firmavex.product.runtime_pack import _atomic_json
        try:
            self.main_window.data_root.mkdir(parents=True, exist_ok=True)
            _atomic_json(self.main_window.data_root / 'first-launch.json', {'schema_version': 1, 'setup_reviewed': True, 'firmware_executed': False})
        except OSError as exc:
            self.runtime.status.setText('Cannot save setup preferences: ' + str(exc))
            return
        super().accept()
        if self.example.isChecked():
            self.main_window.prepare_builtin_example()

    def reject(self):
        if self.main_window.controller.busy:
            self.pending_reject = True
            self.main_window.controller.cancel()
            self.runtime.status.setText('Cancelling setup and waiting for owned process cleanup…')
            return
        super().reject()
