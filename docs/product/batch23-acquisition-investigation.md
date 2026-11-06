# Batch 23C: Windows runtime acquisition investigation

**Blocked: no acquisition repair implemented.** The workspace started clean and
detached at `88ef1e1f9f6dbb773f43dc30918fa6f9a16d16ef`. Production code, package
acquisition, executable qualification, cleanup and publisher trust checks remain
unchanged. QEMU 11.1.3 is not approved by this investigation.

## Established mismatch

The operator supplied verified private-installer evidence from Actions run
[42279061789](https://github.com/mtalhak003/FIRMAVEX/actions/runs/42279061789):

| Tool | Acquired package / executable | Qualification |
|---|---|---|
| QEMU | Package `11.1.3-1`, executable `11.1.3`, SHA-256 `f7e69cf3c284bad6a3b1c4159d2a88001f285c28f890dd2f8e56186682840cc7` | Requires `11.1.2`, SHA-256 `1247e03f58f2e845ff516e0cc951b67d0ee5dd5d6bcbe89faedbec692641b244` |
| GDB | Package `18.1-3`, executable `18.1`, SHA-256 `f867205234b5c61ad53bbb70db25462566b1742b409eb345f7f0178fd388f236` | Matches the existing version/hash gate |

This session did not independently download that diagnostic artifact. An exact
executable match is not evidence of a compatible complete DLL/package closure.

## Publisher-source investigation

Official GitHub-hosted MSYS2 documentation was read at revision
`7c9dc8badc87af9bb3adc93534c9cdc89d96f292`:

- [Updating MSYS2, line 3](https://github.com/msys2/msys2.github.io/blob/7c9dc8badc87af9bb3adc93534c9cdc89d96f292/web/docs/updating.md#L3): rolling release; only full-system upgrades are supported.
- [Installing older packages, line 62](https://github.com/msys2/msys2.github.io/blob/7c9dc8badc87af9bb3adc93534c9cdc89d96f292/web/docs/package-management.md#L62): older package archives can be used, but correct dependency versions may need recursive selection.

The [QEMU packaging recipe](https://github.com/msys2/MINGW-packages/blob/5267249172116ba04df9aa0395c9d1b7ba9f65c9/mingw-w64-qemu/PKGBUILD)
at revision `5267249172116ba04df9aa0395c9d1b7ba9f65c9` declares `11.1.3`, release
`1`, with named runtime dependencies. A recipe revision or upstream source signature does not
authenticate the older MSYS2 binary package, reproduce its executable digest, or
freeze the versions of its binary dependencies.

The following official endpoints returned proxy `403 Forbidden`, both normally
and with approved execution outside the sandbox:

- `https://repo.msys2.org/mingw/ucrt64/`
- `https://packages.msys2.org/packages/mingw-w64-ucrt-x86_64-qemu`
- A candidate `mingw-w64-ucrt-x86_64-qemu-11.1.2-1-any.pkg.tar.zst` URL under that repository and its `.sig` URL.
- `https://www.msys2.org/docs/package-management/` and `/docs/updating/`; their official GitHub sources above remained accessible.

The candidate package release `-1` was a probe, not a verified package identity.
These denials do not prove that older packages or snapshots do not exist. They
prevent this environment from authenticating their availability, signatures,
content hashes and dependency metadata. No independently verifiable immutable
11.1.2 package set was established.

## Safe next step

Obtain an independently reviewable, known-good package set from a previously
qualified installation/CI cache or an authenticated publisher archive. Required
inputs are:

1. The actual package containing the qualified QEMU executable; prove the existing
   executable SHA-256 instead of assuming a package release from its name.
2. The complete compatible QEMU/GDB/Icarus dependency set, including shared
   libraries, modules, data and any bootstrap/core packages needed for installation.
   Retain exact package versions, package metadata, dependency relationships and
   build information where supplied. An installed-package list alone is insufficient.
3. Original package archives and detached publisher signatures, authenticated
   against an independently trusted MSYS2 keyring. Pin archive hashes and signer
   identities in a reviewed lock manifest; never trust keys supplied by the payload.
4. Original license notices and source/recipe identities. Review redistribution
   obligations before hosting a runtime set; this investigation grants no rights.

Only after those inputs are verified should a private installer consume the
complete locked set without resolving missing dependencies from a rolling feed.
Retain existing size/path/signature checks, cancellation handling, executable
admission, diagnostic persistence and previous-generation preservation. Do not
implement a QEMU-only downgrade, ignored-package workaround, disabled signature
checks, or a version label that claims dependency compatibility without evidence.

If the original set cannot be recovered, the concrete alternative is a separately
authorized native qualification of a new, consistently captured vendor package
set and an explicitly reviewed versioned runtime profile. It is not a silent
hash replacement and is not implemented or approved here.

## Validation and remaining Windows work

The unchanged focused tests passed **155 tests, zero failures/errors/skips**:

```sh
QT_QPA_PLATFORM=offscreen /workspace/firmavex-batch7-venv/bin/python -m pytest -q -ra tests/product/test_platform_support.py tests/product/test_runtime_setup.py tests/product/test_runtime_pack.py tests/product/test_tools.py
```

These are administrative/unit checks, not a package-acquisition or native Windows
execution measurement. No new acquisition tests were added because no acquisition
strategy could safely be implemented. The only new file is this report.

A subsequent repair requires native Windows clean setup from the locked package
set, exact executable identities, private cleanup, rejected/tampered/missing-package
failure checks, cancellation, previous-generation preservation, and source/frozen/
installed ARM/RV32/HDL execution, reproduction, exports and process cleanup. Local
Linux tests do not establish any of those Windows outcomes.
