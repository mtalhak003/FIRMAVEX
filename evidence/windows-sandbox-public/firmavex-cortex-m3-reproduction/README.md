# Windows Sandbox Cortex-M3 reproduction evidence

This sanitized derivative documents a FIRMAVEX example-firmware reproduction run reported from Windows Sandbox. The original evidence is preserved separately and unchanged. This package is a publication copy, not a directly importable run archive.

## Sanitization

Machine-specific Windows firmware paths are replaced consistently by `<FIRMWARE>/firmware.elf`; runtime executable paths use `<RUNTIME>/bin/`. Original and reproduction firmware locations share the firmware placeholder because their recorded SHA-256 hashes agree. Process IDs and debugger ports are removed. Run, benchmark, attempt, and observation correlation identifiers use consistent neutral labels. Timestamps, technical addresses, tool identities, hashes, warnings, and the generic `/FIRMAVEX-example/` debug source paths are retained. Those debug source paths identify example source files, not a local user profile. Execution observations are otherwise preserved.

These edits change the JSON bytes and correlation labels. SHA256SUMS covers this derivative's evidence.json, report.md, and README.md; it does not authenticate the original run or hash itself.

## What the evidence supports

The records identify symbolized ARMv7-M ELF example firmware targeting QEMU mps2-an385 (Cortex-M3). All three reproduction attempts record reaching the input-ready breakpoint, injecting and reading back `[2, 1]`, stepping guest instructions, reaching the completion breakpoint, and observing the configured failure value `1`. All three have matching, untruncated execution signatures and the same recorded firmware SHA-256. The summary reports three completed/matching observations and zero infrastructure failures.

The saved configuration retains guided search with budget 16; the operation and actual accounting identify reproduction with budget 3. The current orchestration retains the original configuration during reproduction. This package does not include the preceding search archive.

QEMU exited with code 1 after recorded completion on all three attempts. Cleanup is recorded as successful; this must not be described as a clean natural QEMU exit. GDB warnings about Python initialization, Windows OS ABI fallback, and unavailable example source files are retained.

## Limitations

This evidence does not establish physical hardware validation, general compatibility, independent replay, or public-beta readiness. It supports only the recorded example-firmware observations in the declared emulator environment, not coverage, complete-path equivalence, firmware safety, or compatibility with arbitrary Cortex-M3 firmware or peripherals. `real_firmware` denotes emulator execution of firmware rather than synthetic evaluator results; it does not mean execution on physical hardware.

The package contains no firmware or runtime binaries, build provenance, or original run database. Recorded firmware and tool hashes cannot be independently checked against those absent binaries. It does not establish reproducible compilation, independent authenticity, Windows Sandbox setup or isolation, or broader installation/release acceptance. Firmware consistency is recorded as stable-observed, not an atomic snapshot. Matching receipts are accounting evidence, not independent execution verification.

Verify the publication files from this directory with `sha256sum -c SHA256SUMS`.
