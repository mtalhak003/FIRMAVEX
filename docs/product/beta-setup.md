# Batch 4: first launch, runtimes and beta boundaries

Batch 4 adds a compiler-free example and guided setup to the existing desktop.
It does not broaden firmware compatibility: symbolized ARMv7-M Cortex-M3 ELF,
QEMU `mps2-an385`, uint32 input symbols, input-ready and completion functions,
and an explicitly configured failure symbol/value are required. Raw BIN, arbitrary
vendor MCUs/peripherals, physical hardware and automatic vulnerability judgments
remain unsupported. Main, frozen protocols and research evidence are unchanged.

## Installation without Python

Open the repository **Actions → Desktop distribution candidates → the successful
run for `product/desktop-batch4` → Artifacts**. A GitHub login may be required.
Download the artifact for your OS and architecture and extract its outer GitHub
ZIP. Compare the included SHA256SUMS with the installer, not the outer ZIP.
Checksums detect changes; they do not establish publisher authenticity.

* Windows x86-64: run `FIRMAVEX-Windows-unsigned.exe`. This is an unsigned
  development installer; no certificate or reputation claim is made. Launch
  **FIRMAVEX** from the Start menu. The desktop launcher has no terminal window;
  a separate console worker is retained for reliable protocol communication.
* Ubuntu/Debian x86-64: open `FIRMAVEX-Linux-amd64.deb` with a graphical package
  installer that resolves dependencies. The package requests distro QEMU/GDB
  and Qt host libraries. Use the application menu afterwards. A portable tarball
  is also available but does not install system runtime dependencies. Graphical
  package-manager privilege dialogs and every distribution are not qualified.
* macOS Apple Silicon: open the **unnotarized** DMG, copy the application to
  Applications, then open it. It is not Developer-ID signed/notarized. Do not
  infer a distribution-wide Gatekeeper approval. Existing native QEMU and GDB
  are still required; automatic runtime setup is not implemented on macOS.
  Intel macOS, Windows ARM64 and native Linux ARM64 remain unqualified.

No installer removes user projects/results. Application files are separate from
per-user data: Windows `%LOCALAPPDATA%\FIRMAVEX`, Linux
`$XDG_DATA_HOME/FIRMAVEX` or `~/.local/share/FIRMAVEX`, macOS
`~/Library/Application Support/FIRMAVEX`. Back up that directory before upgrades.
Uninstall removes application files, retaining data and runtime generations.
Runtime/package-manager installations may require separate administrative removal.

## First launch

1. Read the compatibility page. **Check existing runtime** checks real executable
   capabilities; it does not run firmware or claim emulation succeeded.
2. On Windows x86-64, authorize vendor download, then choose **Install / repair
   runtime automatically**. The download can be large and require several minutes
   and substantial free disk space. Installation is cancellable; keep the app
   open until cleanup finishes. Installation refuses incompatible runtime builds.
3. Finish to create a **verified built-in example project**. No compiler is
   needed and no guest runs until you explicitly start testing.
4. Select **Run bounded test**. The example's enumerative search finds `[2, 1]`
   on attempt 10. Reproduce the saved vector three times and export the report.
   This condition is deliberately defined in independent product firmware; it
   is not evidence of a vulnerability or validation of arbitrary hardware.

The source-build example remains available in the Examples menu for developers.
Runtime setup/repair can be reopened later. History lists verified generations
and exposes integrity failures. Rollback only activates an inventoried, compatible
historical generation; it never deletes projects, results or other generations.
A failed/cancelled pre-activation install retains the old pointer. New run records
pin selected QEMU/GDB paths; reproduction verifies image, configuration and saved
tool identities. If old files were removed or altered, reproduction fails closed.
Full inventory verification can take time on a large runtime.

## Runtime integrity and licensing model

Windows downloads MSYS2 **2026-09-27** directly from the publisher:
`msys2-base-x86_64-20260927.sfx.exe`, SHA-256
`ad336cccfda47758b5e15cda993fbba421115cb0b126697daef1ee4dfe37209f`.
The bootstrap is verified before execution. A private temporary installation
updates through signed pacman repositories, installs UCRT64 QEMU and
`gdb-multiarch`, and snapshots ARM QEMU/GDB with all shared libraries, modules and data, omitting
unrelated `qemu-system-*` executables, build-only headers/static libraries,
package-development metadata/manuals, Python test resources and GUI
theme/icon assets unused by headless QEMU. The omission
inventory is retained, along with vendor license files and exact installed
package records. The private vendor installation is
removed after import. User/global MSYS2 installations are not upgraded.

The admitted native profile remains the Batch 3-tested QEMU 11.1.2 / GDB 18.1
executable hashes. MSYS2's rolling feed can change; an unqualified update is
rejected rather than silently bypassing the Windows execution gate. A future
release must provide a maintained, auditable version/source pinning arrangement.
A successful installation alone does not prove firmware execution; native tests
separately require actual completed guest receipts and cleanup.

FIRMAVEX **does not publish QEMU/GDB binary packs** in its installers or artifacts.
Vendor components are obtained directly from their publishers/distro repositories.
Local license/inventory/source-recipe information is retained, but it is not a
complete corresponding-source archive and must not be represented as one.
Redistribution of generated runtime packs requires a separate per-component
license and corresponding-source audit. Qt LGPL and bundled application dependency
notices are in `packaging/THIRD_PARTY_NOTICES.md` and the installed `notices` folder.
macOS one-click runtime distribution remains blocked on a relocatable, maintained,
legally auditable dependency closure. Linux delegates runtime licensing/updates to
the distro. License checksums are integrity evidence, not legal advice/guarantees.

## Build and verification

Qt/PySide6 is pinned to 6.11.1: 6.12 produced a reproducible shutdown
reference-count abort with CPython 3.11, even after tests completed. The same
GUI tests exit successfully with 6.11.1; no tests were disabled.

PyInstaller 6.16.0 builds native GUI and console-worker executables from one shared
bundle. `distribution-manifest.json` records actual Git/dirty state, file hashes,
platform, Python, PyInstaller/Qt/pyelftools versions and signing status. Archives
have SHA256SUMS. This is reproducible build *provenance*, not a claim of bit-for-bit
reproducible installers across timestamps or platforms. Inno Setup and DMG/dpkg
also depend on the host tool versions. `packaging/signing-readiness.json` lists
credentials/verification required before claiming signed/notarized distribution;
those credentials are not present and no signing is claimed.

The packaged example is an intentional MIT product resource in
`resources/example/image.json`, not a research ELF or a cloud campaign artifact.
It includes exact ELF SHA-256, source hashes, build flags, compiler identity and
normalized debug paths. Preparation checks the package bytes and source identities
and statically validates the ELF before writing a new project. It never executes
firmware automatically. The maintainer builder is
`python -m tools.build_product_example_image`; normal users never need it.

Three CI layers protect regressions: platform-neutral product/Qt tests; existing
native Batch 3 firmware/installer workflows; and Batch 4 native provider,
compiler-free GUI/frozen execution, reproduction/export/cancellation/cleanup and
Linux install/upgrade/removal tests. Synthetic unit tests do not qualify firmware.
CI runner tests do not establish clean consumer machines, WSLg or usability on
real desktops. Only successful native run receipts support their tested scope.
See `batch4.md` for actual observed results and unresolved beta gates.
