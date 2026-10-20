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
)

from firmavex.backends.api import Limits, Request, profiles, request_to_dict
from firmavex.product.errors import ProductError
from firmavex.product.presentation import summary, guidance
from .controller import DesktopController
from .diagnostics import arm_reproduction_summary, compiler_diagnostics
from .projects import _safe_root, application_data_directory


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
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.progress_bar.setAccessibleName("Supervised job progress")
        layout.addWidget(self.progress_bar)
        split = QSplitter()
        history_panel = QWidget()
        history_layout = QVBoxLayout(history_panel)
        history_layout.addWidget(QLabel("Saved job history — reopen without execution"))
        self.history = QListWidget()
        self.history.setAccessibleName("Persistent backend job history")
        self.history.itemDoubleClicked.connect(self.open_history_item)
        history_layout.addWidget(self.history)
        history_actions = QHBoxLayout()
        self.history_refresh_button = self._button("Refresh", self.refresh_history)
        self.open_button = self._button("Open saved run…", self.pick_run)
        history_actions.addWidget(self.history_refresh_button)
        history_actions.addWidget(self.open_button)
        history_layout.addLayout(history_actions)
        split.addWidget(history_panel)
        self.tabs = QTabWidget()
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
        if command in {'backend_execute', 'backend_reproduce', 'backend_inspect'}:
            self.summary_view.clear()
            self.result_view.clear()
        if command in {"backend_execute", "backend_reproduce"}:
            self.active_run, self.record = output, None
            self.result_view.clear()
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
            text = self.source_edit.text().strip()
            if not text or any(ord(character) < 32 for character in text):
                raise ValueError("Choose a compatible input file with a valid path.")
            values = ()
            if self.profile == "riscv32-virt":
                tokens = self.values_edit.text().replace(",", " ").split()
                values = tuple(int(token, 16 if token.lower().startswith("0x") else 10) for token in tokens)
            limits = Limits() if self.profile == "cortex-m3-mps2" else Limits(
                self.timeout_spin.value(), artifact_bytes=self.artifact_spin.value() * 1024 * 1024
            )
            request = Request(self.profile, Path(text).expanduser(), values, limits)
            output = self._fresh("runs")
            self._start("backend_execute", {"request": request_to_dict(request), "output_dir": str(output), "trust": trust}, output=output)
        except (ValueError, OSError, ProductError) as exc:
            self._local_error(exc)

    def _trust(self):
        if not self.trust_box.isChecked():
            raise ValueError("Unknown or untrusted workloads are rejected. Explicitly acknowledge a trusted project.")
        return "trusted_example" if self._example_source == self.source_edit.text() else "trusted_project"

    @Slot()
    def cancel(self):
        if self.controller.cancel():
            self.status_label.setText("Cancellation requested; waiting for persistence and process-tree cleanup…")
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
        self.inspect(Path(item.data(Qt.ItemDataRole.UserRole)))

    @Slot()
    def refresh_history(self):
        if self.busy:
            return
        self.history.clear()
        root = self.data_root / "runs"
        try:
            if root.is_dir() and not root.is_symlink():
                # No file content is trusted or parsed in Qt. The worker owns
                # bounded record validation when a user opens an entry.
                for directory in sorted(root.iterdir(), reverse=True)[:1000]:
                    if directory.is_dir() and not directory.is_symlink():
                        item = QListWidgetItem(directory.name)
                        item.setData(Qt.ItemDataRole.UserRole, str(directory))
                        self.history.addItem(item)
        except OSError as exc:
            self._local_error(exc)

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
        self.result_view.setPlainText(_preview(record))
        if command == "backend_check":
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
        self.status_label.setText(category + ": " + str(exc) + " " + guidance(category))
        self._refresh()

    @Slot(dict)
    def _error(self, record):
        self._job = None
        self.result_view.setPlainText(_preview(record))
        explanation = str(record.get("message", "Worker failure")) + "\n" + guidance(record.get("category"))
        details = record.get("details")
        partial = details.get("partial_result") if type(details) is dict else None
        reproduction = arm_reproduction_summary(partial)
        if reproduction:
            explanation += "\n\n" + reproduction
        self.summary_view.setPlainText(explanation)
        self.status_label.setText(str(record.get("category", "worker_error")) + ": " + str(record.get("message", "Inspect saved results.")))
        self._refresh()

    @Slot()
    def _idle(self):
        self.refresh_history()
        self._refresh()
        if self._closing:
            self.close()

    @Slot()
    def _refresh(self):
        idle = not self.busy and not self._closing
        for control in (self.profile_combo, self.source_edit, self.browse_button, self.values_edit, self.trust_box, self.check_button, self.setup_button, self.example_button, self.arm_button, self.history, self.history_refresh_button, self.open_button):
            control.setEnabled(idle)
        self.timeout_spin.setEnabled(idle and self.profile != "cortex-m3-mps2")
        self.artifact_spin.setEnabled(idle and self.profile != "cortex-m3-mps2")
        self.run_button.setEnabled(idle and self._ready and bool(self.source_edit.text().strip()) and self.trust_box.isChecked())
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
