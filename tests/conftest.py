from pathlib import Path

import pytest

from src.firmavex.benchmarks.cortex_m import build_benchmark, load_benchmarks
from src.firmavex.compiler.cortex_m import SUPPORT_DIR, build_cortex_m_firmware


@pytest.fixture(scope="session")
def cortex_m_firmware(tmp_path_factory):
    """Compile legacy runtime fixtures once, never use an ignored checkout ELF."""
    output_dir = tmp_path_factory.mktemp("cortex_m_legacy")
    images = {}
    for name in ("minimal", "failure_condition"):
        result = build_cortex_m_firmware(SUPPORT_DIR / f"{name}.c", output_dir / f"{name}.elf")
        assert result["success"], result["stderr"]
        images[name] = result["output_file"]
    return images


@pytest.fixture(scope="session")
def cortex_m_corpus(tmp_path_factory):
    output_dir = tmp_path_factory.mktemp("cortex_m_v1")
    images = {}
    for benchmark in load_benchmarks():
        result = build_benchmark(benchmark, output_dir / f"{benchmark.name}.elf")
        assert result["success"], result["stderr"]
        images[benchmark.name] = (benchmark, Path(result["output_file"]))
    return images
