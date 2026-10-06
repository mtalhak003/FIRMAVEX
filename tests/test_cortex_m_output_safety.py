from unittest.mock import Mock

import pytest

from src.firmavex.compiler import cortex_m


@pytest.mark.parametrize("destination", ["main.c", "extra.c", "startup.c", "linker.ld"])
@pytest.mark.parametrize("alias", [False, True])
def test_output_cannot_replace_any_build_input(tmp_path, monkeypatch, destination, alias):
    support = tmp_path / "support"
    support.mkdir()
    for name in ("startup.c", "linker.ld"):
        (support / name).write_text(f"original {name}\n")
    main = tmp_path / "main.c"
    extra = tmp_path / "extra.c"
    main.write_text("original main\n")
    extra.write_text("original extra\n")
    inputs = [main, extra, support / "startup.c", support / "linker.ld"]
    original = {path: path.read_bytes() for path in inputs}
    output = next(path for path in inputs if path.name == destination)
    if alias:
        link = tmp_path / "output.elf"
        link.symlink_to(output)
        output = link
    monkeypatch.setattr(cortex_m, "SUPPORT_DIR", support)
    compiler = Mock()
    monkeypatch.setattr(cortex_m.subprocess, "run", compiler)
    result = cortex_m.build_cortex_m_firmware(main, output, extra_sources=(extra,))
    assert result["success"] is False
    assert result["return_code"] == -1
    assert "Unsafe output path" in result["stderr"]
    assert "build input" in result["stderr"]
    compiler.assert_not_called()
    assert {path: path.read_bytes() for path in inputs} == original
