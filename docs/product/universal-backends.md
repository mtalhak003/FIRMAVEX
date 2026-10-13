# Batch 5: offline backend foundation

## Implemented boundary

The new `firmavex.backends` package is independent of Qt and frozen research
protocols. Version-1 immutable requests select an explicit target profile;
capabilities distinguish project searches, symbol observations and HDL
assertion testbenches. `request_to_dict` / `request_from_dict` define a strict
local command record (unknown fields and versions are rejected). Local source
paths are not safe remote API inputs; a future service must implement upload,
authorization and isolated workers separately. No HTTP service is provided.

`Backend.execute(request, output, cancel)` owns preparation, tool subprocesses,
observation and cleanup. `execute()` reserves a new output directory, persists
an admission before dispatch, and commits a separate result by fsync and atomic
rename. It never overwrites a run or retries automatically. An admission without
result is **incomplete, with unknown execution accounting**; absence alone cannot
distinguish a running attempt from an interrupted one. Inspection does not
invent an outcome. This one-observation record is not the research campaign
journal and does not change evaluator-owned execution counts.

Cancellation events produce `cancelled` records; KeyboardInterrupt and SystemExit
persist cancellation diagnostics and are re-raised. Timeout, missing tools and
cleanup failure are infrastructure failures. HDL compile errors are invalid
inputs; missing/duplicate outcome markers or nonzero simulator exit are invalid
outputs. `triggered` denotes an observed firmware predicate or failed supplied
HDL assertion, not a security vulnerability or proof of design correctness.

ARM delegates to existing product `run_project` without changing configuration,
strategies, monitor, evidence or persistence. Its limits remain owned by the
legacy project JSON; nondefault generic limits are rejected rather than ignored.
New backends do not receive or modify research ground truth or partitions.

## Supported-target matrix

| Profile | Input/method | Real local qualification | Boundary |
|---|---|---|---|
| cortex-m3-mps2 | Existing project JSON, search | Linux; prior Batch 4 native Windows/macOS evidence remains separate | Symbolized Cortex-M3 ELF, QEMU mps2-an385; existing desktop and CLI |
| riscv32-virt | ELF, two uint32 values, one observation | Linux x86-64 | RV32IM, ELF32 little-endian ET_EXEC, QEMU virt RAM 0x80000000–0x87ffffff, one CPU |
| verilog-icarus | Single self-contained ASCII Verilog testbench | Linux x86-64 | Icarus SystemVerilog 2012 mode, top module `testbench`, no VHDL or physical FPGA |

New backends are **not natively qualified on Windows or macOS** in this batch.
Windows execution fails closed. POSIX code may work on macOS but tests on Linux
cannot establish that. WSL2/WSLg were not available here. The legacy GUI remains
ARM-specific; new execution is available through installed Python/headless CLI.
Frozen application execution of new backends is deliberately blocked pending a
proper dedicated launcher: frozen GUI executables cannot act as Python `-c`
resource-limit launchers. Existing ARM installers/workflows remain unchanged.

RISC-V requires typed global `input_a`, `input_b`, `failure_flag` (uint32),
functions `input_ready`, `benchmark_complete`, failure value 1, debug type
information, and separate ready/completion locations. GDB disables auto-load,
verifies stops and injected readback, then requires completion before observing
failure. No RISC-V signatures or automatic search strategy have been added.
QEMU tools are checked by actual invocation; tooling and image hashes, logs,
input values, completion and child reaping are recorded. Executable hashes identify
the selected command files, which can be wrappers, not necessarily every dynamic
library or executable reached through them.

HDL must print exactly one standalone `FIRMAVEX_TEST_RESULT=PASS` or `FAIL` and
exit zero. Optional waveforms must use `$dumpfile("waveform.vcd")`. The initial
profile rejects includes and unsupported system tasks. This lexical restriction
is a compatibility boundary, **not a sandbox** or a defense against malicious
HDL. A testbench can misreport its own assertions; the record proves tool
execution and captures its declared outcome, not independent design correctness.

## Ubuntu setup and demonstration

Use an installed source checkout or wheel, not the frozen desktop launcher:

```bash
sudo apt-get update
sudo apt-get install -y iverilog gcc-riscv64-unknown-elf qemu-system-misc gdb-multiarch
python -m pip install -e '.[dev]'
firmavex-backend profiles
# Each output path must be new. All outputs are outside the repository.
firmavex-backend prepare-example riscv32-virt --output "$HOME/firmavex-rv-build"
firmavex-backend execute riscv32-virt "$HOME/firmavex-rv-build/firmware.elf" \
  --values 2 1 --output "$HOME/firmavex-rv-trigger"
firmavex-backend reproduce "$HOME/firmavex-rv-trigger" --output "$HOME/firmavex-rv-replay"
firmavex-backend export "$HOME/firmavex-rv-trigger" --output "$HOME/firmavex-rv-report"
firmavex-backend prepare-example verilog-icarus --output "$HOME/firmavex-hdl-build"
firmavex-backend execute verilog-icarus "$HOME/firmavex-hdl-build/counter.v" \
  --output "$HOME/firmavex-hdl-run"
firmavex-backend inspect "$HOME/firmavex-hdl-run"
```

`prepare-example` compiles RV32 locally (source/compiler/flags/image identities in
`build.json`) or copies the HDL source, and never executes a guest. Fixed object
names and debug prefix maps make RV32 builds identical across two different local
output directories with the same toolchain, as tested; cross-version binary
identity is not promised. `tools/backend_qualification.py --output NEW_DIRECTORY`
performs only three fixed real observations plus one RV32 reproduction and records
small administration timings. It is not a controlled research campaign.

## Resource and evidence limits

New POSIX subprocesses have owned sessions, continuously drained bounded logs,
shared subprocess-phase wall deadline, per-child CPU limits (ceiling of wall timeout plus one second),
address-space limit (default 2 GiB), and file-size limit (default 16 MiB). Aggregate
artifact size is monitored while running and after HDL completion. These are
per-process limits and polling checks, not container-level quotas. A child can
escape a process group deliberately; hostile firmware/HDL/tool execution needs a
future sandbox/container or VM. Do not run untrusted projects with these adapters.
No network isolation is enforced; offline operation means no automatic dependency
downloads or remote execution, not denial of host network access.

TERM/KILL targets owned process groups and direct children are reaped, including
error/cancellation paths. A hard kill can leave an admitted run without result;
inspect reports it incomplete/unknown, and never resumes or replays implicitly.
Saved input hashes are checked before explicit fresh reproduction. JSON evidence,
REPORT.md and checksums can be exported into another new directory. Logs, paths
and diagnostics are administrative and require review/redaction for publication.
Checksums do not authenticate modified records or provide an atomic filesystem
snapshot. Run/result directories must remain user-owned and trusted.

## Licensing and packaging

No runtime binaries are added to Git, installers or wheels. Independent RV32 and
Verilog examples are MIT licensed. Icarus uses GPL-2.0-or-later; QEMU predominantly
GPL-2.0 with component exceptions; GDB is GPL-3.0-or-later; GCC is GPL-3.0-or-later
with runtime exceptions where applicable. Binutils and shared dependencies have
additional obligations. Obtain dependencies from signed OS packages. Exact
component notices/source obligations must be audited before any future binary
redistribution; this batch is not a legal clearance for bundling. Existing Qt,
PyInstaller and Batch 4 runtime notices and license limitations still apply.

## Next steps

Qualify native macOS and Windows tools and resource ownership before enabling
execution there; implement a dedicated frozen native launcher and GUI target
selection; introduce sandboxing and stronger artifact inventories; generalize
RISC-V symbol/config schemas and bridge observation backends to the established
public evaluator/strategies without changing frozen research settings. Additional
boards, BIN files, hardware, VHDL, FPGA synthesis and remote services are unsupported.

## Measured administration cost (Linux development environment)

A predeclared three-observation pilot on this host recorded RV32 safe **0.3159 s**,
RV32 triggering **0.3191 s**, and HDL pass **0.1282 s**, including tool version
probes, startup, observation and cleanup. These are individual observations, not
throughput estimates, platform comparisons or search-strategy measurements.
The same script measured median SHA-256 of 1 MiB at **0.688 ms** and serialization
of the three observation summaries at **0.0141 ms** (five repetitions of 1,000
operations each). SHA-256 already uses a native implementation. These measurements
do not justify introducing another C++20 component, build chain or ABI boundary.
Future profiling should target demonstrated orchestration or artifact bottlenecks
before considering native code. Raw pilot records remain separate from research
campaigns; the qualification script allows independent reproduction with new
outputs and records the actual host/revision/tool identities.
