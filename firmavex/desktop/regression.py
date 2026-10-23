"""Explicit test-set editor and read-only results using the existing supervisor."""
import json
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QCheckBox,
    QPlainTextEdit, QFileDialog, QPushButton, QGridLayout, QScrollArea, QComboBox)

from .workflow import display_text


class RegressionPanel(QWidget):
    def __init__(self, host):
        super().__init__()
        self.host = host
        self.saved = None
        self.current_run = None
        self.previous_run = None
        self.pending = None
        self.loading = False
        self.buttons = []
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        scroll.setWidget(content)
        outer.addWidget(scroll)
        layout = QVBoxLayout(content)
        note = QLabel('Explicit regression sets: up to 16 RV32 or single-file Verilog entries. '
                      'Select a saved configuration in Configurations, then add it here. '
                      'Edits create a new revision; opening never executes. Infrastructure errors stop the set.')
        note.setWordWrap(True)
        layout.addWidget(note)
        saved_row = QHBoxLayout()
        self.saved_sets = QComboBox()
        self.saved_sets.setAccessibleName('Saved regression test-set revisions')
        saved_row.addWidget(self.saved_sets)
        saved_row.addWidget(self.button('List saved sets', lambda: self.start('list', root=str(self.host.data_root / 'testsets'))))
        saved_row.addWidget(self.button('Open listed set', self.open_listed))
        layout.addLayout(saved_row)
        self.name = QLineEdit()
        self.name.setMaxLength(80)
        self.name.setPlaceholderText('Test-set name')
        layout.addWidget(self.name)
        self.context = QLabel('No saved test set selected.')
        self.context.setWordWrap(True)
        self.context.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.context)
        self.entries = QTableWidget(0, 3)
        self.entries.setHorizontalHeaderLabels(['Entry name', 'Configuration revision', 'RV32 values (a,b)'])
        self.entries.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.entries.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.entries.setAccessibleName('Ordered regression test entries')
        layout.addWidget(self.entries)
        row = QGridLayout()
        for index, (label, handler) in enumerate( [('New set', self.new), ('Add selected configuration', self.add),
                               ('Replace configuration', self.replace), ('Remove', self.remove),
                               ('Move up', lambda: self.move(-1)), ('Move down', lambda: self.move(1))]):
            row.addWidget(self.button(label, handler), index // 2, index % 2)
        layout.addLayout(row)
        row = QHBoxLayout()
        self.save_button = self.button('Save new revision', self.save)
        self.open_button = self.button('Open test set…', self.open)
        row.addWidget(self.save_button); row.addWidget(self.open_button)
        self.trust = QCheckBox('I trust every input in this saved test set and the native runtime tools.')
        layout.addLayout(row)
        layout.addWidget(self.trust)
        row = QGridLayout()
        self.run_button = self.button('Run saved test set', self.run)
        row.addWidget(self.run_button, 0, 0)
        row.addWidget(self.button('Open results…', self.open_results), 0, 1)
        row.addWidget(self.button('Select previous run…', self.select_previous), 1, 0)
        self.compare_button = self.button('Compare with previous', self.compare)
        row.addWidget(self.compare_button, 1, 1)
        row.addWidget(self.button('Clear previous run', self.clear_previous), 2, 0)
        layout.addLayout(row)
        self.results = QTableWidget(0, 4)
        self.results.setHorizontalHeaderLabels(['Entry', 'Recorded outcome', 'Category', 'Evidence folder'])
        self.results.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.results.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.results.setAccessibleName('Read-only regression outcomes and evidence references')
        self.results.cellDoubleClicked.connect(self.open_entry)
        layout.addWidget(self.results)
        self.report = QPlainTextEdit()
        self.report.setReadOnly(True)
        self.report.setAccessibleName('Regression counts, revision identities and comparison')
        self.report.setMaximumHeight(180)
        layout.addWidget(self.report)
        self.name.textChanged.connect(self.edited)
        self.entries.itemChanged.connect(self.edited)
        self.trust.toggled.connect(self.refresh)
        self.dirty = True

    def button(self, label, handler):
        button = QPushButton(label)
        button.clicked.connect(handler)
        self.buttons.append(button)
        return button

    def edited(self, *_):
        if not self.loading:
            self.dirty = True
            self.trust.setChecked(False)
            self.context.setText('Unsaved changes. Save a new revision before execution.')
        self.refresh()

    def new(self):
        self.loading = True
        self.saved = None
        self.name.clear(); self.entries.setRowCount(0)
        self.loading = False
        self.edited()

    def _selected(self):
        return self.host._saved_configuration

    def _insert(self, entry, index=None):
        row = self.entries.rowCount() if index is None else index
        self.loading = True
        self.entries.insertRow(row)
        label = QTableWidgetItem(entry['name'])
        label.setData(Qt.ItemDataRole.UserRole, entry)
        revision = QTableWidgetItem(entry.get('configuration_revision', Path(entry['configuration']).name))
        revision.setFlags(revision.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.entries.setItem(row, 0, label)
        self.entries.setItem(row, 1, revision)
        self.entries.setItem(row, 2, QTableWidgetItem(','.join(str(v) for v in entry['values'])))
        self.loading = False

    def add(self):
        config = self._selected()
        if config and self.entries.rowCount() < 16:
            self._insert({'id': uuid4().hex, 'name': config['name'], 'configuration': config['configuration'],
                          'configuration_revision': config['identity'], 'values': config['request']['values']})
            self.edited()

    def replace(self):
        config, row = self._selected(), self.entries.currentRow()
        if config and row >= 0:
            identity = self.entries.item(row, 0).data(Qt.ItemDataRole.UserRole)['id']
            name = self.entries.item(row, 0).text()
            self.entries.removeRow(row)
            self._insert({'id': identity, 'name': name, 'configuration': config['configuration'],
                          'configuration_revision': config['identity'], 'values': config['request']['values']}, row)
            self.edited()

    def remove(self):
        row = self.entries.currentRow()
        if row >= 0:
            self.entries.removeRow(row)
            self.edited()

    def _values(self):
        entries = []
        for row in range(self.entries.rowCount()):
            metadata = self.entries.item(row, 0).data(Qt.ItemDataRole.UserRole)
            value = self.entries.item(row, 2).text().strip()
            if len(value) > 100:
                raise ValueError('Use two bounded uint32 values for RV32, or leave HDL values empty')
            values = [] if not value else [int(v.strip(), 0) for v in value.split(',')]
            entries.append({'id': metadata['id'], 'name': self.entries.item(row, 0).text(),
                            'configuration': metadata['configuration'], 'values': values})
        return entries

    def move(self, direction):
        row = self.entries.currentRow()
        target = row + direction
        if row < 0 or not 0 <= target < self.entries.rowCount():
            return
        try:
            entries = self._values()
            entries[row], entries[target] = entries[target], entries[row]
            self.entries.setRowCount(0)
            for entry in entries:
                self._insert(entry)
            self.entries.selectRow(target)
            self.edited()
        except ValueError as error:
            self.host._local_error(error)

    def start(self, action, **payload):
        if action == 'execute':
            self.results.setRowCount(0)
            self.current_run = None
            self.report.setPlainText('Waiting for the selected test-set run. No completed outcome is available yet.')
        self.pending = action
        if not self.host._start('backend_regression', {'action': action, **payload}, output=Path(payload['output_dir']) if 'output_dir' in payload else None):
            self.pending = None

    def save(self):
        try:
            payload = dict(root=str(self.host.data_root / 'testsets'), name=self.name.text(), entries=self._values())
            if self.saved:
                payload['parent'] = self.saved['directory']
            self.start('save', **payload)
        except ValueError as error:
            self.host._local_error(error)

    def open_listed(self):
        if self.saved_sets.currentData():
            self.start('open', directory=self.saved_sets.currentData())

    def clear_previous(self):
        self.previous_run = None
        self.trust.setChecked(False)
        self.report.setPlainText('Previous-run relationship cleared. The next explicit execution will be an original run.')
        self.refresh()

    def open(self):
        directory = QFileDialog.getExistingDirectory(self, 'Open a saved test-set revision without execution')
        if directory:
            self.start('open', directory=directory)

    def run(self):
        if self.saved and not self.dirty and self.trust.isChecked():
            output = Path(self.saved['directory']) / 'runs' / uuid4().hex
            payload = dict(directory=self.saved['directory'], output_dir=str(output), trust='trusted_project')
            if self.previous_run:
                payload['previous_run'] = self.previous_run['directory']
            self.start('execute', **payload)
            self.trust.setChecked(False)

    def open_results(self):
        directory = QFileDialog.getExistingDirectory(self, 'Open regression results without execution')
        if directory:
            self.start('inspect', directory=directory)

    def select_previous(self):
        directory = QFileDialog.getExistingDirectory(self, 'Select a previous regression run; does not execute or resume it')
        if directory:
            self.start('inspect', directory=directory)
            self.pending = 'previous'

    def compare(self):
        if self.previous_run and self.current_run:
            self.start('compare', left=self.previous_run['directory'], right=self.current_run['directory'])

    def receive(self, record):
        action, self.pending = self.pending, None
        if action == 'list':
            self.saved_sets.clear()
            for entry in record['entries']:
                self.saved_sets.addItem(display_text(entry['name'], 80) + ' · ' + entry['revision'][:12], entry['directory'])
            self.report.setPlainText('Listed at most 200 revisions. Open validates the selected entries and copied inputs; listing does not execute them.')
        elif action in ('open', 'save'):
            self.loading = True
            self.saved = record
            if self.previous_run and self.previous_run['set_id'] != record['set_id']:
                self.previous_run = None
            self.name.setText(record['name']); self.entries.setRowCount(0)
            for entry in record['entries']:
                self._insert(entry)
            self.loading = False
            self.dirty = False
            self.trust.setChecked(False)
            self.context.setText(display_text('Test set ' + record['set_id'] + '\nRevision ' + record['revision'] + '\nCreated ' + record['created_at'] + '\nFolder ' + record['directory'], 500))
        elif action == 'previous':
            self.previous_run = record
            self.trust.setChecked(False)
            self.report.setPlainText('Previous run selected: ' + record['run_id'] + '\n' + record['directory'])
        elif action in ('execute', 'inspect'):
            self.current_run = record
            self.results.setRowCount(len(record['entries']))
            for index, entry in enumerate(record['entries']):
                evidence = str(Path(record['directory']) / entry['evidence']) if entry['evidence'] else 'unavailable'
                for column, value in enumerate((entry['name'], entry['status'], entry['category'], evidence)):
                    item = QTableWidgetItem(display_text(value, 500))
                    item.setToolTip(display_text(entry['diagnostic'], 4096))
                    self.results.setItem(index, column, item)
            self.report.setPlainText(display_text('Test set ' + record['set_id'] + '\nRevision ' + record['revision'] +
                '\nRun ' + record['run_id'] + '\nFolder ' + record['directory'] + '\nRecorded state: ' + record['state'] + '\n' + json.dumps(record['counts']) +
                '\nDouble-click an entry to inspect retained evidence.\n' + record['scope'], 2000))
        elif action == 'compare':
            self.report.setPlainText(display_text(json.dumps(record, indent=2), 16000))
        self.refresh()

    def open_entry(self, row, _column):
        if self.current_run and not self.host.busy:
            entry = self.current_run['entries'][row]
            if entry['evidence']:
                self.host.inspect(Path(self.current_run['directory']) / entry['evidence'])

    def refresh(self, *_):
        idle = not self.host.busy and not self.host._closing
        for button in self.buttons:
            button.setEnabled(idle)
        self.saved_sets.setEnabled(idle)
        self.name.setEnabled(idle); self.entries.setEnabled(idle); self.trust.setEnabled(idle)
        self.run_button.setEnabled(idle and self.saved is not None and not self.dirty and self.trust.isChecked())
        self.compare_button.setEnabled(idle and self.previous_run is not None and self.current_run is not None)
