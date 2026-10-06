# Cortex-M3 benchmark builds (Step 15A)

The target is QEMU `mps2-an385`. Python 3.10+, native GCC,
`arm-none-eabi-gcc`, `qemu-system-arm`, and `arm-none-eabi-gdb` are required
for the complete test suite. A `gdb-multiarch` executable exposed as
`arm-none-eabi-gdb` is also compatible. On Debian the ARM compiler package is
`gcc-arm-none-eabi`; QEMU is `qemu-system-arm`.

From the repository root:

```sh
python -m pip install -r requirements.txt
python -m src.firmavex.benchmarks.cortex_m --output-dir build/cortex_m/v1
python -m pytest -q tests/test_cortex_m_benchmarks.py
python -m pytest -q
```

`build_cortex_m_firmware` is the single build implementation for both legacy
fixtures and corpus images. It uses Cortex-M3 Thumb instructions, `-g -O0`,
freestanding compilation, no standard library, the existing startup/vector
table and linker script, and no linker build ID. Every call rebuilds its inputs;
only a successful compilation replaces the destination. An output path that
resolves to a source or linker input is rejected before compilation. Failures return
`success=False`, a return code and compiler diagnostics. A missing toolchain
returns an installation/PATH hint. Output directories are created automatically.

Pytest session fixtures compile into fresh temporary directories. No test needs
manually generated `minimal.elf` or `failure_condition.elf` in this checkout.
The corpus CLI writes ignored build outputs. No ELF binaries are versioned.
With unchanged source paths and the same compiler, repeated builds are tested
for byte equality. Cross-toolchain or cross-checkout byte equality is not
promised; record compiler versions and the repository commit when comparing runs.

## Corpus version 1

`corpus/manifest.json` lists five programs: threshold, exact-value, bounded-range,
bit-mask, and arithmetic conditions. All share `corpus/harness.c`, unsigned
32-bit `firmavex_input` and `firmavex_failure` symbols, and the
`benchmark_complete` function breakpoint. The harness assigns failure to
exactly 0 or 1 before reaching that breakpoint. The shared evaluation input
domain is integers 0 through 255 inclusive. Each execution starts a fresh QEMU
instance; the existing monitor injects input while the CPU is stopped, before
`main`. The harness must not reset that input. This minimal startup relies on
QEMU loading the ELF RAM sections; these are emulator fixtures, not a complete
hardware startup implementation.

Legacy fixture symbols and source-line breakpoints remain supported. Monitor,
detector, search, reproduction, minimization, reporting and native compilation
behavior are preserved apart from infrastructure-failure hardening: search now
aborts on the first failed observation and returns diagnostics. Monitoring asks
the OS for an available IPv4 loopback port for each observation and passes that
port to both QEMU and GDB. It detects QEMU startup exits and cleans up on GDB
errors/timeouts. Port reservation must be released before QEMU binds, so a small
allocation-to-bind race remains. Runtime tests continue to run serially;
parallel execution has not been introduced or validated.

## Ground truth and fair evaluation

Build/instrumentation metadata contains no expected trigger, predicate,
trigger interval, recommended candidate, or expected execution count.
Evaluation-only ground truth lives in
`tests/data/cortex_m_v1_ground_truth.json`, with trigger intervals for the
entire declared domain and boundary test cases. The builder and runtime/search
modules never load that file. Changed predicate semantics require a corpus
version change and a matching evaluation oracle.

Future comparisons should give each strategy the same opaque firmware execution
interface, input domain, execution budget and feedback policy. Keep ground
truth, source, debug images and descriptive benchmark names in the evaluator;
do not give strategies filesystem access to these artifacts or the oracle.
The present separation is an API/data convention, not an access-control
boundary: source and symbols are necessarily inspectable in this development
checkout. A strategy that reads them would invalidate a black-box comparison.

Count each attempted firmware execution, including unsuccessful attempts,
using the existing search `execution_count`. A failed execution is an
infrastructure failure, not a confirmed non-trigger or a valid success result.
Report failures/no discovery and budget exhaustion explicitly. Report search
cost separately from reproduction and minimization costs. Reuse identical
candidate ordering for deterministic baselines; record random seeds for future
stochastic strategies. Ground truth may validate outcomes only after execution.
The tests exercise the existing ascending baseline over the common domain and
check executions-to-failure against the oracle after the search returns.
No guided search strategy is introduced here.
