# ADR 0002: capability-aware heterogeneous backends

- **Status:** retrospective record of implemented architecture.
- **Evidence date:** 2026-10-14 (Asia/Karachi), Batch 5 implementation and Batch 6
  desktop integration commits.
- **Record prepared:** 2026-11-09 (Asia/Karachi).

## Context and documented decision

The [Batch 5 backend record](../product/universal-backends.md) introduces a
Qt-independent `firmavex.backends` package with versioned immutable requests,
explicit target profiles and method capabilities. It distinguishes ARM project
search, RV32 symbol observation and Verilog assertion-testbench execution.
The [unified desktop record](../product/unified-desktop.md) later integrates these
contracts without presenting HDL simulation as firmware search.

The implemented decision is to share lifecycle, persistence, errors, cancellation
and evidence contracts while preserving backend-specific methods and inputs.
ARM delegates to existing product services and retains authoritative evaluator
accounting. Generic limits that cannot apply to the legacy ARM project are
rejected rather than silently ignored. The supported profiles are bounded
Cortex-M3 MPS2, RV32IM QEMU `virt`, and Icarus Verilog testbenches, not arbitrary
firmware, VHDL, synthesis or physical FPGA/hardware support.

## Recorded basis and consequences

The Batch 5 source explicitly identifies independence from Qt and frozen research
protocols, target compatibility and non-equivalent input methods. These are the
recorded design properties. It does not preserve a complete comparison of every
possible backend abstraction; no additional historical rationale is asserted here.

An admission without a terminal result remains incomplete, with unknown
accounting where appropriate. A trusted example/project declaration is required
on desktop execution paths; it is not OS authentication or a hostile-workload
sandbox. Offline operation means no required application account/service after
dependencies are installed, not verified network isolation.

## Implementation and validation references

- [Backend foundation a981066](https://github.com/mtalhak003/FIRMAVEX/commit/a9810669277dad8f531f2410f40c4638d610b0f7).
- [Authoritative ARM outcome repair d49a85e](https://github.com/mtalhak003/FIRMAVEX/commit/d49a85ebbefc53f76564fa5d2ae7f8e80ffc4632).
- [Unified desktop c8478ce](https://github.com/mtalhak003/FIRMAVEX/commit/c8478ce65af073e817994643afc885bd8a2a8f98).
- [Backend regressions](../../tests/backends/test_backends.py) and
  [process-security regressions](../../tests/backends/test_process_security.py)
  support implementation review. Native execution evidence remains profile,
  runtime, OS and source-revision specific.
- The [execution threat model](../security/execution-threat-model.md) records
  current trust and resource-boundary limitations.

## Remaining work

Qualify new targets, methods, native platforms and frozen/installed paths
independently. No API/remote worker or untrusted workload capability follows from
the shared interface alone. Use current readiness records rather than treating
the original Batch 5 capability table as a permanent support promise.
