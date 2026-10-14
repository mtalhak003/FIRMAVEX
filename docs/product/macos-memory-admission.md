# macOS Apple Silicon memory-admission investigation

Status: **native unified execution is blocked**. This document separates measured
facts, source inspection and unqualified alternatives. No sandbox is claimed.

## Established failure

At commit `993a506e4c082645d1a48644670aa9a2a4c78fe2`,
[native job 115924665349](https://github.com/mtalhak003/FIRMAVEX/actions/runs/38585048563/job/115924665349)
recorded Python-launcher virtual mappings of 420,837,490,688 bytes. Requested
address-space caps were 134,217,728 and 2,147,483,648 bytes. Resident memory was
about 21 MiB. Virtual mappings are not physical RAM consumption.

The job retained `native-security-regressions.log` in
`FIRMAVEX-macos-14-unified-native-evidence`. The cloud's GitHub artifact/API
endpoint denied access when fetching that ZIP, so the initial inspection used
its published pytest tracebacks and kernel diagnostics, not an invented local
copy of the retained log. New native probe records are also published as Actions
notices and retained in a separate investigation artifact directory.

XNU rejects lowering the limit below the current map size. In the released
[xnu-10002.81.5 resource implementation](https://github.com/apple-oss-distributions/xnu/blob/xnu-10002.81.5/bsd/kern/kern_resource.c),
`RLIMIT_AS` delegates to `vm_map_set_size_limit`; its
[VM implementation](https://github.com/apple-oss-distributions/xnu/blob/xnu-10002.81.5/osfmk/vm/vm_map.c)
returns failure when `new_size_limit < map->size`. BSD returns `EINVAL`; CPython
renders that as `ValueError: current limit exceeds maximum limit`. This error is
not evidence that FIRMAVEX tried to raise the inherited hard limit. The same VM
source applies a current-map-size check to `vm_map_set_data_limit`.

## Alternatives and required evidence

| Option | Actual property / outstanding question |
|---|---|
| Small C launcher | Removes Python/Qt startup cost; does not inherently remove dyld/allocator VM reservations. Must measure its mapping and admit the unchanged cap, then exec a target successfully. |
| Separately supervised native launcher | Can own/reap children and keep Python out of the child, but supervision alone adds no kernel memory ceiling. A watch-and-kill resident sampler permits overshoot and is not an equivalent hard admission cap. |
| Disable nano allocator | Could reduce reservations; cannot be assumed effective or sufficient. Native probe compares default versus `MallocNanoZone=0`, without changing the production environment. |
| `RLIMIT_DATA` | Different resource semantics; not automatically an address-space replacement. Native admission and allocation enforcement would need qualification. XNU source also checks existing map size at admission. |
| Mach footprint limit | Physical-footprint rather than address-space semantics. `task_set_phys_footprint_limit` checks `proc_check_footprint_priv`; a successful call still does not demonstrate fatal enforcement or descendant coverage. |
| Memorystatus fatal limits | Kernel source requires root or an appropriate entitlement for setting limits. Probe attempts self only, never requests elevation or changes another process. Availability or an API success alone does not qualify enforcement. |
| Privileged helper / Linux VM | Potential separate product architecture, installation and security-review work. Not implemented and not a routine fallback. |

See Apple's [task implementation](https://github.com/apple-oss-distributions/xnu/blob/xnu-11215.41.3/osfmk/kern/task.c)
and [memorystatus implementation](https://github.com/apple-oss-distributions/xnu/blob/xnu-11215.41.3/bsd/kern/kern_memorystatus.c)
for privilege and fatal-limit paths. Kernel releases differ; the native probe
records the actual kernel, OS, compiler, source and executable hashes.

## Reproduce the bounded investigation

On an actual macOS development checkout with Apple clang/SDK:

```sh
python -m tools.darwin_memory_probe --output /tmp/firmavex-memory-investigation-new
python tools/product_ci_tests.py -q tests/backends/test_records_security.py tests/backends/test_process_security.py tests/product/test_backend_services.py
```

The first command requires a fresh output directory. It compiles an independent
small C executable and starts fresh processes for AS, DATA, Mach footprint and
memorystatus self-probes at both existing cap values, with default and disabled
nano allocator. AS/DATA admission is followed only by `/usr/bin/true` if admitted.
The helper has CPU/alarm bounds; the parent has deadlines, owned process groups
and reaping. It cannot dispatch caller-selected firmware. It writes
`investigation.json`, build output and the diagnostic executable outside the
repository. All observations are administrative native-OS measurements, **zero
firmware executions**, and not memory-enforcement or sandbox qualification.

The second command remains unchanged and can fail. Investigation does not replace
it or authorize downstream end-to-end checks after failed resource admission.

## Interim support policy recommendation

Until an independently enforceable, natively tested policy exists, designate
macOS Apple Silicon **desktop preview / native unified execution unsupported**.
A successful DMG build or GUI startup does not qualify execution. Retain failed
native qualification and publish its logs; do not mark the required checks skipped,
add requested bytes to the process baseline, use unlimited AS, or silently replace
a hard limit with polling. Prior ARM-only evidence must stay scoped to its tested
workflow; it does not qualify the Batch 6 universal resource contract.

Windows and Ubuntu qualification remain separate. Do not change their controls or
make their availability depend on macOS passing. A future macOS solution needs
actual over-limit refusal/termination and descendant tests, source/frozen/installed
ARM/RV32/HDL execution, GUI, cancellation, reproduction, cleanup, exports and
upgrade/removal checks before revising this recommendation.
