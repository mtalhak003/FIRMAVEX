# Physical consumer acceptance — not executed by CI

Use a disposable machine/VM and independent test results, never a research archive.
Record tester, date, OS/build, CPU, standard/admin account type, display scaling,
package hash, source revision, runtime versions/hashes and every PASS/FAIL/BLOCKED.
Do not replace an unperformed check with PASS. Retain errors and screenshots after
reviewing paths, names and diagnostics for publication.

1. Verify the package checksum and authentic publisher signature through a
   separately trusted key/channel. An unsigned preview fails the public signing
   gate. Do not treat a checksum as authenticity or silently bypass OS warnings.
2. With Python/compiler absent and a standard user account, install using the
   documented platform flow; separately record any administrator prompt needed
   by the OS package manager. Launch from the desktop/start menu.
3. Navigate the first-launch wizard using keyboard and normal/high-DPI scaling.
   Missing dependencies must be understandable. Install the licensed runtime;
   record source/signature checks, notices and host compatibility decisions.
4. Run the compiler-free example, inspect the configured failure and exact input,
   reproduce it, export a report, close/reopen the application and saved history.
   Compare result, SQLite and evidence hashes. This is emulator evidence, not
   physical firmware validation.
5. Disconnect external networking after dependency setup. Repeat the local
   example/reproduction/export. Reconnect only after recording the offline result.
6. Cancel an in-progress ARM/RV32/HDL supported example. Check classification,
   accounting and absence of owned QEMU/GDB/Icarus processes. No invented completed
   result or partial-success promotion is acceptable.
7. On a disposable copy only, corrupt an inactive runtime component; detection
   must fail closed. Repair to a verified generation and confirm preserved jobs.
8. Install the actual approved older version, save real results, hash the entire
   independent archive, upgrade to the distinct new version, reopen and compare.
   Exercise the specifically supported rollback procedure. Do not infer future
   schema downgrade support from one pair of versions.
9. Interrupt installation at a declared reproducible point. Record the actual
   interruption and recovery, not merely a completed installer. Also test limited
   permissions and bounded low disk on a disposable volume. Preserve diagnostics
   and prove original saved results remain unchanged after recovery.
10. Uninstall/reinstall. Independently stored projects/results must survive.
    Confirm no unexpected service, account, telemetry or external-network
    requirement remains. Record any incomplete removal separately.

macOS preview UI acceptance cannot qualify unified native execution. No hostile
firmware/HDL, unsupported MCU/BIN, hardware or VHDL claim follows from this list.
All mandatory physical acceptance rows remain UNTESTED until human evidence exists.
