"""Recent-shortcut recovery uses real files; no firmware is dispatched."""
import json
import os

import pytest

from firmavex.desktop import recents
from firmavex.product.errors import ProductError


@pytest.mark.parametrize('raw', [b'not JSON', b'[]', b'{"schema_version":true,"paths":[]}',
    b'{"schema_version":1,"paths":[],"paths":[]}', b'{"bad":NaN}', b'\xff', b'x'*65537],
    ids=['invalid-json', 'wrong-container', 'boolean-version', 'duplicate-fields',
         'nonfinite-json', 'invalid-utf8', 'over-byte-limit'])
def test_explicit_clear_recovers_invalid_preferences_without_reading_projects(tmp_path, raw):
    preferences = tmp_path/'preferences'; preferences.mkdir()
    index = preferences/'recent-projects.json'; index.write_bytes(raw)
    project = tmp_path/'project'; project.mkdir()
    saved = project/'saved-result.json'; saved.write_bytes(b'authoritative user bytes')
    with pytest.raises((ProductError, ValueError)):
        recents.load(preferences)
    recents.clear(preferences)
    assert recents.load(preferences) == []
    assert json.loads(index.read_text()) == {'schema_version': 1, 'paths': []}
    assert saved.read_bytes() == b'authoritative user bytes'


def test_clear_does_not_open_or_delete_shortcut_targets(tmp_path, monkeypatch):
    preferences = tmp_path/'preferences'
    one = tmp_path/'one'; two = tmp_path/'two'
    recents.remember(preferences, one); recents.remember(preferences, two)
    # Preference operations must not stat/open remembered target paths.
    from pathlib import Path
    original_stat = Path.stat
    def stat(path, *args, **kwargs):
        if path in (one, two): pytest.fail('Shortcut targets must remain untouched')
        return original_stat(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'stat', stat)
    recents.clear(preferences)
    assert recents.load(preferences) == []


def test_forget_removes_exact_selected_shortcut_only(tmp_path):
    preferences = tmp_path/'preferences'
    first = tmp_path/'project'; second = tmp_path/'project-copy'
    first.mkdir(); second.mkdir()
    one = first/'saved-result.json'; one.write_bytes(b'first result')
    two = second/'saved-result.json'; two.write_bytes(b'second result')
    recents.remember(preferences, first); recents.remember(preferences, second)
    assert recents.forget(preferences, str(first)) is True
    assert recents.load(preferences) == [str(second)]
    assert one.read_bytes() == b'first result' and two.read_bytes() == b'second result'
    assert first.is_dir() and second.is_dir()


def test_forget_missing_shortcut_is_read_only_and_does_not_create_preferences(tmp_path, monkeypatch):
    root = tmp_path/'preferences'
    monkeypatch.setattr(recents, '_write', lambda *args: pytest.fail('No preference write expected'))
    assert recents.forget(root, tmp_path/'missing-project') is False
    assert not root.exists()


@pytest.mark.parametrize('project', [None, False, [], '', 'bad\npath'])
def test_forget_invalid_selection_does_not_create_preferences(tmp_path, project):
    root = tmp_path/'preferences'
    with pytest.raises(ValueError): recents.forget(root, project)
    assert not root.exists()


def test_forget_does_not_implicitly_repair_corrupt_index(tmp_path):
    index = tmp_path/'recent-projects.json'; index.write_bytes(b'corrupt preference data')
    with pytest.raises(ProductError): recents.forget(tmp_path, tmp_path/'project')
    assert index.read_bytes() == b'corrupt preference data'


@pytest.mark.parametrize('operation', ['clear', 'forget'])
def test_preference_replacement_failure_preserves_previous_index(tmp_path, monkeypatch, operation):
    root = tmp_path/'preferences'
    selected = tmp_path/'project'; recents.remember(root, selected)
    index = root/'recent-projects.json'; before = index.read_bytes()
    from firmavex.backends import engine
    def denied(*args): raise OSError('replacement denied')
    monkeypatch.setattr(engine.os, 'replace', denied)
    with pytest.raises(OSError, match='replacement denied'):
        recents.clear(root) if operation == 'clear' else recents.forget(root, selected)
    assert index.read_bytes() == before
    assert not list(root.glob('*.tmp'))


@pytest.mark.parametrize('control', [KeyboardInterrupt, SystemExit])
def test_clear_interruption_preserves_original_exception_and_previous_preferences(tmp_path, monkeypatch, control):
    root = tmp_path/'preferences'
    recents.remember(root, tmp_path/'project')
    index = root/'recent-projects.json'; before = index.read_bytes()
    from firmavex.backends import engine
    original = control('original shortcut reset interruption')
    def interrupted(*args): raise original
    monkeypatch.setattr(engine.os, 'replace', interrupted)
    with pytest.raises(control) as caught: recents.clear(root)
    assert caught.value is original
    assert index.read_bytes() == before
    assert not list(root.glob('*.tmp'))


def test_clear_rejects_linked_index_without_touching_target(tmp_path):
    target = tmp_path/'target'; target.write_bytes(b'not shortcut preferences')
    root = tmp_path/'preferences'; root.mkdir()
    try: (root/'recent-projects.json').symlink_to(target)
    except OSError: pytest.skip('Host does not permit symlinks')
    with pytest.raises(ValueError): recents.clear(root)
    assert target.read_bytes() == b'not shortcut preferences'


def test_clear_rejects_hardlinked_index_without_touching_alias(tmp_path):
    target = tmp_path/'target'; target.write_bytes(b'not shortcut preferences')
    root = tmp_path/'preferences'; root.mkdir()
    try: os.link(target, root/'recent-projects.json')
    except OSError: pytest.skip('Host does not permit hardlinks')
    with pytest.raises(ValueError): recents.clear(root)
    assert target.read_bytes() == b'not shortcut preferences'


def test_clear_rejects_directory_instead_of_index(tmp_path):
    root = tmp_path/'preferences'; root.mkdir()
    index = root/'recent-projects.json'; index.mkdir()
    saved = index/'keep'; saved.write_bytes(b'preserve')
    with pytest.raises(ValueError): recents.clear(root)
    assert saved.read_bytes() == b'preserve'


@pytest.mark.parametrize('operation', ['clear', 'forget'])
def test_preferences_cannot_write_inside_application_checkout(operation):
    from pathlib import Path
    root = Path(recents.__file__).resolve().parents[2]
    with pytest.raises(ProductError, match='outside'):
        recents.clear(root) if operation == 'clear' else recents.forget(root, root/'project')
