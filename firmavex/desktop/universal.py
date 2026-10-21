"""Capability-aware backend workspace, using only the supervised worker.

Saved jobs live in fresh directories outside the application. Opening this
window or reopening a record never runs a target. The original ARM project
editor remains available for its richer search configuration.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMainWindow, QPlainTextEdit, QProgressBar, QPushButton, QSpinBox,
    QSplitter, QTabWidget, QVBoxLayout, QWidget,
    QTableWidget, QTableWidgetItem, QAbstractItemView, QHeaderView,
)

from firmavex.backends.api import profiles, request_to_dict
from firmavex.product.errors import ProductError
from firmavex.product.presentation import summary, guidance
from .controller import DesktopController
from .diagnostics import arm_reproduction_summary, compiler_diagnostics
from .projects import _safe_root, application_data_directory
from .workflow import display_text, execution_request, result_context
from firmavex.product.run_review import outcome_category


_LABELS = {
    "cortex-m3-mps2": "ARM Cortex-M3 — bounded firmware search",
    "riscv32-virt": "RISC-V RV32 — one input-vector observation",
    "verilog-icarus": "Verilog / Icarus — testbench simulation",
}


def _preview(record: dict) -> str:
    text = json.dumps(record, indent=2, sort_keys=True, ensure_ascii=False)
    if len(text) > 65536:
        return text[:65536] + "\n[Display truncated; the complete record remains on disk.]"
    return text


class UniversalWindow(QMainWindow):
    """One owned worker at a time; no firmware or HDL runs in the Qt process."""

    arm_configuration_requested = Signal()
    runtime_setup_requested = Signal()

    def __init__(self, controller=None, *, data_root: Path | None = None, parent=None):
        super().__init__(parent)
        self.controller = controller or DesktopController(self)
        self.data_root = _safe_root(data_root or application_data_directory()) / "backend-workspace"
        self.active_run: Path | None = None
        self.record: dict | None = None
        self._job: str | None = None
        self._output: Path | None = None
        self._closing = False
        self._ready = False
        self._example_source: str | None = None
        self._comparison_left: str | None = None
        self._history_summaries = {}
        self.setWindowTitle("FIRMAVEX — processor and HDL backends")
        self.resize(1100, 760)
        self.setMinimumSize(760, 580)
        self._build()
        self.controller.event.connect(self._progress)
        self.controller.result.connect(self._result)
        self.controller.error.connect(self._error)
        self.controller.busy_changed.connect(self._refresh)
        self.controller.idle.connect(self._idle)
        self._profile_changed()
        self.refresh_history()

    @property
    def profile(self):
        return self.profile_combo.currentData()

    @property
    def busy(self):
        return self.controller.busy

    def _button(self, text, slot):
        button = QPushButton(text)
        button.clicked.connect(slot)
        return button

    def _build(self):
        body = QWidget()
        self.setCentralWidget(body)
        layout = QVBoxLayout(body)
        self.notice = QLabel(
            "Local emulation and HDL simulation • trusted projects only • no hardware validation. "
            "These backends are not a security sandbox. Do not import hostile or unknown projects."
        )
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)
        from firmavex.product.capabilities import describe
        policy = describe()['support']
        self.platform_notice = QLabel('macOS desktop preview only — native unified execution is unsupported.' if policy['native_unified_execution'] == 'unsupported' else 'Qualified baseline examples: Windows x64 / Ubuntu x64. Selected tools require separate readiness and qualification checks.')
        self.platform_notice.setWordWrap(True)
        layout.addWidget(self.platform_notice)
        form = QFormLayout()
        self.profile_combo = QComboBox()
        self.profile_combo.setAccessibleName("Backend and target")
        for profile, label in _LABELS.items():
            self.profile_combo.addItem(label, profile)
        self.profile_combo.currentIndexChanged.connect(self._profile_changed)
        form.addRow("Backend / target", self.profile_combo)
        self.capability_label = QLabel()
        self.capability_label.setWordWrap(True)
        form.addRow("Capabilities", self.capability_label)
        row = QWidget()
        source_layout = QHBoxLayout(row)
        source_layout.setContentsMargins(0, 0, 0, 0)
        self.source_edit = QLineEdit()
        self.source_edit.setAccessibleName("Project or input artifact path")
        self.source_edit.textChanged.connect(self._source_changed)
        self.browse_button = self._button("Browse…", self.pick_source)
        source_layout.addWidget(self.source_edit, 1)
        source_layout.addWidget(self.browse_button)
        self.source_label = QLabel("ARM project JSON")
        form.addRow(self.source_label, row)
        self.values_edit = QLineEdit("2, 1")
        self.values_edit.setAccessibleName("RV32 input vector")
        self.values_edit.textChanged.connect(self._refresh)
        self.values_label = QLabel("Two uint32 inputs (decimal or hex)")
        form.addRow(self.values_label, self.values_edit)
        self.timeout_spin = QDoubleSpinBox()
        self.timeout_spin.setRange(0.1, 3600)
        self.timeout_spin.setValue(10)
        self.timeout_spin.setSuffix(" s")
        self.timeout_spin.setAccessibleName("Execution wall-clock timeout")
        form.addRow("Wall-clock limit", self.timeout_spin)
        self.artifact_spin = QSpinBox()
        self.artifact_spin.setRange(1, 64)
        self.artifact_spin.setValue(16)
        self.artifact_spin.setSuffix(" MiB")
        form.addRow("Artifact byte limit", self.artifact_spin)
        self.trust_box = QCheckBox("I know and trust this project and its runtime tools; it is not hostile or unknown.")
        self.trust_box.setAccessibleName("Explicit trusted project acknowledgement")
        self.trust_box.toggled.connect(self._refresh)
        form.addRow(self.trust_box)
        layout.addLayout(form)
        actions = QHBoxLayout()
        self.check_button = self._button("Check runtime readiness", self.check_runtime)
        self.example_button = self._button("Prepare independent example", self.prepare_example)
        self.setup_button = self._button("Runtime setup / repair…", self.runtime_setup_requested.emit)
        self.arm_button = self._button("Open ARM search configuration", self.arm_configuration_requested.emit)
        self.run_button = self._button("Run selected method", self.execute)
        self.cancel_button = self._button("Cancel and clean up", self.cancel)
        for button in (self.check_button, self.setup_button, self.example_button, self.arm_button):
            actions.addWidget(button)
        layout.addLayout(actions)
        execution_actions = QHBoxLayout()
        execution_actions.addWidget(self.run_button)
        execution_actions.addWidget(self.cancel_button)
        layout.addLayout(execution_actions)
        self.workflow_hint = QLabel()
        self.workflow_hint.setTextFormat(Qt.TextFormat.PlainText)
        self.workflow_hint.setWordWrap(True)
        self.workflow_hint.setAccessibleName('Next workflow step')
        layout.addWidget(self.workflow_hint)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.progress_bar.setAccessibleName("Supervised job progress")
        layout.addWidget(self.progress_bar)
        split = QSplitter()
        history_panel = QWidget()
        history_layout = QVBoxLayout(history_panel)
        history_layout.addWidget(QLabel("Saved job history — reopen without execution"))
        self.history_filter = QLineEdit()
        self.history_filter.setPlaceholderText('Filter saved run names…')
        self.history_filter.setAccessibleName('Filter saved run history')
        self.history_filter.setMaxLength(128)
        self.history_filter.textChanged.connect(self._filter_history)
        history_layout.addWidget(self.history_filter)
        self.outcome_filter = QComboBox()
        self.outcome_filter.setAccessibleName('Filter history by last inspected recorded outcome')
        for title, category in [('All outcomes', 'all'), ('Recorded failure observed', 'observed_failure'),
                                ('Passed / no failure recorded', 'no_failure'), ('Failed / inconsistent', 'failed'),
                                ('Cancelled', 'cancelled'), ('Unknown / incomplete / not inspected', 'unknown')]:
            self.outcome_filter.addItem(title, category)
        self.outcome_filter.currentIndexChanged.connect(self._filter_history)
        history_layout.addWidget(self.outcome_filter)
        self.history = QListWidget()
        self.history.setAccessibleName("Persistent backend job history")
        self.history.itemDoubleClicked.connect(self.open_history_item)
        self.history.itemSelectionChanged.connect(self._refresh)
        history_layout.addWidget(self.history)
        self.history_hint = QLabel()
        self.history_hint.setWordWrap(True)
        history_layout.addWidget(self.history_hint)
        history_actions = QHBoxLayout()
        self.history_refresh_button = self._button("Refresh", self.refresh_history)
        self.open_button = self._button("Open saved run…", self.pick_run)
        self.open_selected_button = self._button('Open selected', self.open_selected_history)
        history_actions.addWidget(self.open_selected_button)
        history_actions.addWidget(self.history_refresh_button)
        history_actions.addWidget(self.open_button)
        history_layout.addLayout(history_actions)
        review_actions = QHBoxLayout()
        self.history_summary_button = self._button('Inspect summaries (up to 50)', self.inspect_history_summaries)
        self.pin_button = self._button('Set left run', self.pin_comparison)
        self.compare_button = self._button('Compare with left', self.compare_selected)
        for button in (self.history_summary_button, self.pin_button, self.compare_button):
            review_actions.addWidget(button)
        history_layout.addLayout(review_actions)
        verification_actions = QHBoxLayout()
        self.verify_button = self._button('Verify selected evidence', self.verify_selected)
        self.verify_folder_button = self._button('Verify folder…', self.verify_folder)
        verification_actions.addWidget(self.verify_button)
        verification_actions.addWidget(self.verify_folder_button)
        history_layout.addLayout(verification_actions)
        self.comparison_hint = QLabel('Select two different saved runs: mark the left, then select the right. Comparison never executes them.')
        self.comparison_hint.setTextFormat(Qt.TextFormat.PlainText)
        self.comparison_hint.setWordWrap(True)
        history_layout.addWidget(self.comparison_hint)
        folder_actions = QHBoxLayout()
        self.left_folder_button = self._button('Choose left folder…', self.pick_comparison_left)
        self.right_folder_button = self._button('Compare folder…', self.pick_comparison_right)
        folder_actions.addWidget(self.left_folder_button)
        folder_actions.addWidget(self.right_folder_button)
        history_layout.addLayout(folder_actions)
        split.addWidget(history_panel)
        self.tabs = QTabWidget()
        self.result_context_label = QLabel('No saved result selected. Opening history never executes a target.')
        self.result_context_label.setTextFormat(Qt.TextFormat.PlainText)
        self.result_context_label.setWordWrap(True)
        self.result_context_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.result_context_label)
        self.result_view = QPlainTextEdit()
        self.result_view.setReadOnly(True)
        self.result_view.setAccessibleName("Backend result and execution evidence")
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(1000)
        self.log_view.setAccessibleName("Live worker progress and diagnostics")
        self.summary_view = QPlainTextEdit()
        self.summary_view.setReadOnly(True)
        self.summary_view.setAccessibleName("Readable result explanation and limitations")
        self.tabs.addTab(self.summary_view, "Summary")
        self.tabs.addTab(self.result_view, "Result / evidence")
        self.tabs.addTab(self.log_view, "Progress / logs")
        self.operation_view = QPlainTextEdit()
        self.operation_view.setReadOnly(True)
        self.operation_view.setAccessibleName('Runtime, preparation and export details')
        self.operation_view.setPlaceholderText('Runtime checks, example preparation and export details appear here.')
        self.tabs.addTab(self.operation_view, 'Operation details')
        comparison_panel = QWidget()
        comparison_layout = QVBoxLayout(comparison_panel)
        self.comparison_scope = QLabel('Choose two saved backend or standalone ARM run folders. Comparison never executes them.')
        self.comparison_scope.setTextFormat(Qt.TextFormat.PlainText)
        self.comparison_scope.setWordWrap(True)
        comparison_layout.addWidget(self.comparison_scope)
        self.comparison_view = QTableWidget(0, 4)
        self.comparison_view.setHorizontalHeaderLabels(['Field', 'Left run', 'Right run', 'Comparison'])
        self.comparison_view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.comparison_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.comparison_view.verticalHeader().hide()
        self.comparison_view.setWordWrap(True)
        self.comparison_view.setAccessibleName('Read-only saved-run comparison')
        comparison_layout.addWidget(self.comparison_view)
        self.comparison_panel = comparison_panel
        self.tabs.addTab(comparison_panel, 'Compare saved runs')
        self.verification_panel = QWidget()
        verification_layout = QVBoxLayout(self.verification_panel)
        self.verification_target = QLabel('No verification folder selected')
        self.verification_target.setTextFormat(Qt.TextFormat.PlainText)
        self.verification_target.setWordWrap(True)
        verification_layout.addWidget(self.verification_target)
        self.verification_label = QLabel('Select a run or choose a folder to check its supported artifacts without execution. Hash matches are not authenticity or execution proof.')
        self.verification_label.setTextFormat(Qt.TextFormat.PlainText)
        self.verification_label.setWordWrap(True)
        verification_layout.addWidget(self.verification_label)
        self.verification_progress = QProgressBar()
        self.verification_progress.setRange(0, 1)
        self.verification_progress.setValue(0)
        self.verification_progress.setTextVisible(False)
        self.verification_progress.setAccessibleName('Artifact verification progress')
        verification_layout.addWidget(self.verification_progress)
        self.verification_table = QTableWidget(0, 2)
        self.verification_table.setHorizontalHeaderLabels(['Artifact', 'Check outcome'])
        self.verification_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.verification_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.verification_table.setAccessibleName('Per-artifact evidence verification results')
        verification_layout.addWidget(self.verification_table)
        self.tabs.addTab(self.verification_panel, 'Verify evidence')
        self.summary_view.setPlaceholderText('Prepare a trusted example or open a saved run to review its outcome here.')
        split.addWidget(self.tabs)
        split.setStretchFactor(1, 2)
        layout.addWidget(split, 1)
        exports = QHBoxLayout()
        self.reproduce_button = self._button("Reproduce saved observation", self.reproduce)
        self.export_button = self._button("Export report, logs and waveforms…", self.export)
        exports.addWidget(self.reproduce_button)
        exports.addWidget(self.export_button)
        layout.addLayout(exports)
        self.status_label = QLabel("Ready. Runtime checking and example preparation do not execute a target.")
        self.status_label.setTextFormat(Qt.TextFormat.PlainText)
        self.status_label.setWordWrap(True)
        self.statusBar().addWidget(self.status_label, 1)

    @Slot()
    def _profile_changed(self):
        self._ready = False
        self._example_source = None
        self.trust_box.setChecked(False)
        profile = profiles[self.profile]
        self.capability_label.setText(
            f"{profile.architecture}; method: {', '.join(profile.capabilities.methods)}; "
            f"input: {profile.capabilities.input_kind}; "
            f"waveforms: {'yes' if profile.capabilities.waveforms else 'no'}. "
            "Runtime availability is checked separately from native qualification. "
            + ({"cortex-m3-mps2": "QEMU mps2-an385; symbolized Cortex-M3 ELF and ready/completion bindings required.",
                "riscv32-virt": "QEMU virt; RV32IM ELF with the documented two-input symbol contract required.",
                "verilog-icarus": "One self-contained ASCII testbench; no synthesis, VHDL or physical FPGA support."}[self.profile])
        )
        self.source_label.setText({"cortex-m3-mps2": "Existing ARM project JSON", "riscv32-virt": "Compatible RV32 ELF", "verilog-icarus": "Self-contained Verilog testbench"}[self.profile])
        self.values_edit.setVisible(self.profile == "riscv32-virt")
        self.values_label.setVisible(self.profile == "riscv32-virt")
        self.arm_button.setVisible(self.profile == "cortex-m3-mps2")
        self.timeout_spin.setEnabled(self.profile != "cortex-m3-mps2")
        self.artifact_spin.setEnabled(self.profile != "cortex-m3-mps2")
        self.source_edit.clear()
        self._refresh()

    @Slot(str)
    def _source_changed(self, text):
        if self._example_source != text:
            self._example_source = None
            self.trust_box.setChecked(False)
        self._refresh()

    def _fresh(self, category):
        root = self.data_root / category
        root.mkdir(parents=True, exist_ok=True)
        return root / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:12])

    def _start(self, command, payload, *, output=None):
        if self.busy or self._closing:
            return False
        self._job, self._output = command, output
        if command == 'backend_verify':
            self.verification_table.setRowCount(0)
            self.verification_target.setText('Verification folder: ' + display_text(payload.get('run_dir', 'unavailable'), 500))
            self.verification_label.setText('Inspecting archive; artifact count is not known yet. Cancel stops verification without changing saved files.')
            self.verification_progress.setRange(0, 0)
            self.verification_progress.setTextVisible(False)
            self.tabs.setCurrentWidget(self.verification_panel)
        if command == 'backend_compare':
            self.comparison_view.setRowCount(0)
            self.comparison_scope.setText('Comparison in progress. Previous values cleared; cancellation does not produce a comparison.')
        if command in {'backend_execute', 'backend_reproduce', 'backend_inspect'}:
            self.summary_view.clear()
            self.result_view.clear()
            self.result_context_label.setText('Waiting for a validated result; no saved outcome is displayed.')
        if command in {"backend_execute", "backend_reproduce"}:
            self.active_run, self.record = output, None
            self.result_view.clear()
        if command != 'backend_verify':
            self.log_view.clear()
        self.status_label.setText("Running supervised job; waiting for confirmed completion and cleanup…")
        if not self.controller.start(command, payload):
            self._job = None
            self._refresh()
            return False
        return True

    @Slot()
    def check_runtime(self):
        self._ready = False
        self._start("backend_check", {"profile": self.profile})

    @Slot()
    def prepare_example(self):
        if self.busy:
            return
        try:
            output = self._fresh("examples")
            self._start("backend_prepare", {"profile": self.profile, "output_dir": str(output)}, output=output)
        except (ValueError, OSError, ProductError) as exc:
            self._local_error(exc)

    @Slot()
    def execute(self):
        if self.busy:
            return
        try:
            if not self._ready:
                raise ValueError("Check runtime readiness first; probes do not establish native qualification.")
            trust = self._trust()
            request = self._request()
            output = self._fresh("runs")
            self._start("backend_execute", {"request": request_to_dict(request), "output_dir": str(output), "trust": trust}, output=output)
        except (ValueError, OSError, ProductError) as exc:
            self._local_error(exc)

    def _trust(self):
        if not self.trust_box.isChecked():
            raise ValueError("Unknown or untrusted workloads are rejected. Explicitly acknowledge a trusted project.")
        return "trusted_example" if self._example_source == self.source_edit.text() else "trusted_project"

    def _request(self):
        return execution_request(self.profile, self.source_edit.text(), self.values_edit.text(),
                                 self.timeout_spin.value(), self.artifact_spin.value())

    @Slot()
    def cancel(self):
        if self.controller.cancel():
            self.status_label.setText('Cancellation requested; waiting for file checks to stop and worker cleanup. Saved evidence stays unchanged.' if self._job == 'backend_verify' else "Cancellation requested; waiting for persistence and process-tree cleanup…")
            self.cancel_button.setEnabled(False)

    @Slot()
    def pick_source(self):
        filters = {"cortex-m3-mps2": "ARM project (*.json)", "riscv32-virt": "RV32 ELF (*.elf)", "verilog-icarus": "Verilog testbench (*.v *.sv)"}
        path, _ = QFileDialog.getOpenFileName(self, "Select trusted project input", "", filters[self.profile])
        if path:
            self.source_edit.setText(path)

    @Slot()
    def pick_run(self):
        directory = QFileDialog.getExistingDirectory(self, "Open saved backend run without executing it")
        if directory:
            self.inspect(Path(directory))

    def inspect(self, directory):
        if self._start("backend_inspect", {"run_dir": str(directory)}):
            self.active_run = Path(directory)
            self.record = None
            self._example_source = None
            self.trust_box.setChecked(False)

    @Slot(QListWidgetItem)
    def open_history_item(self, item):
        if item is not None and not item.isHidden():
            self.inspect(Path(item.data(Qt.ItemDataRole.UserRole)))

    @Slot()
    def open_selected_history(self):
        self.open_history_item(self.history.currentItem())

    def inspect_history_summaries(self):
        paths = [self.history.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.history.count())
                 if self.history_filter.text().casefold() in Path(self.history.item(i).data(Qt.ItemDataRole.UserRole)).name.casefold()][:50]
        if paths:
            self._start('backend_history', {'run_dirs': paths})

    def pin_comparison(self):
        item = self.history.currentItem()
        if not self.busy and item is not None and not item.isHidden():
            self._comparison_left = item.data(Qt.ItemDataRole.UserRole)
            self.comparison_hint.setText('Left run: ' + display_text(self._comparison_left, 200) + '. Select a different right run, then Compare. Both are re-inspected.')
            self._refresh()

    def pick_comparison_left(self):
        if self.busy:
            return
        folder = QFileDialog.getExistingDirectory(self, 'Choose left saved backend or standalone ARM run')
        if folder:
            self._comparison_left = folder
            self.comparison_hint.setText('Left run: ' + display_text(folder, 200) + '. Choose another folder or select a right run.')
            self._refresh()

    def pick_comparison_right(self):
        if self.busy or not self._comparison_left:
            return
        folder = QFileDialog.getExistingDirectory(self, 'Choose right saved backend or standalone ARM run')
        if folder:
            self._start('backend_compare', {'left': self._comparison_left, 'right': folder})

    def compare_selected(self):
        item = self.history.currentItem()
        right = item.data(Qt.ItemDataRole.UserRole) if item is not None and not item.isHidden() else None
        if self._comparison_left and right and right != self._comparison_left:
            self._start('backend_compare', {'left': self._comparison_left, 'right': right})

    def verify_selected(self):
        item = self.history.currentItem()
        if item is not None and not item.isHidden():
            self._start('backend_verify', {'run_dir': item.data(Qt.ItemDataRole.UserRole)})

    def verify_folder(self):
        if self.busy:
            return
        folder = QFileDialog.getExistingDirectory(self, 'Verify saved evidence without execution')
        if folder:
            self._start('backend_verify', {'run_dir': folder})

    def _verification_update(self, payload):
        if 'items' in payload:
            rows = payload['items'][:256]
            self.verification_table.setRowCount(len(rows))
            for index, item in enumerate(rows):
                self._verification_row(index, item)
        elif type(payload.get('index')) is int and 0 <= payload['index'] < self.verification_table.rowCount():
            self._verification_row(payload['index'], payload['item'])
        total, completed = payload.get('total'), payload.get('completed', 0)
        self.verification_progress.setTextVisible(type(total) is int and total > 0)
        if type(total) is int and total > 0:
            self.verification_progress.setRange(0, total)
            self.verification_progress.setValue(completed)
        elif payload.get('status') is None:
            self.verification_progress.setRange(0, 0)
        else:
            self.verification_progress.setRange(0, 1)
            self.verification_progress.setValue(0)
        phase = display_text(payload.get('status') or payload.get('phase', 'verification'), 80)
        count = f'{completed} of {total} artifact checks finished' if type(total) is int else 'Artifact total unavailable'
        self.verification_label.setText(phase + ' — ' + count + '. ' + display_text(payload.get('diagnostic', 'Pending and cancelled work is not verified.'), 600))

    def _verification_row(self, index, row):
        for column, key in enumerate(('name', 'state')):
            self.verification_table.setItem(index, column, QTableWidgetItem(display_text(row.get(key, 'unavailable'), 160)))

    @Slot()
    def _filter_history(self):
        query = self.history_filter.text().casefold()
        visible = 0
        for index in range(self.history.count()):
            item = self.history.item(index)
            path = item.data(Qt.ItemDataRole.UserRole)
            category = self.outcome_filter.currentData()
            matches = category == 'all' or outcome_category(self._history_summaries.get(path, {})) == category
            item.setHidden(query not in Path(path).name.casefold() or not matches)
            visible += not item.isHidden()
        if not self.history.count():
            message = 'No saved jobs here yet. Run a trusted project or use Open saved run to inspect another folder.'
        elif not visible:
            message = 'No matching run names or inspected outcomes. Inspect summaries for matching names, or clear the filters.'
        else:
            message = f'{visible} of {self.history.count()} listed runs. Outcomes reflect the last inspection; inspect summaries to update. Up to 1000 entries are listed.'
        self.history_hint.setText(message)
        self._refresh()

    @Slot()
    def refresh_history(self, *, preserve_summaries=False):
        if self.busy:
            return
        if not preserve_summaries:
            self._history_summaries.clear()
        selected = self.history.currentItem()
        selected_path = selected.data(Qt.ItemDataRole.UserRole) if selected else None
        self.history.clear()
        root = self.data_root / "runs"
        try:
            if root.is_dir() and not root.is_symlink():
                # No file content is trusted or parsed in Qt. The worker owns
                # bounded record validation when a user opens an entry.
                for directory in sorted(root.iterdir(), reverse=True)[:1000]:
                    if directory.is_dir() and not directory.is_symlink():
                        item = QListWidgetItem(display_text(directory.name, 255))
                        item.setData(Qt.ItemDataRole.UserRole, str(directory))
                        self.history.addItem(item)
                        self._summary_label(item)
                        if str(directory) == selected_path:
                            self.history.setCurrentItem(item)
        except OSError as exc:
            self._local_error(exc)
        self._filter_history()

    def _summary_label(self, item):
        path = item.data(Qt.ItemDataRole.UserRole)
        entry = self._history_summaries.get(path)
        if entry:
            fields = entry.get('fields', {})
            item.setText(display_text(Path(path).name, 100) + ' · ' + display_text(fields.get('backend') or 'unknown backend', 80) +
                         ' · ' + display_text(fields.get('status') or 'unknown', 80) + ' · integrity: ' + entry.get('integrity', {}).get('state', 'unavailable') + ' · last inspected: ' + entry['inspection'])

    @Slot()
    def reproduce(self):
        if self.busy or self.active_run is None or self.record is None:
            return
        try:
            trust = self._trust()
            output = self._fresh("runs")
            self._start("backend_reproduce", {"run_dir": str(self.active_run), "output_dir": str(output), "trust": trust}, output=output)
        except (ValueError, OSError, ProductError) as exc:
            self._local_error(exc)

    @Slot()
    def export(self):
        if self.busy or self.active_run is None:
            return
        parent = QFileDialog.getExistingDirectory(self, "Select parent for a fresh report, logs and waveform export")
        if parent:
            destination = Path(parent) / ("firmavex-backend-export-" + uuid4().hex[:12])
            self._start("backend_export", {"run_dir": str(self.active_run), "output_dir": str(destination)}, output=destination)

    @Slot(dict)
    def _progress(self, envelope):
        payload = envelope.get('payload', {})
        if self._job == 'backend_verify' and type(payload) is dict and payload.get('type') == 'verification_progress':
            self._verification_update(payload)
            return
        self.log_view.appendPlainText(_preview(envelope)[:8192])
        payload = envelope.get("payload", {})
        if type(payload) is dict:
            phases = {
                "validation": "Validating inputs, trust and compatibility",
                "process_started": "Starting owned runtime process",
                "input_ready": "Target reached its input-ready breakpoint",
                "input_injected": "Input vector injected",
                "simulation_output": "Simulator producing output",
                "finished": "Backend finished",
            }
            label = payload.get("message") or phases.get(payload.get("stage")) or payload.get("stage") or payload.get("type") or envelope.get("kind")
            accounting = payload.get("accounting")
            if payload.get("type") == "trial_complete" and type(accounting) is dict:
                label = f"Charged ARM evaluator attempts: {accounting.get('attempted_executions', 'unknown')}"
            if label:
                self.status_label.setText(str(label)[:500] + " — worker owns execution and cleanup.")

    @Slot(dict)
    def _result(self, record):
        command = self._job
        self._job = None
        administrative = command in {'backend_check', 'backend_prepare', 'backend_export', 'backend_history', 'backend_compare', 'backend_verify'}
        target = self.operation_view if administrative else self.result_view
        target.setPlainText(_preview(record))
        if administrative:
            self.tabs.setCurrentWidget(self.operation_view)
        if command == 'backend_verify':
            self._verification_update(record)
            self.tabs.setCurrentWidget(self.verification_panel)
            self.status_label.setText('Evidence verification: ' + display_text(record.get('status', 'unavailable'), 80) + '. Review per-artifact outcomes and scope.')
        elif command == 'backend_history':
            entries = {entry['run_dir']: entry for entry in record.get('entries', [])}
            self._history_summaries.update(entries)
            for index in range(self.history.count()):
                item = self.history.item(index)
                self._summary_label(item)
            self.status_label.setText('Inspected up to 50 listed run summaries. Saved metadata is not execution verification; refresh clears summaries.')
        elif command == 'backend_compare':
            rows = [('Saved folder', record['left']['run_dir'], record['right']['run_dir'], 'Reference only')]
            for row in record['rows']:
                rows.append((row['field'], row['left'], row['right'], row['comparison']))
            rows.append(('Evidence reference', record['left']['evidence_reference'], record['right']['evidence_reference'], 'Reference only'))
            for key in ('state', 'scope'):
                rows.append(('Integrity ' + key, record['left'].get('integrity', {}).get(key), record['right'].get('integrity', {}).get(key), 'Scoped checks only'))
            self.comparison_view.setRowCount(len(rows))
            for index, row in enumerate(rows):
                for column, value in enumerate(row):
                    text = 'unavailable' if value is None else value if type(value) is str else json.dumps(value)
                    item = QTableWidgetItem(display_text(text, 300))
                    item.setToolTip(display_text(text, 1000))
                    self.comparison_view.setItem(index, column, item)
            self.comparison_view.resizeRowsToContents()
            self.comparison_scope.setText(display_text(record.get('scope', ''), 1000))
            self.tabs.setCurrentWidget(self.comparison_panel)
            self.status_label.setText('Read-only comparison complete. Unavailable fields are not evidence of equality.')
        elif command == "backend_check":
            self._ready = record.get("status") in {"tools_available", "ready"} or record.get("success") is True
            self.status_label.setText("Runtime tools available; actual execution is checked by the backend." if self._ready else "Runtime unavailable or unsupported. Review readiness details; nothing executed.")
        elif command == "backend_prepare":
            artifact = record.get("firmware") or record.get("source") or {}
            artifact_path = artifact.get("path") if type(artifact) is dict else artifact if type(artifact) is str else None
            source = record.get("config_file") if self.profile == "cortex-m3-mps2" else (
                record.get("firmware_file") or record.get("source_file")
                or artifact_path
            )
            if source:
                self._example_source = str(source)
                self.source_edit.setText(str(source))
                self.trust_box.setChecked(False)
                self.status_label.setText("Independent example prepared; no target execution performed. Check runtime, acknowledge trusted runtime tools, then Run.")
            else:
                self.status_label.setText("Preparation returned no usable source path; inspect details before proceeding.")
        elif command in {"backend_execute", "backend_inspect", "backend_reproduce"}:
            self.record = record.get("result", record) if command == "backend_reproduce" else record
            self.result_context_label.setText(result_context(self.record, self.active_run))
            status = self.record.get("status", "unknown")
            prefix = "Saved record" if command == "backend_inspect" else "Observed outcome"
            self.status_label.setText(f"{prefix}: {status}. Review completion, evidence and cleanup fields; receipt arrival alone is not success.")
            explanation = summary(self.record)
            diagnostics = compiler_diagnostics(self.record)
            if diagnostics:
                explanation += "\n\n" + diagnostics
            reproduction = arm_reproduction_summary(self.record)
            if reproduction:
                explanation += "\n\n" + reproduction
            self.summary_view.setPlainText(explanation)
            self.tabs.setCurrentWidget(self.summary_view)
        elif command == "backend_export":
            self.status_label.setText("Export complete: " + str(record.get("destination", self._output)))
        self._refresh()

    def _local_error(self, exc):
        category = exc.category if isinstance(exc, ProductError) else "invalid_input"
        self.status_label.setText(display_text(category + ": " + str(exc) + " " + guidance(category)))
        self._refresh()

    @Slot(dict)
    def _error(self, record):
        command = self._job
        self._job = None
        if command in {'backend_check', 'backend_prepare', 'backend_export', 'backend_history', 'backend_compare', 'backend_verify'}:
            if command == 'backend_verify':
                for index in range(self.verification_table.rowCount()):
                    state = self.verification_table.item(index, 1)
                    if state.text() in {'pending', 'checking'}:
                        state.setText('not_checked')
                self.verification_progress.setRange(0, 1)
                self.verification_progress.setValue(0)
                self.verification_progress.setTextVisible(False)
                self.verification_label.setText('Verification interrupted. Completed checks retained; no overall verification result is available.')
            if command == 'backend_compare':
                self.comparison_scope.setText('Comparison unavailable: ' + display_text(record.get('message', 'Review operation details.'), 500))
            self.operation_view.setPlainText(_preview(record))
            self.tabs.setCurrentWidget(self.operation_view)
            self.status_label.setText(display_text(str(record.get('category', 'worker_error')) + ': ' + str(record.get('message', 'Review operation details.'))))
            self._refresh()
            return
        self.result_context_label.setText('No validated outcome from this operation. Review the error and inspect the saved run if available.')
        self.result_view.setPlainText(_preview(record))
        explanation = display_text(record.get("message", "Worker failure"), 2000) + "\n" + guidance(record.get("category"))
        details = record.get("details")
        partial = details.get("partial_result") if type(details) is dict else None
        reproduction = arm_reproduction_summary(partial)
        if reproduction:
            explanation += "\n\n" + reproduction
        self.summary_view.setPlainText(explanation)
        self.tabs.setCurrentWidget(self.summary_view)
        self.status_label.setText(display_text(str(record.get("category", "worker_error")) + ": " + str(record.get("message", "Inspect saved results."))))
        self._refresh()

    @Slot()
    def _idle(self):
        self.refresh_history(preserve_summaries=True)
        self._refresh()
        if self._closing:
            self.close()

    @Slot()
    def _refresh(self):
        idle = not self.busy and not self._closing
        for control in (self.profile_combo, self.source_edit, self.browse_button, self.values_edit, self.trust_box, self.check_button, self.setup_button, self.example_button, self.arm_button, self.history, self.history_filter, self.outcome_filter, self.history_refresh_button, self.open_button, self.left_folder_button):
            control.setEnabled(idle)
        self.timeout_spin.setEnabled(idle and self.profile != "cortex-m3-mps2")
        self.artifact_spin.setEnabled(idle and self.profile != "cortex-m3-mps2")
        try:
            self._request()
            input_error = None
        except ValueError as exc:
            input_error = str(exc)
        self.run_button.setEnabled(idle and self._ready and input_error is None and self.trust_box.isChecked())
        if not idle:
            hint = 'Wait for the active job and confirmed cleanup before starting another operation.'
        elif input_error:
            hint = input_error + ' Preparing an independent example does not execute it.'
        elif not self._ready:
            hint = 'Next: check runtime readiness for the selected backend. No target executes during this check.'
        elif not self.trust_box.isChecked():
            hint = 'Next: review the input and runtime tools, then acknowledge trust before Run.'
        else:
            hint = 'Ready to submit with Run. The worker will validate file compatibility and runtime support before dispatch.'
        self.workflow_hint.setText(hint)
        self.run_button.setToolTip(hint)
        selected = self.history.currentItem()
        self.open_selected_button.setEnabled(idle and selected is not None and not selected.isHidden())
        self.pin_button.setEnabled(idle and selected is not None and not selected.isHidden())
        self.compare_button.setEnabled(idle and selected is not None and not selected.isHidden() and
                                       self._comparison_left is not None and selected.data(Qt.ItemDataRole.UserRole) != self._comparison_left)
        self.history_summary_button.setEnabled(idle and any(self.history_filter.text().casefold() in Path(self.history.item(i).data(Qt.ItemDataRole.UserRole)).name.casefold() for i in range(self.history.count())))
        self.right_folder_button.setEnabled(idle and self._comparison_left is not None)
        self.verify_button.setEnabled(idle and selected is not None and not selected.isHidden())
        self.verify_folder_button.setEnabled(idle)
        self.cancel_button.setEnabled(self.busy and not self._closing)
        self.reproduce_button.setEnabled(idle and self.active_run is not None and self.record is not None and self.record.get("status") in {"passed", "triggered"} and self.trust_box.isChecked())
        self.export_button.setEnabled(idle and self.active_run is not None and self.record is not None)
        self.progress_bar.setRange(0, 0 if self.busy else 1)
        self.progress_bar.setValue(0)

    def closeEvent(self, event: QCloseEvent):
        if not self.controller.shutdown():
            self._closing = True
            self.status_label.setText("Closing after cancellation, persistence and process-tree cleanup…")
            self._refresh()
            event.ignore()
            return
        event.accept()
