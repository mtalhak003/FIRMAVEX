"""Accessible desktop workflow around the product worker, never the research campaign.

Firmware operations execute in the supervised worker. Project import/open use a
small background task so copying an image cannot block the GUI event loop.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, Signal
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog,
    QFormLayout, QFrame, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QMainWindow, QMessageBox, QPlainTextEdit,
    QProgressBar, QPushButton, QScrollArea, QSpinBox, QSplitter,
    QStackedWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, QTabWidget,
)

from firmavex.product.config import ProductConfig, load_config
from firmavex.product.errors import ProductError
from firmavex.product.services import _report
from .controller import DesktopController
from .projects import DesktopProject, application_data_directory, _safe_root


def _fresh_name(prefix: str) -> str:
    return prefix + "-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]


def _json(value: object) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False)


class _TaskSignals(QObject):
    finished = Signal(object)
    failed = Signal(dict)


class _ProjectTask(QRunnable):
    def __init__(self, operation):
        super().__init__()
        self.operation = operation
        self.signals = _TaskSignals()

    def run(self):
        try:
            self.signals.finished.emit(self.operation())
        except BaseException as exc:
            details = exc.to_dict() if isinstance(exc, ProductError) else {
                "category": "cancelled" if not isinstance(exc, Exception) else "project_error", "message": str(exc),
                "details": {"exception_type": type(exc).__name__},
            }
            self.signals.failed.emit(details)


class MainWindow(QMainWindow):
    """One active job, explicit import/recovery, and evidence-aware result views."""

    def __init__(self, controller=None, *, data_root: Path | None = None):
        super().__init__()
        self.controller = controller if controller is not None else DesktopController(self)
        self.data_root = Path(data_root) if data_root is not None else application_data_directory()
        self.project = None
        self.active_run: Path | None = None
        self.result_record: dict | None = None
        self.inspection: dict | None = None
        self._job: str | None = None
        self._job_output: Path | None = None
        self._local_task = None
        self._closing = False
        self._config_template: ProductConfig | None = None
        self._universal_window = None
        self.setWindowTitle("FIRMAVEX Desktop — firmware testing")
        self.resize(1160, 800)
        self.setMinimumSize(860, 620)
        self._build_ui()
        self.controller.event.connect(self._event)
        self.controller.result.connect(self._result)
        self.controller.error.connect(self._error)
        self.controller.busy_changed.connect(self._busy_changed)
        self.controller.idle.connect(self._idle)
        self._refresh_enabled()

    @property
    def busy(self) -> bool:
        return self._local_task is not None or self.controller.busy

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        header = QHBoxLayout()
        brand = QLabel("FIRMAVEX Desktop")
        brand.setStyleSheet("font-size: 22px; font-weight: 600;")
        self.project_label = QLabel("No project open")
        self.project_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        header.addWidget(brand)
        header.addStretch()
        header.addWidget(self.project_label)
        outer.addLayout(header)
        self.warning = QLabel("Emulated Cortex-M3 testing • compatible symbolized ELF only • trusted projects only • not a security sandbox • no hardware validation")
        self.warning.setWordWrap(True)
        outer.addWidget(self.warning)
        split = QSplitter()
        self.navigation = QListWidget()
        self.navigation.addItems(["Welcome", "Project & configuration", "Testing & progress", "Results & reproduction"])
        self.navigation.setMaximumWidth(235)
        self.navigation.setAccessibleName("Application navigation")
        self.pages = QStackedWidget()
        self.navigation.currentRowChanged.connect(self.pages.setCurrentIndex)
        split.addWidget(self.navigation)
        split.addWidget(self.pages)
        split.setStretchFactor(1, 1)
        outer.addWidget(split, 1)
        self._welcome_page()
        self._project_page()
        self._testing_page()
        self._results_page()
        self.navigation.setCurrentRow(0)
        self.status_label = QLabel("Ready. Open a project or build the independent example.")
        self.status_label.setWordWrap(True)
        self.statusBar().addWidget(self.status_label, 1)
        menu = self.menuBar().addMenu("&File")
        for title, shortcut, callback in (
            ("&New project", QKeySequence.New, lambda: self.navigation.setCurrentRow(1)),
            ("&Open project…", QKeySequence.Open, self._pick_open_project),
            ("&Save configuration", QKeySequence.Save, self.save_configuration),
            ("&Quit", QKeySequence.Quit, self.close),
        ):
            action = QAction(title, self)
            action.setShortcut(shortcut)
            action.triggered.connect(callback)
            menu.addAction(action)
        examples = self.menuBar().addMenu("&Examples")
        for text, callback in (("Verified built-in image (no compiler)", self.prepare_builtin_example), ("Build from source (requires ARM GCC)", self.build_example)):
            action = QAction(text, self)
            action.triggered.connect(callback)
            examples.addAction(action)
        backends = self.menuBar().addMenu("&Backends")
        self.backend_action = QAction("Processor and HDL workspace…", self)
        self.backend_action.triggered.connect(self.show_backends)
        backends.addAction(self.backend_action)

    def show_backends(self):
        """Open a separate capability-aware workspace; preserve the ARM editor."""
        if self.busy or self._closing:
            self.status_label.setText("Wait for the active ARM job and cleanup before switching workspaces.")
            return
        from .universal import UniversalWindow
        if self._universal_window is None:
            self._universal_window = UniversalWindow(data_root=self.data_root, parent=self)
            self._universal_window.setWindowModality(Qt.WindowModality.WindowModal)
            self._universal_window.arm_configuration_requested.connect(self._return_to_arm)
            self._universal_window.runtime_setup_requested.connect(self._backend_setup)
            self._universal_window.controller.idle.connect(self._backend_idle)
        self._universal_window.show()
        self._universal_window.raise_()
        self._universal_window.activateWindow()

    def _return_to_arm(self):
        if self._universal_window is not None and not self._universal_window.busy:
            self._universal_window.close()
            self.navigation.setCurrentRow(1)

    def _backend_idle(self):
        if self._closing:
            self.close()

    def _backend_setup(self):
        if self._universal_window is not None and not self._universal_window.busy:
            self._universal_window.close()
            self.show_setup()

    def _button(self, text, callback, *, name=None):
        button = QPushButton(text)
        if name:
            button.setObjectName(name)
        button.clicked.connect(callback)
        return button

    def _welcome_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        title = QLabel("Test firmware with a recorded, reproducible workflow")
        title.setStyleSheet("font-size: 19px; font-weight: 600;")
        layout.addWidget(title)
        intro = QLabel(
            "1. Import compatible Cortex-M3 ELF firmware into a new project.\n"
            "2. Declare input symbols, input-ready and completion functions, and the failure condition.\n"
            "3. Validate tools and configuration, run a bounded search, then reproduce or export the result.\n\n"
            "The independent example includes the required symbols and startup code. "
            "Opening this application does not execute firmware."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        row = QHBoxLayout()
        self.new_button = self._button("New firmware project", lambda: self.navigation.setCurrentRow(1))
        self.open_button = self._button("Open project…", self._pick_open_project)
        self.example_button = self._button("Try built-in example (no compiler)", self.prepare_builtin_example)
        for button in (self.new_button, self.open_button, self.example_button):
            row.addWidget(button)
        layout.addLayout(row)
        self.setup_button = self._button("First-launch setup and runtime repair…", self.show_setup)
        layout.addWidget(self.setup_button)
        self.doctor_button = self._button("Check runtime tools", self.check_tools)
        layout.addWidget(self.doctor_button)
        self.runtime_install_button = self._button("Install / repair trusted runtime pack…", self.install_runtime_pack)
        self.runtime_verify_button = self._button("Verify installed runtime pack", self.verify_runtime_pack)
        layout.addWidget(self.runtime_install_button)
        layout.addWidget(self.runtime_verify_button)
        self.tool_status = QLabel("Check QEMU and ARM-capable GDB before testing. The built-in example requires no compiler.")
        self.tool_status.setWordWrap(True)
        layout.addWidget(self.tool_status)
        self.tool_details = QPlainTextEdit()
        self.tool_details.setReadOnly(True)
        self.tool_details.setPlaceholderText("Tool availability, versions, and platform limitations appear here.")
        self.tool_details.setAccessibleName("Runtime capability report")
        layout.addWidget(self.tool_details, 1)
        self.pages.addWidget(page)

    def _project_page(self):
        page = QWidget()
        outer = QVBoxLayout(page)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        form = QFormLayout(content)
        self.firmware_edit = QLineEdit()
        self.firmware_edit.setPlaceholderText("Choose a Cortex-M3 ELF image; raw BIN images are not supported")
        self.firmware_button = self._button("Browse ELF…", self._pick_firmware)
        row = QHBoxLayout()
        row.addWidget(self.firmware_edit)
        row.addWidget(self.firmware_button)
        form.addRow("Firmware ELF", row)
        self.project_dir_edit = QLineEdit(str(self.data_root / "projects" / _fresh_name("project")))
        self.project_dir_button = self._button("Choose parent…", self._pick_project_parent)
        row = QHBoxLayout()
        row.addWidget(self.project_dir_edit)
        row.addWidget(self.project_dir_button)
        form.addRow("New project folder", row)
        self.create_button = self._button("Import into new project", self.create_project)
        form.addRow("", self.create_button)
        help_text = QLabel(
            "Imports copy the image into the new project. Existing files are never overwritten. "
            "Input/failure bindings must be uint32 symbols or individual array entries. "
            "Breakpoints must be plain C function names. The supported board is QEMU mps2-an385."
        )
        help_text.setWordWrap(True)
        form.addRow(help_text)
        self.inputs_edit = QLineEdit("product_inputs[0], product_inputs[1]")
        self.inputs_edit.setPlaceholderText("e.g. inputs[0], inputs[1] — comma-separated, in vector order")
        self.ready_edit = QLineEdit("product_input_ready")
        self.complete_edit = QLineEdit("product_complete")
        self.failure_edit = QLineEdit("product_failure")
        self.failure_value_edit = QLineEdit("1")
        self.minimum_edit = QLineEdit("0")
        self.maximum_edit = QLineEdit("3")
        for label, widget in (
            ("Input bindings (ordered)", self.inputs_edit),
            ("Input-ready function", self.ready_edit),
            ("Completion function", self.complete_edit),
            ("Failure symbol", self.failure_edit),
            ("Failure value (equality)", self.failure_value_edit),
            ("Input minimum (uint32)", self.minimum_edit),
            ("Input maximum (uint32)", self.maximum_edit),
        ):
            form.addRow(label, widget)
        self.strategy_combo = QComboBox()
        self.strategy_combo.addItems(["enumerative", "random", "guided"])
        self.seed_edit = QLineEdit("0")
        self.seed_edit.setToolTip("Explicit integer seed for random/guided. Enumerative has no seed.")
        self.budget_spin = QSpinBox()
        self.budget_spin.setRange(1, 1_000_000)
        self.budget_spin.setValue(16)
        self.timeout_spin = QDoubleSpinBox()
        self.timeout_spin.setRange(0.001, 3600)
        self.timeout_spin.setDecimals(3)
        self.timeout_spin.setValue(10)
        self.startup_spin = QDoubleSpinBox()
        self.startup_spin.setRange(0.001, 3600)
        self.startup_spin.setDecimals(3)
        self.startup_spin.setValue(5)
        self.signature_check = QCheckBox("Collect bounded execution signatures (required for guided)")
        self.signature_check.setChecked(True)
        self.archive_spin = QSpinBox()
        self.archive_spin.setRange(1, 1_000_000)
        self.archive_spin.setValue(32)
        self.mutations_spin = QSpinBox()
        self.mutations_spin.setRange(1, 1_000_000)
        self.mutations_spin.setValue(8)
        for label, widget in (
            ("Search strategy", self.strategy_combo), ("Seed", self.seed_edit),
            ("Charged attempt budget", self.budget_spin),
            ("Execution timeout (seconds)", self.timeout_spin),
            ("Startup timeout (seconds)", self.startup_spin),
            ("Runtime feedback", self.signature_check),
            ("Guided archive size", self.archive_spin),
            ("Guided mutation attempts", self.mutations_spin),
        ):
            form.addRow(label, widget)
        self.qemu_edit = QLineEdit()
        self.gdb_edit = QLineEdit()
        self.compiler_edit = QLineEdit()
        for label, widget in (("QEMU override", self.qemu_edit), ("ARM-capable GDB override", self.gdb_edit), ("ARM compiler override", self.compiler_edit)):
            widget.setPlaceholderText("Leave empty for automatic discovery")
            form.addRow(label, widget)
        self.strategy_combo.currentTextChanged.connect(self._strategy_changed)
        self._strategy_changed()
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)
        row = QHBoxLayout()
        self.save_button = self._button("Save configuration", self.save_configuration)
        self.validate_button = self._button("Validate firmware & tools", self.validate_configuration)
        self.run_button = self._button("Run bounded test", self.start_run)
        for button in (self.save_button, self.validate_button, self.run_button):
            row.addWidget(button)
        outer.addLayout(row)
        self.validation_text = QPlainTextEdit()
        self.validation_text.setReadOnly(True)
        self.validation_text.setMaximumHeight(150)
        self.validation_text.setPlaceholderText("Validation details and actionable errors appear here.")
        outer.addWidget(self.validation_text)
        self.pages.addWidget(page)

    def _testing_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        self.progress_label = QLabel("No test running.")
        self.progress_label.setWordWrap(True)
        layout.addWidget(self.progress_label)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        self.accounting_label = QLabel("Charged attempts: 0 • completed observations: 0 • infrastructure failures: 0")
        self.accounting_label.setWordWrap(True)
        layout.addWidget(self.accounting_label)
        self.cancel_button = self._button("Cancel and preserve partial result", self.cancel_job)
        layout.addWidget(self.cancel_button)
        self.attempts_table = QTableWidget(0, 4)
        self.attempts_table.setHorizontalHeaderLabels(["Charged attempt", "Input vector", "Observation", "Signature digest"])
        self.attempts_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.attempts_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.attempts_table.horizontalHeader().setStretchLastSection(True)
        self.attempts_table.setAccessibleName("Recent execution observations")
        layout.addWidget(self.attempts_table, 1)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(1000)
        self.log.setMaximumHeight(175)
        self.log.setAccessibleName("Execution and cleanup event log")
        layout.addWidget(self.log)
        note = QLabel("The view retains the latest 500 observations. Full persisted records remain in the run folder.")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.pages.addWidget(page)

    def _results_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        top = QHBoxLayout()
        self.open_run_button = self._button("Open run folder…", self._pick_run)
        self.inspect_button = self._button("Inspect saved run", self.inspect_current_run)
        top.addWidget(self.open_run_button)
        top.addWidget(self.inspect_button)
        top.addStretch()
        layout.addLayout(top)
        self.run_path_label = QLabel("No run selected")
        self.run_path_label.setWordWrap(True)
        self.run_path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.run_path_label)
        self.outcome_label = QLabel("No result available")
        self.outcome_label.setWordWrap(True)
        self.outcome_label.setStyleSheet("font-size: 18px; font-weight: 600;")
        self.trigger_label = QLabel("Triggering input: unavailable")
        self.trigger_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.evidence_label = QLabel("Execution evidence: unavailable")
        self.evidence_label.setWordWrap(True)
        layout.addWidget(self.outcome_label)
        layout.addWidget(self.trigger_label)
        layout.addWidget(self.evidence_label)
        self.result_text = QPlainTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setAccessibleName("Saved result, accounting and diagnostics")
        self.report_view = QPlainTextEdit()
        self.report_view.setReadOnly(True)
        self.report_view.setAccessibleName("Readable firmware test report")
        self.result_tabs = QTabWidget()
        self.result_tabs.addTab(self.report_view, "Readable report")
        self.result_tabs.addTab(self.result_text, "Evidence & diagnostics")
        layout.addWidget(self.result_tabs, 1)
        row = QHBoxLayout()
        self.replay_spin = QSpinBox()
        self.replay_spin.setRange(1, 100)
        self.replay_spin.setValue(3)
        self.replay_spin.setAccessibleName("Bounded reproduction attempt count")
        self.reproduce_button = self._button("Reproduce exact triggering vector", self.reproduce)
        self.export_button = self._button("Export report & evidence", self.export_result)
        row.addWidget(QLabel("Repetitions:"))
        row.addWidget(self.replay_spin)
        row.addWidget(self.reproduce_button)
        row.addWidget(self.export_button)
        layout.addLayout(row)
        row = QHBoxLayout()
        self.recover_button = self._button("Mark interrupted run recovered…", self.recover_current_run)
        self.restart_button = self._button("Restart as a new run…", self.restart_current_run)
        row.addWidget(self.recover_button)
        row.addWidget(self.restart_button)
        layout.addLayout(row)
        warning = QLabel("A failure is the configured symbol condition in this emulator. No discovery is not a safety guarantee. Charged attempts are not independent proof of physical firmware executions.")
        warning.setWordWrap(True)
        layout.addWidget(warning)
        self.pages.addWidget(page)

    def _strategy_changed(self, *_):
        strategy = self.strategy_combo.currentText()
        self.seed_edit.setEnabled(strategy != "enumerative" and not self.busy)
        self.archive_spin.setEnabled(strategy == "guided" and not self.busy)
        self.mutations_spin.setEnabled(strategy == "guided" and not self.busy)

    def _refresh_enabled(self):
        idle = not self.busy and not self._closing
        project = self.project is not None
        for button in (self.new_button, self.open_button, self.example_button,
                       self.setup_button, self.runtime_install_button, self.runtime_verify_button,
                       self.doctor_button, self.create_button, self.firmware_button,
                       self.project_dir_button, self.open_run_button):
            button.setEnabled(idle)
        for button in (self.save_button, self.validate_button, self.run_button):
            button.setEnabled(idle and project)
        self.cancel_button.setEnabled(self.controller.busy and not self._closing)
        self.inspect_button.setEnabled(idle and self.active_run is not None)
        has_result = self.result_record is not None
        self.export_button.setEnabled(idle and self.active_run is not None and has_result)
        trigger = self.result_record.get("triggering_input") if has_result else None
        mode = self.result_record.get("measurement_mode") if has_result else None
        self.reproduce_button.setEnabled(idle and self.active_run is not None and trigger is not None and mode == "real_firmware")
        self.recover_button.setEnabled(idle and self.active_run is not None and bool((self.inspection or {}).get("recovery_required")))
        self.restart_button.setEnabled(idle and self.active_run is not None and (self.result_record or {}).get("state") in {"interrupted", "cancelled", "failed"})
        for widget in (self.firmware_edit, self.project_dir_edit, self.inputs_edit,
                       self.ready_edit, self.complete_edit, self.failure_edit,
                       self.failure_value_edit, self.minimum_edit, self.maximum_edit,
                       self.strategy_combo, self.budget_spin, self.timeout_spin,
                       self.startup_spin, self.signature_check, self.qemu_edit,
                       self.gdb_edit, self.compiler_edit, self.replay_spin):
            widget.setEnabled(idle)
        self._strategy_changed()

    @staticmethod
    def _integer(edit: QLineEdit, label: str) -> int:
        value = edit.text().strip()
        try:
            # Hex notation is useful for masks; decimal remains exact for the
            # entire uint32 range, unlike a signed Qt spin box.
            return int(value, 16 if value.lower().startswith(("0x", "+0x", "-0x")) else 10)
        except ValueError as exc:
            raise ProductError("invalid_configuration", f"{label} must be an integer (decimal or 0x hexadecimal).") from exc

    def configuration(self) -> ProductConfig:
        firmware = self.project.firmware_path if self.project else Path(self.firmware_edit.text().strip())
        if not self.firmware_edit.text().strip() and self.project is None:
            raise ProductError("invalid_configuration", "Choose an ELF firmware image first.")
        strategy = self.strategy_combo.currentText()
        values = dict(
            firmware=firmware,
            input_symbols=tuple(value.strip() for value in self.inputs_edit.text().split(",")),
            ready_breakpoint=self.ready_edit.text().strip(),
            completion_breakpoint=self.complete_edit.text().strip(),
            failure_symbol=self.failure_edit.text().strip(),
            input_min=self._integer(self.minimum_edit, "Input minimum"),
            input_max=self._integer(self.maximum_edit, "Input maximum"),
            failure_value=self._integer(self.failure_value_edit, "Failure value"),
            execution_budget=self.budget_spin.value(), strategy=strategy,
            seed=None if strategy == "enumerative" else self._integer(self.seed_edit, "Seed"),
            timeout_seconds=self.timeout_spin.value(), startup_timeout_seconds=self.startup_spin.value(),
            collect_signature=self.signature_check.isChecked(),
            guided_archive_size=self.archive_spin.value(), guided_mutation_attempts=self.mutations_spin.value(),
            qemu=self.qemu_edit.text().strip() or None,
            gdb=self.gdb_edit.text().strip() or None,
            compiler=self.compiler_edit.text().strip() or None,
        )
        return ProductConfig(**values)

    def _load_fields(self, config):
        self._config_template = config
        self.firmware_edit.setText(str(config.firmware))
        self.inputs_edit.setText(", ".join(config.input_symbols))
        self.ready_edit.setText(config.ready_breakpoint)
        self.complete_edit.setText(config.completion_breakpoint)
        self.failure_edit.setText(config.failure_symbol)
        self.failure_value_edit.setText(str(config.failure_value))
        self.minimum_edit.setText(str(config.input_min))
        self.maximum_edit.setText(str(config.input_max))
        self.strategy_combo.setCurrentText(config.strategy)
        self.seed_edit.setText(str(config.seed if config.seed is not None else 0))
        self.budget_spin.setValue(config.execution_budget)
        self.timeout_spin.setValue(config.timeout_seconds)
        self.startup_spin.setValue(config.startup_timeout_seconds)
        self.signature_check.setChecked(config.collect_signature)
        self.archive_spin.setValue(config.guided_archive_size)
        self.mutations_spin.setValue(config.guided_mutation_attempts)
        self.qemu_edit.setText(config.qemu or "")
        self.gdb_edit.setText(config.gdb or "")
        self.compiler_edit.setText(config.compiler or "")

    def _local_operation(self, operation, callback):
        if self.busy:
            return False
        task = _ProjectTask(operation)
        self._local_task = task

        def finished(value):
            self._local_task = None
            try:
                callback(value)
            except Exception as exc:
                self._error(exc.to_dict() if isinstance(exc, ProductError) else {"category": "project_error", "message": str(exc)})
            self._refresh_enabled()
            self._idle()

        def failed(error):
            self._local_task = None
            self._error(error)
            self._refresh_enabled()
            self._idle()

        task.signals.finished.connect(finished)
        task.signals.failed.connect(failed)
        self._refresh_enabled()
        QThreadPool.globalInstance().start(task)
        return True

    def _adopt_project(self, value):
        project, config = value
        self.project = project
        self._load_fields(config)
        self.project_dir_edit.setText(str(project.root))
        self.project_label.setText(project.root.name)
        self.status_label.setText("Project open. Review the configuration, then validate firmware and tools.")
        self.navigation.setCurrentRow(1)
        self.validation_text.clear()
        self._refresh_enabled()

    def create_project(self):
        if self.busy:
            return
        try:
            config = self.configuration()
            directory_text = self.project_dir_edit.text().strip()
            if not directory_text:
                raise ProductError("project_error", "Choose a new project folder.")
            directory = Path(directory_text).expanduser()
            self.status_label.setText("Importing firmware into a new project…")
            self._local_operation(lambda: self._verified_project(DesktopProject.create(directory, config.firmware, config)), self._adopt_project)
        except Exception as exc:
            self._error(exc.to_dict() if isinstance(exc, ProductError) else {"category": "project_error", "message": str(exc)})

    def open_project(self, directory):
        if not self.busy:
            self.status_label.setText("Opening and verifying project…")
            self._local_operation(lambda: self._verified_project(DesktopProject.open(Path(directory))), self._adopt_project)

    @staticmethod
    def _verified_project(project):
        return project, project.load_config()

    def _pick_open_project(self):
        if self.busy:
            return
        directory = QFileDialog.getExistingDirectory(self, "Open FIRMAVEX project")
        if directory:
            self.open_project(directory)

    def _pick_firmware(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select compatible Cortex-M3 ELF", "", "ELF firmware (*.elf);;All files (*)")
        if path:
            self.firmware_edit.setText(path)

    def _pick_project_parent(self):
        directory = QFileDialog.getExistingDirectory(self, "Choose parent for a new project")
        if directory:
            self.project_dir_edit.setText(str(Path(directory) / _fresh_name("project")))

    def save_configuration(self, after=None):
        if self.busy or self.project is None:
            return False
        try:
            config = self.configuration()
            def saved(command_path):
                self._config_template = config
                self.status_label.setText("Configuration saved. Runtime validation is performed again before execution.")
                if callable(after):
                    after(config, command_path)
            def persist():
                record = self.project.save_config(config)
                return self.project.command_config(record) if callable(after) else None
            return self._local_operation(persist, saved)
        except Exception as exc:
            self._error(exc.to_dict() if isinstance(exc, ProductError) else {"category": "project_error", "message": str(exc)})
            return False

    def _start(self, command, payload, *, output=None):
        if self.busy or self._closing:
            return False
        if not self.controller.start(command, payload):
            return False
        self._job = command
        self._job_output = Path(output) if output is not None else None
        self.status_label.setText(f"{command.replace('_', ' ').capitalize()} in progress…")
        self._refresh_enabled()
        return True

    def _runtime_report(self, result):
        self.tool_details.setPlainText(json.dumps(result, indent=2, sort_keys=True))
        self.tool_status.setText("Runtime integrity checked. Capability probes do not establish native firmware qualification. Check runtime tools next.")

    def verify_runtime_pack(self):
        from firmavex.product.runtime_pack import active_tools
        self._local_operation(lambda: {"verified_tools": active_tools()}, self._runtime_report)

    def install_runtime_pack(self):
        from PySide6.QtWidgets import QInputDialog
        from firmavex.product.runtime_pack import install
        path, _ = QFileDialog.getOpenFileName(self, "Select trusted runtime pack", "", "Runtime ZIP (*.zip)")
        if not path:
            return
        digest, accepted = QInputDialog.getText(self, "Verify publisher checksum", "Paste the SHA-256 obtained separately from the trusted publisher. Installation executes tool capability probes. No official runtime pack is distributed yet.")
        if accepted:
            self._local_operation(lambda: install(Path(path), digest.strip()), self._runtime_report)

    def show_setup(self):
        if self.busy:
            return
        from .setup_wizard import SetupWizard
        existing = getattr(self, '_setup_wizard', None)
        if existing is not None and existing.isVisible():
            existing.raise_()
            return
        self._setup_wizard = SetupWizard(self)
        self._setup_wizard.setAttribute(Qt.WA_DeleteOnClose)
        self._setup_wizard.finished.connect(lambda: setattr(self, "_setup_wizard", None))
        self._setup_wizard.open()

    def prepare_builtin_example(self):
        output = self.data_root / 'examples' / _fresh_name('builtin-example')
        self._start('prepare_example', {'output_dir': str(output)}, output=output)

    def check_tools(self):
        self._start("doctor", {})

    def build_example(self):
        output = self.data_root / "examples" / _fresh_name("example")
        self._start("build_example", {"output_dir": str(output)}, output=output)

    def validate_configuration(self):
        self.save_configuration(lambda config, command_path: self._start("validate", {"config": str(command_path)}))

    def start_run(self):
        def saved(config, command_path):
            def ready(output):
                self._prepare_progress(config.execution_budget)
                if self._start("run", {"config": str(command_path), "output_dir": str(output)}, output=output):
                    self.active_run = output
                    self.result_record = None
                    self.inspection = None
                    self.navigation.setCurrentRow(2)
            self._local_operation(lambda: self.project.new_run_directory("run"), ready)
        self.save_configuration(saved)

    def _prepare_progress(self, budget):
        self.progress_bar.setRange(0, budget)
        self.progress_bar.setValue(0)
        self.attempts_table.setRowCount(0)
        self.log.clear()
        self.accounting_label.setText("Charged attempts: 0 • completed observations: 0 • infrastructure failures: 0")
        self.progress_label.setText("Starting supervised worker. Inputs are injected only after firmware initialization.")

    def cancel_job(self):
        if self.controller.busy and self.controller.cancel():
            self.cancel_button.setEnabled(False)
            self.status_label.setText("Cancellation requested; waiting for debugger/process cleanup and saved accounting.")

    def _event(self, event):
        kind = event.get("kind")
        payload = event.get("payload", event)
        if kind == "accepted":
            self.log.appendPlainText("Worker accepted: " + str(payload.get("command", self._job)))
            return
        if kind not in {None, "progress"}:
            return
        if payload.get("type") == "trial_complete":
            accounting = payload.get("accounting") or {}
            count = accounting.get("attempted_executions", 0)
            self.progress_bar.setValue(count)
            self.accounting_label.setText(
                f"Charged attempts: {count} • completed observations: {accounting.get('successful_executions', 0)} "
                f"• infrastructure failures: {accounting.get('infrastructure_failures', 0)}"
            )
            feedback = payload.get("feedback") or {}
            observation_label = {"safe": "Condition not observed", "triggered": "Configured failure", "infrastructure_failure": "Infrastructure failure"}.get(feedback.get("status"), str(feedback.get("status", "unknown")))
            signature = feedback.get("execution_signature") or feedback.get("signature") or {}
            if self.attempts_table.rowCount() >= 500:
                self.attempts_table.removeRow(0)
            row = self.attempts_table.rowCount()
            self.attempts_table.insertRow(row)
            for column, text in enumerate((str(count), json.dumps(payload.get("input")), observation_label, str(signature.get("digest", signature.get("sha256", ""))))):
                self.attempts_table.setItem(row, column, QTableWidgetItem(text))
            self.attempts_table.scrollToBottom()
            self.progress_label.setText(f"Last observation: {observation_label} for {payload.get('input')}")
        else:
            stage = payload.get("stage") or payload.get("type") or "runtime event"
            self.progress_label.setText(str(stage).replace("_", " ").capitalize())
        self.log.appendPlainText(json.dumps(payload, sort_keys=True))

    def _result(self, result):
        command = self._job
        if command in {"doctor", "validate", "build_example", "prepare_example", "setup_runtime", "rollback_runtime", "runtime_history", "export"} and result.get("success") is False:
            self._error({"category": "operation_failed", "message": "The operation returned a failed result.", "details": result})
            return
        if command == "doctor":
            self.tool_details.setPlainText(_json(result))
            identities = result.get("tools", {}).get("identities", {})
            versions = " • ".join(str(identities[name].get("version", name)) for name in ("qemu", "gdb") if name in identities)
            platform_note = "Native firmware execution remains unsupported." if result.get("native_execution") == "unsupported" else "Guest compatibility is checked during execution."
            self.tool_status.setText((versions or "Runtime capability report received.") + "\n" + platform_note + " The built-in example requires no compiler.")
        elif command in {"setup_runtime", "runtime_history", "rollback_runtime"}:
            self._runtime_report(result)
        elif command == "validate":
            self.validation_text.setPlainText("Validation passed. Guest compatibility still requires execution.\n\n" + _json(result))
        elif command in {"build_example", "prepare_example"}:
            config = load_config(result["config_file"])
            root = self.data_root / "projects" / _fresh_name("example-project")
            # Controller is still completing cleanup. Import starts after idle.
            self._pending_example = (root, config)
            self.tool_details.setPlainText(("Verified example image prepared without compilation" if command == "prepare_example" else "Independent example compiled") + "; importing project after worker cleanup.\n\n" + _json(result))
        elif command in {"run", "restart", "reproduce"}:
            self.active_run = self._job_output
            self.inspection = None
            self._show_result(result)
        elif command in {"inspect", "recover"}:
            self.inspection = result
            self._show_result(result.get("result"), inspection=result)
        elif command == "export":
            self.status_label.setText("Export complete: " + str(self._job_output))
            self.log.appendPlainText("Report export: " + _json(result))
        if command != "export":
            self.status_label.setText("Operation finished; waiting for worker cleanup." if self.controller.busy else "Operation complete.")
        self._refresh_enabled()

    def _show_result(self, result, *, inspection=None):
        self.result_record = result
        self.run_path_label.setText(str(self.active_run) if self.active_run is not None else "No run selected")
        if result is None:
            self.outcome_label.setText("Incomplete run — no terminal result")
            self.trigger_label.setText("Triggering input: unavailable")
            self.evidence_label.setText("Inspect and explicitly recover interrupted state before restarting.")
            self.result_text.setPlainText(_json(inspection or {}))
            self.report_view.setPlainText("No terminal result exists. Unknown execution accounting remains unknown.")
        else:
            self.outcome_label.setText(str(result.get("outcome", result.get("state", "unknown"))).replace("_", " "))
            self.trigger_label.setText("Triggering input: " + json.dumps(result.get("triggering_input")))
            self.evidence_label.setText(
                "Measurement mode: " + str(result.get("measurement_mode", "unknown"))
                + " • execution evidence: " + str(result.get("execution_evidence", "unknown"))
                + " • state: " + str(result.get("state", "unknown"))
            )
            self.result_text.setPlainText(_json(inspection or result))
            self.report_view.setPlainText(_report(result))
            verification = (inspection or {}).get("accounting_verification", {})
            if verification.get("status") == "incomplete_receipts":
                self.evidence_label.setText(self.evidence_label.text() + " • execution verification failed: missing receipts")
        self.navigation.setCurrentRow(3)
        self._refresh_enabled()

    def _error(self, error):
        category = error.get("category", "unknown_error")
        message = error.get("message", "Operation failed.")
        self.status_label.setText(f"{category}: {message}")
        self.validation_text.setPlainText(_json(error))
        if self._job == "doctor":
            self.tool_status.setText(f"Runtime check failed: {message} ({category}). See installation instructions for platform dependencies.")
        self.log.appendPlainText("ERROR " + _json(error))
        details = error.get("details") or {}
        partial = details.get("partial_result")
        if self._job in {"run", "restart", "reproduce"} and self._job_output is not None:
            self.active_run = self._job_output
            self.result_record = None
            self.inspection = None
        if type(partial) is dict:
            self.inspection = partial
            self._show_result(partial.get("result"), inspection=partial)
        elif self._job in {"run", "restart", "reproduce"} and self._job_output is not None:
            self.active_run = self._job_output
            self.run_path_label.setText(str(self.active_run))
            self.outcome_label.setText("Operation failed — inspect persisted records")
            self.result_text.setPlainText(_json(error))
            self.report_view.setPlainText("Operation failed. Inspect retained records; no successful execution result is assumed.\n\n" + message)
            self.navigation.setCurrentRow(3)
        self._refresh_enabled()

    def _busy_changed(self, busy):
        self._refresh_enabled()

    def _idle(self):
        self._refresh_enabled()
        if not self.busy:
            self._job = None
            if self.status_label.text() == "Operation finished; waiting for worker cleanup.":
                self.status_label.setText("Operation complete. Results and retained evidence are available.")
        if self._closing and not self.busy:
            self.close()
            return
        pending = getattr(self, "_pending_example", None)
        if pending is not None and not self.busy:
            del self._pending_example
            root, config = pending
            self._local_operation(lambda: self._verified_project(DesktopProject.create(root, config.firmware, config)), self._adopt_project)

    def open_run(self, directory):
        if self.busy:
            return
        self.active_run = Path(directory)
        self.result_record = None
        self.inspection = None
        self._start("inspect", {"run_dir": str(self.active_run)})

    def _pick_run(self):
        directory = QFileDialog.getExistingDirectory(self, "Open saved product run")
        if directory:
            self.open_run(directory)

    def inspect_current_run(self):
        if self.active_run is not None:
            self._start("inspect", {"run_dir": str(self.active_run)})

    def _new_result_directory(self, kind):
        if self.project is not None:
            return self.project.new_run_directory(kind)
        return self.data_root / "runs" / _fresh_name(kind)

    def reproduce(self):
        if self.busy or self.active_run is None or not self.reproduce_button.isEnabled():
            return
        count = self.replay_spin.value()
        source = self.active_run
        def ready(output):
            self._prepare_progress(count)
            if self._start("reproduce", {"run_dir": str(source), "output_dir": str(output), "attempts": count}, output=output):
                self.navigation.setCurrentRow(2)
        self._local_operation(lambda: self._new_result_directory("reproduction"), ready)

    def export_result(self):
        if self.busy or self.active_run is None:
            return
        parent = QFileDialog.getExistingDirectory(self, "Choose parent folder for a new report export")
        if parent:
            try:
                output = _safe_root(Path(parent) / _fresh_name("firmavex-report"))
                self._start("export", {"run_dir": str(self.active_run), "output_dir": str(output)}, output=output)
            except ProductError as exc:
                self._error(exc.to_dict())

    def recover_current_run(self):
        if self.busy or self.active_run is None:
            return
        choice = QMessageBox.question(
            self, "Explicit interrupted-state recovery",
            "This marks interrupted accounting without executing firmware. Unknown work remains unknown. "
            "Completed records are retained. Continue?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if choice == QMessageBox.Yes:
            self._start("recover", {"run_dir": str(self.active_run)})

    def restart_current_run(self):
        if self.busy or self.active_run is None:
            return
        choice = QMessageBox.question(
            self, "Restart in a separate new run",
            "This restarts the strategy from the beginning in a new run folder. "
            "Previously attempted firmware work can repeat. The old run is retained. Continue?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if choice == QMessageBox.Yes:
            source = self.active_run
            budget = ((self.result_record or {}).get("accounting") or {}).get("execution_budget", self.budget_spin.value())
            def ready(output):
                self._prepare_progress(budget)
                if self._start("restart", {"run_dir": str(source), "output_dir": str(output)}, output=output):
                    self.navigation.setCurrentRow(2)
            self._local_operation(lambda: self._new_result_directory("restart"), ready)

    def closeEvent(self, event: QCloseEvent):
        if self._universal_window is not None:
            self._universal_window.close()
            if self._universal_window.busy:
                self._closing = True
                self.status_label.setText("Closing after backend cancellation, persistence, and worker cleanup…")
                event.ignore()
                return
        if self.busy:
            self._closing = True
            self.controller.shutdown()
            self.status_label.setText("Closing after cancellation, persistence, and worker cleanup…")
            self._refresh_enabled()
            event.ignore()
            return
        if not self.controller.shutdown():
            self._closing = True
            event.ignore()
            return
        event.accept()
