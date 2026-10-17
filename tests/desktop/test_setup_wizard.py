"""Synthetic GUI state tests; no firmware/platform qualification is inferred."""
import json
from pathlib import Path
import pytest
from PySide6.QtWidgets import QWizard
from tests.desktop.test_window import SyntheticController
from firmavex.desktop.window import MainWindow
from firmavex.desktop.setup_wizard import SetupWizard


@pytest.fixture
def setup(qtbot, tmp_path):
    controller = SyntheticController()
    window = MainWindow(controller, data_root=tmp_path / 'user data')
    qtbot.addWidget(window)
    wizard = SetupWizard(window)
    qtbot.addWidget(wizard)
    wizard.show()
    yield window, wizard, controller
    if controller.busy:
        controller.finish(error={'category':'cancelled','message':'synthetic cleanup','details':{}})
    wizard.reject(); window.close()


def test_opening_wizard_never_dispatches_firmware(setup):
    window, wizard, controller = setup
    assert controller.calls == []
    assert not wizard.ready
    assert 'Runtime' in wizard.runtime.status.accessibleName()


def test_runtime_check_must_pass_before_finish(setup):
    window, wizard, controller = setup
    wizard.accept()
    assert not (window.data_root / 'first-launch.json').exists()
    wizard.check()
    assert controller.calls[-1][0] == 'doctor'
    controller.finish({'success':True,'native_execution':'experimental','tools':{'identities':{}}})
    assert wizard.ready
    wizard.example.setChecked(False)
    wizard.accept()
    assert json.loads((window.data_root / 'first-launch.json').read_text())['firmware_executed'] is False
    assert all(command != 'run' for command, _ in controller.calls)


def test_failed_or_unqualified_runtime_cannot_complete(setup):
    window, wizard, controller = setup
    wizard.check()
    controller.finish({'success':True,'native_execution':'unsupported','tools':{'identities':{}}})
    assert not wizard.ready
    assert not wizard.runtime.isComplete()


def test_install_requires_explicit_consent_and_windows_host(setup, monkeypatch):
    window, wizard, controller = setup
    monkeypatch.setattr('firmavex.desktop.setup_wizard.host', lambda: {'os':'windows','arch':'x86_64'})
    wizard.refresh()
    assert not wizard.runtime.install.isEnabled()
    wizard.runtime.consent.setChecked(True)
    wizard.refresh()
    assert wizard.runtime.install.isEnabled()
    wizard.install()
    assert controller.calls[-1][0] == 'setup_runtime'
    assert not wizard.ready


def test_failed_generations_are_visible_but_cannot_be_selected(setup):
    window, wizard, controller = setup
    wizard.history()
    controller.finish({'success':True,'generations':[{'generation':'a'*32,'pack_id':'test','integrity':'verified','active':True},{'generation':'b'*32,'integrity':'failed','error':'checksum mismatch'}]})
    assert wizard.runtime.generations.count() == 1
    assert 'checksum mismatch' in wizard.runtime.status.text()
    wizard.restore()
    assert controller.calls[-1] == ('rollback_runtime', {'generation':'a'*32})


def test_cancel_waits_for_worker_cleanup(setup):
    window, wizard, controller = setup
    wizard.check()
    wizard.reject()
    assert controller.cancelled and wizard.pending_reject
    assert wizard.isVisible()
    controller.finish(error={'category':'cancelled','message':'synthetic cleanup','details':{}})
    assert not wizard.isVisible()


def test_finish_prepares_image_without_running_firmware(setup):
    window, wizard, controller = setup
    wizard.ready = True
    wizard.accept()
    assert controller.calls[-1][0] == 'prepare_example'
    assert all(command != 'run' for command, _ in controller.calls)


def test_install_method_cannot_bypass_consent(setup, monkeypatch):
    window, wizard, controller = setup
    monkeypatch.setattr('firmavex.desktop.setup_wizard.host', lambda: {'os':'windows','arch':'x86_64'})
    wizard.install()
    assert controller.calls == []


def test_preferences_write_error_leaves_wizard_open(setup, monkeypatch):
    window, wizard, controller = setup
    wizard.ready = True
    def denied(*args): raise PermissionError('read-only user storage')
    monkeypatch.setattr('firmavex.product.runtime_pack._atomic_json', denied)
    wizard.accept()
    assert wizard.isVisible()
    assert 'Cannot save' in wizard.runtime.status.text()
    assert controller.calls == []


def test_guidance_is_offline_and_does_not_claim_arbitrary_support(setup):
    window, wizard, controller = setup
    text = wizard.runtime.guidance.text()
    assert 'no account or internet' in text
    assert 'outside the application/runtime' in text
    assert wizard.runtime.guidance.accessibleName()
    assert controller.calls == []


@pytest.mark.parametrize('system,arch,expected', [
    ('windows', 'x86_64', 'Never disable signature checks'),
    ('linux', 'x86_64', 'portable archive does not install runtimes'),
    ('macos', 'arm64', 'Unified native execution is unsupported'),
    ('windows', 'arm64', 'no native qualification')])
def test_platform_setup_guidance_is_honest(system, arch, expected):
    from firmavex.product.setup_guidance import instructions
    assert expected in instructions({'os': system, 'arch': arch})
