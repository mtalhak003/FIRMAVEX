# Batch 3 distribution candidates and runtime management

This branch is a development candidate, not a public beta. Frozen research
protocols, results and campaigns are unchanged. Runtime installation is distinct
from firmware qualification. The existing native Windows execution gate remains.

## Compatibility boundaries

| Platform | Application packaging | Actual ARM execution |
| --- | --- | --- |
| Linux x86-64 | Portable PyInstaller directory/tar, built on Linux | Tested on this Linux cloud host; see validation report |
| Windows x86-64 | Per-user Inno Setup candidate, unsigned | Blocked pending native ARM/GDB qualification |
| macOS | Native `.app` and unnotarized DMG candidates | Independent example passed native macOS CI; broader/bundled firmware qualification pending |
| WSL2/WSLg | Linux package needs WSLg display and compatible Linux libraries | Not tested on an actual WSL host in this batch |

Only symbolized ELF32 little-endian Cortex-M3 images with supported DWARF uint32
inputs, explicit input-ready/completion functions and configured failure symbol
are supported. QEMU's `mps2-an385` peripherals/memory map must match the firmware.
BIN, arbitrary boards, hardware, Cortex-M4/M7, and sandboxing untrusted firmware
are unsupported. macOS architecture follows the build host; no universal binary
or Intel/Apple Silicon equivalence is implied. GUI startup is not firmware proof.

## Runtime availability and redistribution

The executing engine requires QEMU with `mps2-an385` and ARM-capable GDB with
embedded Python and hashlib. Building the example additionally requires ARM GCC.
A GDB executable that lacks Python is insufficient even if it understands ARM.

Official QEMU and Arm download sites could not be retrieved in this cloud
(network proxy returned 403). No vendor ZIP, checksum, Windows ARM-capable GDB
build, or portable macOS dependency closure has therefore been qualified here.
Do not distribute guessed binaries or imply an official runtime pack exists.
The macOS qualification workflow passed using Homebrew-installed candidates; this is
not a redistribution solution for ordinary users.

QEMU/GDB/GCC have GPL obligations; Qt/PySide6 has separate LGPL/GPL/commercial
terms. Before distributing binaries, review exact component licenses and
corresponding-source obligations, include notices/source or compliant offers,
retain Qt replacement rights, and inventory every dependency. A manifest's
`source_offer` text alone does not establish legal compliance. The MIT project
license does not relicense third-party runtime components.

## Install and first launch

Download this branch's **Desktop distribution candidates** Actions artifact for
your OS. Artifacts require a GitHub login and have retention limits. Extract the
outer Actions ZIP, verify the included SHA256SUMS against the package bytes.
Checksums detect corruption; authenticate the publisher/channel separately.

* Windows: run `FIRMAVEX-Windows-unsigned.exe`. It installs for the current user,
  creates a Start menu entry, and optionally a desktop shortcut. Native testing
  remains blocked. Unsigned packages may prompt SmartScreen; do not disable OS
  security controls. GUI/installer CI checks are separate from ARM qualification.
* Linux: extract the portable tar into a user-owned applications directory and
  launch `FIRMAVEX/FIRMAVEX`. Compatible host display, GL and libc are required;
  this is not an AppImage or a guarantee for all distributions.
* macOS: open the unnotarized DMG and copy FIRMAVEX.app to Applications. It is
  not Developer-ID signed or notarized. Gatekeeper may prevent launch; public
  distribution requires signing/notarization before ordinary-user readiness.

The executable includes Python and Qt, but **does not bundle QEMU/GDB/GCC yet**.
The console subsystem is retained for the supervised worker; a Windows console
window is a known UX limitation. No firmware is run merely by opening the app.

On Welcome, choose **Check runtime tools**. Existing PATH tools and explicit
project tool paths remain usable. Install/repair a trusted runtime ZIP only when
its separately published SHA-256 and publisher are trusted. The GUI hashes the
ZIP, validates extraction, checks all inventoried files, then executes capability
probes. This executes third-party native code; it is not a sandbox. If no pack
is installed, **Verify installed runtime pack** reports an empty tool inventory;
that does not mean the runtime is ready. Follow it with Check runtime tools.

## Runtime pack schema 1

ZIP members are files only (no directory entries, links, special files, encrypted
members, duplicate/case-colliding paths, traversal, or reserved Windows names).
Maximum 20,001 members including runtime.json; at most 2 GiB expanded content.
Every file except runtime.json must appear in `files` with lowercase SHA-256.
Example manifest shape (placeholder hashes are not usable):

```json
{
  "schema_version": 1,
  "id": "publisher-runtime-version",
  "host": {"os": "linux", "arch": "x86_64"},
  "tools": {"qemu": "bin/qemu-system-arm", "gdb": "bin/arm-none-eabi-gdb"},
  "files": {"bin/qemu-system-arm": "<64 hex>", "bin/arm-none-eabi-gdb": "<64 hex>", "LICENSES.txt": "<64 hex>"},
  "licenses": ["LICENSES.txt"],
  "source_offer": "Exact corresponding source location and redistribution terms"
}
```

All DLLs/dylibs/shared libraries/data files must also be inventoried and have
working relocatable resolution. This importer does not construct that closure.
Compiler is optional, named `compiler` in tools. Pack selection is exact host
OS/CPU, not emulation-based. No qualification is inferred from host capabilities.

CLI alternative for an installed source package:

```sh
python -m firmavex.product.runtime_pack install runtime.zip --sha256 PUBLISHER_SHA256
python -m firmavex.product.runtime_pack verify
```

Frozen executable: replace `python -m firmavex.product.runtime_pack` with
`FIRMAVEX --firmavex-runtime`. Verification does not run firmware. Discovery
verifies the complete active inventory before using managed executables;
explicit project paths take precedence. A corrupt active pack fails closed.

Each successful repair activates a new UUID generation atomically via a pointer.
Old generations are retained so active runs are not deleted underneath them.
Failed installs leave activation unchanged. A directory lock prevents concurrent
installers; after a crash it must be inspected and removed manually only when
no installer owns it. Hash/identity checks do not provide an atomic filesystem
snapshot, prevent all adversarial races, or lock external executables.

## User data, upgrades and uninstall

Projects/results remain outside the application, under the per-user FIRMAVEX
application-data root by default, or in the user-selected project location.
Runtime generations live under that root's `runtimes` directory. Installers do
not remove those directories. Close jobs before upgrading. Back up projects and
results first. Windows upgrades reuse the same AppId; no data migration is
implemented. Linux upgrades replace the application directory; macOS replaces
the app bundle. Removing the application leaves user data intact. Manual deletion
of projects/results is separate and must be deliberate.

## Release gates

Before public beta: actual native Windows firmware qualification with a licensed,
checksum-pinned relocatable runtime; macOS Intel and Apple Silicon qualification;
actual WSLg tests; runtime binary/source supply chain; signed Windows installer;
Developer-ID signing/notarization; clean-VM install/upgrade/uninstall tests;
compiler-free example import; GUI-only launcher; offline setup/repair usability
and accessibility checks. CI artifacts remain unsigned development candidates.

### Additional Windows candidate investigation

The official MSYS2 MINGW-packages recipes are accessible through GitHub even
though this host cannot retrieve the package catalog. They define UCRT64 QEMU,
ARM GCC, and `gdb-multiarch` built with embedded Python and all targets. The
Windows candidate job installs these through MSYS2's normal signed-package feed,
then runs real adapter/input/timeout/cancellation tests. This is an investigation,
not a frozen or redistributed runtime pack. No signature checks are disabled.
The production Windows gate remains unchanged pending observed qualification
and integrated supervised desktop execution. Package recipes are not proof that
those binaries work or that their dependency closure is portable.
