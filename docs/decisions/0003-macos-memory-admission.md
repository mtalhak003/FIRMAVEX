# ADR 0003: preserve failed macOS memory admission and preview-only status

- **Status:** retrospective record of a documented support restriction.
- **Evidence date:** 2026-10-14 (Asia/Karachi), native investigation commits.
- **Record prepared:** 2026-11-09 (Asia/Karachi).

## Context and documented decision

The [macOS memory-admission investigation](../product/macos-memory-admission.md)
records native Apple Silicon failures when applying the existing address-space
caps. Its retained account separates large virtual mappings from resident RAM,
kernel admission errors from firmware behavior, and probe results from enforceable
memory isolation.

The documented policy is **macOS Apple Silicon desktop preview; native unified
execution unsupported** until a separately qualified enforcement design exists.
Do not increase/disable the caps, replace a hard bound with unqualified polling,
skip a required failed check or infer execution support from GUI/DMG success.
Earlier ARM-only workflow observations do not qualify the later universal
resource contract.

## Recorded reasoning and alternatives

The investigation documents that XNU rejects a limit below the current map size.
It then compares a small C launcher, allocator settings, `RLIMIT_DATA`, Mach
footprint limits and memorystatus calls. Its native probe did not establish an
unprivileged substitute: address-space/data admission failed, Mach access was
denied, and memorystatus lacked the required privilege. A smaller resident
launcher did not remove the measured virtual-map problem.

These are the retained findings and stated recommendation, not a claim that every
possible macOS architecture was disproved. A privileged helper or VM is future
design work requiring explicit installation/security review. Windows and Ubuntu
support must remain independently scoped rather than being weakened to match
this failure.

## Evidence references

- [Investigation implementation 8ab7f41](https://github.com/mtalhak003/FIRMAVEX/commit/8ab7f41d253f95e397a9b45eb178ebe4b963ecd3).
- [Findings/evidence record 0d3011a](https://github.com/mtalhak003/FIRMAVEX/commit/0d3011abbe2f6b9b1b758d067ad7bb566f81ac66).
- [Retained native job reference 115942649651](https://github.com/mtalhak003/FIRMAVEX/actions/runs/38590177869/job/115942649651),
  cited by the investigation. This ADR summarizes the retained source record; it
  does not claim a new independent download/review of that job's original artifact.
- [Current threat-model platform boundary](../security/execution-threat-model.md).

## Remaining work

Any policy revision needs real target-OS over-limit/descendant enforcement tests,
then source, frozen and installed ARM/RV32/HDL journeys, GUI, cancellation,
reproduction, cleanup and exports. Until that evidence exists, preserve the
failure and preview restriction. No new native test was run for this ADR.
