"""Actual product CLI/worker/evaluator execution, independent of research fixtures."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys


def test_supervised_real_firmware_demo_and_readonly_inspection(tmp_path):
    output = tmp_path / "product demonstration with spaces"
    completed = subprocess.run(
        [sys.executable, "-m", "firmavex.product.cli", "demo", "--output-dir", str(output)],
        capture_output=True, text=True, timeout=90,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    result = json.loads(completed.stdout)
    assert result["success"] and result["measurement_mode"] == "real_firmware"
    search, replay = result["search"], result["reproduction"]
    assert search["triggering_input"] == [2, 1]
    assert search["accounting"]["attempted_executions"] == 10
    assert search["accounting"]["successful_executions"] == 10
    assert replay["reproduction"]["matching_observations"] == 3
    assert replay["accounting"]["attempted_executions"] == 3
    assert not result["research_campaign_executed"]
    from firmavex.product.services import inspect_run
    from firmavex.product.store import RunStore
    for directory, expected in (("search", 10), ("reproduction", 3)):
        root = output / directory
        before = {path.name: (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns)
                  for path in root.iterdir() if path.is_file()}
        inspected = inspect_run(root)
        assert inspected["state"] == "completed" and inspected["attempts_recorded"] == expected
        with RunStore(root) as store:
            records = store.snapshot()["attempts"]
        for attempt in records:
            evidence = attempt["record"]["evidence"]
            assert evidence["measurement_mode"] == "real_firmware"
            assert evidence["cleanup_verified"]
            assert all(process["reaped"] for process in evidence["cleanup"]["processes"])
            assert evidence["firmware"]["sha256"] == search["firmware_sha256"]
        after = {path.name: (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns)
                 for path in root.iterdir() if path.is_file()}
        assert before == after
    export = output / "export"
    for line in (export / "SHA256SUMS").read_text().splitlines():
        checksum, name = line.split("  ", 1)
        assert hashlib.sha256((export / name).read_bytes()).hexdigest() == checksum
