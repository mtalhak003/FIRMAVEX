import json

import pytest

from firmavex.product import cli
from firmavex.product.errors import ProductError


def test_help_does_not_import_execution_services(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"])
    assert exc.value.code == 0
    assert "Cortex-M3" in capsys.readouterr().out


@pytest.mark.parametrize("argv,command,payload", [
    (["doctor"], "doctor", {}),
    (["validate", "config.json"], "validate", {"config": "config.json"}),
    (["run", "config.json", "--output-dir", "out"], "run", {"config": "config.json", "output_dir": "out"}),
    (["inspect", "old"], "inspect", {"run_dir": "old"}),
    (["recover", "old"], "recover", {"run_dir": "old"}),
    (["restart", "old", "--output-dir", "new"], "restart", {"run_dir": "old", "output_dir": "new"}),
    (["export", "old", "--output-dir", "new"], "export", {"run_dir": "old", "output_dir": "new"}),
    (["reproduce", "old", "--output-dir", "new"], "reproduce", {"run_dir": "old", "output_dir": "new", "attempts": 3}),
    (["demo", "--output-dir", "new"], "demo", {"output_dir": "new"}),
])
def test_cli_uses_supervised_dispatch(monkeypatch, capsys, argv, command, payload):
    from firmavex.product import supervisor
    calls = []
    def execute(self, name, values, **kwargs):
        calls.append((name, values))
        return {"status": "no_failure_observed_within_budget", "measurement_mode": "synthetic_test"}
    monkeypatch.setattr(supervisor.Supervisor, "execute", execute)
    assert cli.main(argv) == 0
    assert calls == [(command, payload)]
    assert json.loads(capsys.readouterr().out)["measurement_mode"] == "synthetic_test"


def test_structured_error_and_exit_status(monkeypatch, capsys):
    from firmavex.product import supervisor
    def execute(*args, **kwargs):
        raise ProductError("missing_tool", "No QEMU", {"name": "qemu"})
    monkeypatch.setattr(supervisor.Supervisor, "execute", execute)
    assert cli.main(["doctor"]) == 1
    assert json.loads(capsys.readouterr().out)["error"]["category"] == "missing_tool"


def test_cancelled_returns_130(monkeypatch, capsys):
    from firmavex.product import supervisor
    def execute(*args, **kwargs):
        raise ProductError("cancelled", "Interrupted")
    monkeypatch.setattr(supervisor.Supervisor, "execute", execute)
    assert cli.main(["run", "c", "--output-dir", "o"]) == 130


@pytest.mark.parametrize("attempts", ["0", "-1", "101"])
def test_invalid_reproduction_count_does_not_dispatch(monkeypatch, capsys, attempts):
    from firmavex.product import supervisor
    monkeypatch.setattr(supervisor.Supervisor, "execute", lambda *a, **k: pytest.fail("must not dispatch"))
    assert cli.main(["reproduce", "r", "--output-dir", "o", "--attempts", attempts]) == 1


@pytest.mark.parametrize("status,code", [
    ("failure_observed", 0), ("no_failure_observed_within_budget", 0),
    ("infrastructure_failure", 1), ("evidence_incomplete", 1), ("cancelled", 130),
])
def test_result_exit_semantics(status, code):
    assert cli._exit_status({"status": status}) == code
