# Batch 6: unified offline desktop

The **Backends** workspace in the desktop application's Backends menu uses the
same supervised worker as the existing ARM interface. Choose ARM Cortex-M3,
RISC-V RV32, or Verilog/Icarus. Controls describe the method accurately: ARM is
bounded firmware search, RV32 is a configured symbol observation, and Icarus is
an HDL testbench simulation, not firmware fuzzing.

## First run

1. Open Backends and select the target. Click **Check runtime**. Availability
   probes run actual host tools, but are not themselves guest qualification.
2. Use **Prepare example** for an integrity-verified compiler-free ARM or RV32
   image, or the product-owned counter testbench. No compiler is needed to run
   these examples. Alternatively import a compatible trusted project.
3. Read and explicitly acknowledge workload and runtime trust. Preparation
   does not check this acknowledgment automatically. Unknown/untrusted workloads
   are rejected; this application does not provide a verified hostile-input sandbox.
4. Execute, inspect progress, or cancel. A terminal record appears after worker
   cleanup. A configured trigger is distinct from an infrastructure failure.
5. Reproduce supported completed observations into a new run, or export a fresh
   directory containing JSON, readable report, bounded logs, checksums, and VCD
   waveforms when present. ARM exports also include authoritative SQLite records.
6. Reopen results from persistent workspace history, or open an existing run
   directory without executing it. Files are stored independently of application
   installation and upgrades. Existing ARM SQLite schema and commands are unchanged.

Closing a busy workspace requests cancellation and waits for process cleanup.
An admission without final result remains incomplete: an OS-held ownership lock
separates a running attempt from released ownership without inventing execution
counts. Legacy records without ownership evidence retain unknown lifecycle.
No automatic retry or resume dispatches firmware.

## Compatibility

- ARM: existing symbolized Cortex-M3 ELF project JSON, QEMU `mps2-an385`, mandatory
  ready/completion breakpoints, typed uint32 bindings and existing evaluator.
- RV32: ELF32 little-endian RV32IM, QEMU `virt`, 128 MiB RAM at `0x80000000`, typed
  `input_a`, `input_b`, `failure_flag`, `input_ready`, `benchmark_complete`.
  Two uint32 values; no automatic RISC-V fuzzing or new search strategy.
- HDL: one self-contained ASCII Verilog testbench, top `testbench`, Icarus
  SystemVerilog-2012 mode, explicit PASS/FAIL result. Waveform filename must be
  `waveform.vcd`. Includes and unsupported system tasks are rejected. This is
  neither synthesis nor physical FPGA validation. No VHDL support is claimed.

Application and backend launchers are frozen together; tools do not require a
separate Python installation. MIT example firmware is packaged with source
identities and image hashes. QEMU/GDB/Icarus binaries are **not bundled** in the
application. The Windows consented setup downloads publisher-signed MSYS2 packages
and retains notices and inventories. It now retains RV32 QEMU and Icarus components
without changing the existing ARM runtime-pack schema. Ubuntu packages use OS
runtime dependencies. macOS runtime instructions use Homebrew.

Windows RV32/HDL candidate qualification remains gated until actual native CI
has passed for the selected runtime. `FIRMAVEX_QUALIFY_BACKENDS=1` is an explicit
administrator qualification override, not proof of support or a trust bypass.
The existing Windows ARM runtime gate remains unchanged.

Installers remain unsigned; the macOS DMG is unnotarized. CI runner installation
and upgrade tests do not constitute qualification of every clean consumer OS,
Gatekeeper/SmartScreen experience, CPU architecture, or publisher runtime version.
See the final native qualification records for the combinations actually tested.

## Dependencies and offline operation

Ubuntu: `qemu-system-arm`, `qemu-system-misc`, `gdb-multiarch`, `iverilog`, plus Qt
host libraries installed by the Debian package. No ARM/RISC-V compiler is required
for bundled examples. Windows runtime setup is available in the workspace and
first-launch wizard; offline verified runtime packs remain supported. macOS:
`brew install qemu gdb icarus-verilog`. Readiness reports publisher guidance,
selected executable identities, versions and compatibility details.

After dependencies are installed, preparation, execution, history, inspection,
reproduction and export make no mandatory remote requests. GDB uses a dynamically
selected localhost port. No account, telemetry, hosted service or public API is
required. Runtime installation is a separate, consented online operation.

The headless equivalent remains available through `firmavex-backend` (installed
Python) or frozen `FIRMAVEX --firmavex-backends`. Execution/reproduction now require
`--trust trusted_example` or `--trust trusted_project`; omitted/untrusted labels
are rejected. `prepare-example --builtin` uses the compiler-free catalog. The
Batch 5 `execute(Request, output, cancel)` Python entry remains a trusted-caller
API for compatibility; product UI/worker entry points use `execute_trusted`.

## Security boundary and remaining risks

Trusted projects and administrator-trusted runtime executables run with the host
user's privileges. Trust acknowledgment is not a sandbox. Linux user namespaces
and bubblewrap are available in the development environment, but no independently
verified filesystem/network isolation policy is implemented for the combined
QEMU/GDB/toolchain worker. Windows Job objects provide ownership/resource controls,
not AppContainer isolation; macOS resource limits are not an OS security boundary.
**Do not use these adapters for hostile or unknown firmware, HDL or executables.**

Defense in depth includes strict regular-file/path checks, rejection of symlinks
and special files at protected boundaries, bounded stable reads, source snapshots
and trust revalidation, shell-free argv, fresh working directories, admission before
execution, deadline/output/artifact checks, CPU/memory/file limits where available,
and owned process-tree cleanup. Windows children cannot receive their private
launch admission before Job ownership is established. POSIX children receive
limits in a dedicated launcher before tool execution. These are not aggregate VM
quotas and deliberately escaped process groups are outside the supported model.

Exports verify artifact hashes, names, collisions and total retention limits before
creating output; no archive extraction or arbitrary relative path is accepted.
Observable capture races fail closed, but the filesystem is not locked atomically.
Logs, absolute paths and supplied metadata are administrator-owned and require
review/redaction before publication. Checksums do not authenticate an attacker-
modified installation or archive. Retention is bounded per run/export; there is no
automatic deletion of historical user runs.

No research protocol, benchmark predicate, ground truth, strategy, accounting
policy, campaign archive or original experimental result is changed. Product ARM
progress flushing exposes existing nonce-bound debugger diagnostics promptly;
it adds no guest instructions and changes no failure-observation/signature point.

## Native qualification procedure

`tools/universal_desktop_ci.py --output NEW_DIRECTORY [--engine FROZEN_CONSOLE]`
runs a fixed, small independent example plan. It verifies actual ARM triggering
and three reproductions, RV32 safe/triggering observations and replays, HDL pass
and deliberately failing assertions with VCD, and in-flight cancellation for all
three backends. Cancellation waits for actual debugger readback/simulator output,
not an executable name or a mock. Saved records, reports, logs and process cleanup
are independently checked. Outputs stay separate from research campaigns.

The unified-desktop GitHub workflow runs source GUI, source worker, frozen worker,
and installed application checks on Ubuntu x64, Windows x64 and Apple Silicon,
plus reinstall/removal checks preserving independently stored records. Native
qualification must succeed before claiming a platform/backend combination.

## Batch 6 qualification checkpoint

The Ubuntu x64 job in [run 38546993532](https://github.com/mtalhak003/FIRMAVEX/actions/runs/38546993532) passed actual source, frozen and installed ARM/RV32/HDL execution, reproduction, cancellation, persistence and export, including package reinstall/removal with retained results. This is example-based qualification, not arbitrary-target support.

The same workflow did **not** qualify native Windows or macOS multi-backend execution. Windows publisher package installation failed before execution. Darwin rejected RLIMIT_AS admission even when requested limits were below inherited caps; this remains a fail-closed limitation, not permission to omit memory controls. Older ARM-only macOS execution evidence does not qualify the new adapters. The Windows native compatibility catalog intentionally contains no approved entries until complete native evidence exists. Candidate qualification requires explicit administrator opt-in and conveys no support guarantee.

Installers remain unsigned/unnotarized unless a particular artifact supplies independently verifiable signing evidence. CI failures and partial results must be reviewed before beta distribution.

### Native regression repair and reproducible Darwin blocker

Failed run [38548476770](https://github.com/mtalhak003/FIRMAVEX/actions/runs/38548476770)
exposed two Windows filesystem assumptions. `DirEntry.stat()` can provide a zero
link count on Windows: artifact inventory now requests uncached, no-follow path
metadata and still rejects hardlinks, special files and reparse points. Windows
may defer file timestamp updates while handles remain open: bounded capture now
also rereads unbuffered bytes and rejects inconsistent content even if metadata
appears unchanged. Two matching reads are not an atomic snapshot or protection
against an adversarial writer. Original capture-race and artifact-limit tests
remain enabled; new regressions model the observed metadata behavior.

On Darwin the failure is **not** raising an inherited hard limit. XNU's
`RLIMIT_AS` admission returns `EINVAL` if the process's current virtual mapping
already exceeds the requested cap. The Python launcher can have a very large
virtual mapping on Apple Silicon. See Apple's `bsd/kern/kern_resource.c`,
`case RLIMIT_AS` and `vm_map_set_size_limit`. The launcher now records kernel
virtual/resident bytes on this failure; no fallback removes or enlarges the cap.
A smaller/native launcher or an independently qualified alternative memory
boundary needs separate implementation and native validation before support.

Reproduce the exact native regression step from an installed development checkout:

```sh
python tools/product_ci_tests.py -q tests/backends/test_records_security.py tests/backends/test_process_security.py tests/product/test_backend_services.py
```

The native workflow retains `native-security-regressions.log` even on failure.
Its pipeline propagates the test exit status; downstream qualification does not
run after failed admission checks. A failed macOS job remains failed, rather than
being converted into a skip or a support claim.
