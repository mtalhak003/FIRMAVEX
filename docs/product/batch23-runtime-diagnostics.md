# Batch 23A: Windows runtime qualification diagnostics

This change adds failure diagnostics, not a new runtime qualification. The
existing Windows x86-64 profile still requires the exact QEMU 11.1.2 and GDB 18.1
version strings and executable SHA-256 values in `platform_support.py`.
QEMU 11.1.3 remains rejected. Package acquisition and firmware execution are
unchanged; a checksum-pinned bootstrap does not pin later vendor package updates.

## Diagnostic contract

On Windows admission rejection, `ProductError.details.qualification` contains
the following bounded comparison. Successful admission creates no such record.

| Field | Meaning |
|---|---|
| `schema_version` | Diagnostic comparison schema, currently `1` |
| `required_profile`, `profile_version` | Existing admission profile; not an observed runtime identity |
| `host_architecture` | Allowlisted normalized architecture, or `unknown`; no host name |
| `tools.qemu.expected`, `tools.gdb.expected` | Required `version` and `sha256` from the unchanged gate |
| `tools.qemu.observed`, `tools.gdb.observed` | Version/hash captured by discovery, or `null` when unavailable or omitted |
| `tools.<name>.matches` | Per-field comparison; `null` when an observed field is unavailable |

Observed versions must exactly match a bounded numeric
`QEMU emulator version <version>` or `GNU gdb (GDB) <version>` format. Digests
must be 64 lowercase hexadecimal characters. Unknown suffixes, multiline output,
paths and malformed types are omitted, not copied or truncated. A `null` does
not mean a match and cannot open the gate. These rules sanitize diagnostics;
they do not replace or influence the existing exact admission comparison.

## Private vendor installation

Discovery captures identities before the rejected runtime-pack generation is
removed. The provider then saves the comparison in the existing exclusive JSON
diagnostic **before private vendor installation cleanup**. It reuses the existing
path/reparse-point checks, permissions, flush/fsync and error handling. The saved
JSON adds `qualification` and `vendor_packages` to the existing diagnostic schema.

`vendor_packages` contains only `mingw-w64-ucrt-x86_64-qemu` and
`mingw-w64-ucrt-x86_64-gdb-multiarch` package versions from the already collected
`pacman -Q` inventory. Supported numeric versions include the package release and
optional epoch. Missing, malformed, duplicate or unsupported entries become
`null`; oversized inventories are omitted. Other packages, the complete inventory,
environment, executable paths and raw vendor output are not added to this record.
Expected values are taken from application policy, never from error-supplied
claims. Publication reprojects only the allowlisted observed fields.

Diagnostics remain under the existing per-user
`FIRMAVEX/installation-diagnostics/runtime-setup-*.json` location. The Windows
setup workflow already retains this exact JSON pattern. The same failure is
reported after cleanup without writing a duplicate diagnostic. If persistence
fails, rejection remains in force, existing cleanup is attempted and
`diagnostic_write_failed` is reported. Previous valid generations, activation
pointers and user data are preserved.

KeyboardInterrupt/SystemExit from discovery or diagnostic persistence propagate
unchanged. An inherited vendor-cleanup limitation remains: an interruption in
private GPG-agent cleanup becomes `runtime_cleanup_failed` when there is no prior
error, or is suppressed into a note on the prior error. Subsequent private-tree
removal can therefore be skipped. Batch 23A does not repair this behavior and
does not guarantee cancellation propagation or complete cleanup in every phase.

## Limits and validation

The comparison explains why selected executables were rejected; it does not
authenticate their publisher, establish full DLL closure compatibility, prove
package-to-executable ownership or authorize a different runtime profile.
Package versions are observations from the vendor inventory, not independent
correspondence proof. No new package queries or workload executions are added.

Synthetic tests exercise the real gate, runtime-pack filesystem handling,
exclusive diagnostic writer and cleanup, with fake vendor commands/discovery.
They cover both tool mismatches, unavailable identities, successful admission,
discovery/persistence interruption, previous-generation preservation, diagnostic
write failure, bounded projection and publication hygiene. Malformed identity
containers still raise AttributeError in the inherited admission predicate;
their regression test documents that limitation without changing policy.
Package projection tests include the size boundary and optional epoch format.
These tests are not Windows native
qualification. A real Windows setup run is still needed to obtain the actual
private install's identities and confirm retained diagnostics after rejection.
