from tools import desktop_ci_demo as wrapper


def test_failure_status_and_message_are_preserved(monkeypatch, capsys, tmp_path):
    def failed(args):
        print('{"success":false,"error":{"category":"worker_failure","message":"actual error","details":{}}}')
        return 1
    monkeypatch.setattr(wrapper, 'cli', failed)
    assert wrapper.main(['--output-dir', str(tmp_path / 'unused')]) == 1
    output = capsys.readouterr().out
    assert '::error title=Native supervised demonstration failure::' in output
    assert 'worker_failure' in output and 'actual error' in output
    assert not (tmp_path / 'unused').exists()


def test_success_is_not_changed_or_labeled_failure(monkeypatch, capsys, tmp_path):
    def succeeded(args):
        print('{"success":true}')
        return 0
    monkeypatch.setattr(wrapper, 'cli', succeeded)
    assert wrapper.main(['--output-dir', str(tmp_path / 'unused')]) == 0
    assert '::error' not in capsys.readouterr().out
