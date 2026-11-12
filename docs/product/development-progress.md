# Development progress

This is the primary chronological engineering history for FIRMAVEX. Its initial
retrospective audit covers major milestones in the 159 commits reachable from
the audited checkpoint
`e518342ede28ef462a0d6054f04b17e5bcb27821`, from September 14 to November 9, 2026.
Related repair commits are grouped; README-only maintenance is not presented as
new engine work. Later dated entries extend that history with their own evidence
and date basis. The retrospective audit does not establish development hours,
contemporaneous approval meetings or new execution results.

**Date basis:** unless explicitly marked otherwise, retrospective dates are
recorded Git **committer** timestamps converted to **Asia/Karachi**, not inferred
execution/completion dates. Review date: November 9, 2026. Unknown event dates stay
unknown. Commit identities and original history are preserved.

**Evidence labels:** Git/source facts describe retained implementation;
CI observations describe a named run/revision; historical records attribute
counts to versioned reports; user reports remain attributed; missing evidence
is NOT PROVEN. These labels are separate from PASS/FAIL outcomes. Earlier failures
and limited passes remain visible; no Windows candidate result grants production
approval. See the [evidence audit](../development/history-audit.md),
[documentation index](../README.md), [decision records](../decisions/README.md),
and [future-entry template](../development/milestone-template.md).

**Expanded Batch 30 coverage:** the
[source register](../development/history-sources.md) catalogues all **162 commits**
through Batch 29 checkpoint `da22cc6853d21cfa45fd851aa77108357f62dd7e`.
The [research contract map](../development/research-history.md),
[validation history](../development/validation-history.md) and
[chronological troubleshooting register](../development/troubleshooting-history.md)
add detail and evidence gaps to this primary timeline. The original 159-commit
audit/counts above remain the earlier review's scope, not a current test result.

| History segment | Coverage |
|---|---|
| [Research foundation](#research-foundation) | Static analysis, Cortex-M execution, blind evaluation, frozen comparisons, durable campaigns |
| [Desktop and backend foundation](#desktop-and-backend-foundation) | Batches 1–11, GUI/runtime packaging, RV32/HDL, platform and release blockers |
| [Product workflow and evidence review](#product-workflow-and-evidence-review) | Batches 12–22, result review/verification, regression sets and Windows repairs |
| [Windows candidate evidence and provenance](#windows-candidate-evidence-and-provenance) | Batches 23–28, isolated qualification, installed rejection and provenance tools |
| [November 9 progress update](#november-9-2026--windows-candidate-evidence-and-release-preparation) | Preserved CI observations and user-reported original-ZIP verification |
| [Batch 29 desktop workflows](#2026-11-10--batch-29-desktop-project-readiness-and-export-workflows) | Project reset, static ELF feedback, recent-list recovery, runtime/progress presentation and confirmed exports |

## Research foundation

### 2026-09-14–21 — Initial analysis pipeline and FIRMAVEX identity

- **Objective and implementation — verified Git history:** Establish the initial CodePulse repository, C firmware fixtures, compiler and static analyzer, then rename the project to FIRMAVEX. Follow-up commits addressed comment/string handling, format-string detection and numeric/context-aware copy checks.
- **Recorded decisions:** Source separation into compiler/analyzer/pipeline components and benchmark tests is visible in the commits. The historical reasoning for each heuristic or the project rename is not retained; no retrospective motivation is inferred.
- **Commits:** [initial repository `e189416`](https://github.com/mtalhak003/FIRMAVEX/commit/e189416b0efedf219def144b7e1aa2044ac87fb1), [initial analyzer `3b8714d`](https://github.com/mtalhak003/FIRMAVEX/commit/3b8714d1b45f1d637fc2238db62f991c6f4df935), [pipeline `72cf215`](https://github.com/mtalhak003/FIRMAVEX/commit/72cf2158cf2442e89a991d25b85119efb53eb961), [rename `1381da2`](https://github.com/mtalhak003/FIRMAVEX/commit/1381da24366da5a374e3e05b2287688269f72242), [copy-analysis repair `c70449e`](https://github.com/mtalhak003/FIRMAVEX/commit/c70449eeb5c99104dd5bf522a97eb071353af4d8).
- **Validation and failures:** Commits retain analyzer/compiler/pipeline/benchmark tests and explicit comment/string-handling repairs. No exact aggregate passing-test result or original CI artifact was established by this audit.
- **Limitations and next step:** Heuristic source analysis is not a firmware execution or security guarantee. The later Cortex-M path introduced observable execution and triggering-input workflows. Intervening README-maintenance commits through September 28 are not represented as new engine milestones.

### 2026-10-03–04 — Cortex-M execution, monitoring and failure workflows

- **Objective and implementation — verified Git history:** Add a minimal Cortex-M3 target, QEMU execution, GDB symbol monitoring, runtime failure detection, automated search, reproduction, integer minimization and structured reports.
- **Recorded decisions:** The staged component boundaries are visible in the implementation commits; later research documentation identifies QEMU `mps2-an385` and debugger-controlled inputs/completion observation. This is a simulator/debugger path, not physical hardware qualification.
- **Commits:** [target `5f5c17a`](https://github.com/mtalhak003/FIRMAVEX/commit/5f5c17abb22924d4c53222a807b6ff4455723b23), [QEMU backend `23aa92b`](https://github.com/mtalhak003/FIRMAVEX/commit/23aa92b619878c8615b96ce107bec4fc8c5003ad), [GDB monitor `d0ab657`](https://github.com/mtalhak003/FIRMAVEX/commit/d0ab65746dbfa94a73a5f12e4c2ac108357e3104), [detection `c9651df`](https://github.com/mtalhak003/FIRMAVEX/commit/c9651dfbdba6db25c2801f4e82f40516cd8b9509), [search `31ba157`](https://github.com/mtalhak003/FIRMAVEX/commit/31ba157b4c4d261f2cd046b367eebbfafd0b9747), [reproduction/minimization `0ebbf11`](https://github.com/mtalhak003/FIRMAVEX/commit/0ebbf113f35a9d86fcd952101cff6235adf6f9d0), [reporting `f0a92d8`](https://github.com/mtalhak003/FIRMAVEX/commit/f0a92d8112a0ab242e28e7f12dbd39c8ea1febfd).
- **Validation and failures:** Component tests are retained in Git; a dated aggregate test transcript was not established here. Later Step 15A explicitly fixes failed-observation masking and shared debugger-port assumptions.
- **Limitations and next step:** The initial tests depended on prebuilt ignored firmware images. Step 15A replaced that dependency with versioned, automated benchmark builds.

### 2026-10-06 — Steps 15A–15B: reproducible corpus and opaque evaluation

- **Objective and implementation — verified Git/history documents:** Replace manually prebuilt ELFs with shared `arm-none-eabi-gcc` build logic and five scalar v1 conditions; then add eight v2 fixtures with four input coordinates, each ranging from 0 to 15, administrative development/held-out splits and an opaque evaluation API.
- **Recorded decisions:** Ground truth remains test-only; the evaluator owns budgets, diagnostic data and accounting. Infrastructure failures abort searches/sessions rather than becoming safe observations. Admitted `KeyboardInterrupt`/`SystemExit` attempts remain charged and aborted before interruption propagates. Dynamic localhost GDB ports replace fixed-port dependence. See [Step 15B's contract](../development/evaluation.md) and [benchmark build documentation](../../firmware/benchmarks/cortex_m/README.md).
- **Commits:** [Step 15A `e03ff47`](https://github.com/mtalhak003/FIRMAVEX/commit/e03ff47f0f739517ae6c1b5c9db958ca756d7c8e), [Step 15B `944bdb5`](https://github.com/mtalhak003/FIRMAVEX/commit/944bdb52867f12e0004959a45d33febf8be1526c).
- **Validation and failures — retained documentation:** Compiler/output-safety, oracle, runtime-integrity and evaluator tests are committed. Step 15B documents exhaustive host-oracle checks over the finite domains and 52 defined QEMU v2 trials; those are historical documented assertions, not executions rerun by this audit. No aggregate passing-suite count is asserted here.
- **Limitations and next step:** The Python information boundary is cooperative, not adversarial isolation; public held-out fixture sources are inspectable. Toolchain/layout dependence, fresh-process startup and port handoff remain limitations. The next milestones standardized strategy execution and experiment records.

### 2026-10-07 — Steps 16A–16E: strategies, experiment records and frozen baselines

- **Objective and implementation — verified Git/history documents:** Add the common `SearchStrategy` lifecycle/runner, deterministic last-position-fastest enumeration, seeded uniform random sampling without replacement, immutable single-experiment records and campaign/protocol summaries.
- **Recorded decisions:** Strategies use only public immutable records; evaluator admission/accounting remains authoritative. Enumerative ordering is feedback-independent and O(width); random uses private seeded lazy Fisher–Yates state. `standard_baseline_protocol` freezes one enumerative run plus random seeds 0–9, preserving order and official serialization. See [strategy contract](../development/strategies.md), [experiment records](../development/experiments.md) and [baseline protocol](../development/evaluation-protocol.md).
- **Commits:** [16A `26d0e7c`](https://github.com/mtalhak003/FIRMAVEX/commit/26d0e7c6aeb2e1289b01cb51849c49e9244773ad), [16B `0694e99`](https://github.com/mtalhak003/FIRMAVEX/commit/0694e99dd46d477881c537ea697999e692f917e1), [16C `aeede4d`](https://github.com/mtalhak003/FIRMAVEX/commit/aeede4d2475c81120c9afe74493fe2bd77c391f5), [16D `ebeb9fa`](https://github.com/mtalhak003/FIRMAVEX/commit/ebeb9faac1491065b9fef593b40115d4758f7af5), [16E `e64d036`](https://github.com/mtalhak003/FIRMAVEX/commit/e64d036476ca2b8607b1dc050f695e6000364f02).
- **Validation and failures:** Dedicated strategy, experiment and protocol tests are committed, including replay/order/uniqueness, invalid-output and abort/censoring contracts. No independently retained aggregate test transcript was reviewed here. The records preserve infrastructure aborts and invalid outputs rather than treating them as ordinary non-discoveries.
- **Limitations and next step:** Conditional discovery costs must accompany discovery rates; a censored run is not assigned an invented first-failure index. These milestones establish framework and methodology, not strategy-performance results. Step 17 adds runtime feedback and a guided participant separately.

### 2026-10-08 — Steps 17A–17B: bounded runtime signatures and feedback-guided search

- **Objective and implementation — verified Git/history documents:** Add an immutable execution signature from an ordered bounded guest-PC prefix, then a deterministic feedback-guided strategy using signature novelty, a bounded FIFO parent archive, coordinate mutation and sparse random fallback.
- **Recorded decisions:** Versioned SHA-256 framing includes ordered uint32 PCs and a truncation marker; the completion PC is excluded, and exactly 4,096 samples immediately followed by completion is untruncated. The signature is an equality label, not distance, coverage or AI guidance. The strategy-facing API does not expose source, oracle, partition or administrator-diagnostic data; this remains a cooperative information boundary, not adversarial isolation. Baseline behavior and official serialization remain unchanged. See [signature semantics](../development/runtime-signature.md) and [guided algorithm](../development/guided-search.md).
- **Commits:** [17A `4449f6f`](https://github.com/mtalhak003/FIRMAVEX/commit/4449f6f870e695b911a742405cd44a7acce5a144), [17B `d62cc71`](https://github.com/mtalhak003/FIRMAVEX/commit/d62cc715d82cf26359dc34ae96c48749bdb43403).
- **Validation and failures — retained documentation:** Step 17A records 85 focused tests and three fresh QEMU trials proving controlled safe-input replay/differentiation. Step 17B records tests for causal feedback changes, deterministic replay and finite-domain progress, plus a two-observation real Cortex-M integration. These are historical documentation, not reruns or comparative campaigns.
- **Documentation clarification — Batch 30:** the original signature page described reaching the cap too broadly. Its collection paragraph now matches the already-committed collector and boundary tests: 4,096 samples immediately followed by completion is untruncated; execution beyond the sampled prefix is truncated. Neither code nor historical results changed.
- **Limitations and next step:** Single-stepping adds cost; identical paths with different data can share signatures and behavior beyond the prefix is invisible. No novelty, AI, hardware or superiority claim follows. The next step freezes a controlled comparison protocol.

### 2026-10-08 — Step 18A: controlled three-strategy protocol

- **Objective and implementation — verified Git/history documents:** Add `controlled_cortex_m_v1`, separate from the standard baseline: all eight v2 fixtures (six development/two held out), 256 evaluator attempts per run, enumerative once, random seeds 0–9 and guided seeds 0–9 with settings 32/8. This yields 21 runs/fixture and 168 overall; development alone has 126 runs/32,256 maximum charged attempts.
- **Recorded decisions:** Freeze configuration/ordering, reject guided-default drift and keep partitions administrative. Preserve infrastructure aborts and right-censored non-discoveries. The retained immutable expansion prevents an already-constructed preset silently adopting changed defaults. See [controlled protocol](../experiments/controlled-evaluation-v1.md).
- **Commit:** [18A `d14ca90`](https://github.com/mtalhak003/FIRMAVEX/commit/d14ca9079a5d3465711e5c7cd95ba448a3da58db).
- **Validation and failures:** Dedicated controlled-protocol tests are committed. The document explicitly records a severe floor effect: the cap guarantees no enumerative discoveries across these fixtures; the earliest is at attempt 3,328. No aggregate passing-suite count or full-campaign result is inferred here.
- **Limitations and next step:** Equal attempt budgets are not equal effectiveness across search orders; this preset alone cannot support general superiority. A higher-budget sensitivity study would need separate predeclaration. Step 18B measured runtime feasibility without changing the frozen settings.

### 2026-10-08 — Step 18B: bounded real-firmware feasibility and provenance

- **Objective and implementation — verified Git/history documents:** Add opt-in provenance capture, a predeclared 12-attempt real QEMU/GDB pilot and separate timing/reproducibility reporting; harden observable file/Git races, synthetic/real labels, partition/vector checks and final-inspection failure handling.
- **Recorded decisions:** Reject inconsistent capture while explicitly reporting non-atomic snapshots; private administrative provenance is separate from public research artifacts. Synthetic observations cannot be relabelled as real firmware, and a failed final inspection cannot count as fully verified completion. See [runtime feasibility](../experiments/runtime-feasibility.md).
- **Commit:** [18B `24c53e2`](https://github.com/mtalhak003/FIRMAVEX/commit/24c53e2a917548b3bbb3b82191783adcc7fe1325).
- **Validation — retained documentation:** The original pilot reports 12 successful admitted attempts (six prescribed safe, six prescribed triggered), zero timeouts/infrastructure/cleanup failures and mean 0.950239351 seconds per attempt. After hardening, the document records 103 focused tests and 978 complete-suite tests passed without failures/skips. Raw external pilot archives were not re-inspected in this history audit.
- **Limitations and next step:** Prescribed triggers are not search discoveries, and extrapolated campaign costs are estimates. No strategy ranking follows from the pilot. Reliable interruption/recovery becomes the next prerequisite.

### 2026-10-09 — Step 18C: durable campaign execution and recovery

- **Objective and implementation — verified Git/history documents:** Add a versioned, checksummed administrator journal, ordered completed-prefix persistence, fresh attempt ownership, explicit experiment-boundary restart authorization, context compatibility, record codec and recovery-history export.
- **Recorded decisions:** Preserve official experiment schemas, evaluator accounting and frozen protocol. Completed experiments are not rerun; abandoned/unknown partial work remains disclosed. Interruption is propagated after truthful accounting and cleanup. Cooperative POSIX locking, file synchronization and replacement do not imply universal crash durability. See [campaign recovery](../experiments/campaign-recovery.md).
- **Commit:** [18C / current research checkpoint `4cdedd2`](https://github.com/mtalhak003/FIRMAVEX/commit/4cdedd23997aa3455585512f03bbe69b179ad887).
- **Validation — retained documentation:** Final targeted suites recorded 514 passed; the complete suite recorded 1,365 passed with no failures/skips. The document states that no controlled campaign or new pilot was run for this milestone. These historical totals were not rerun by this audit.
- **Limitations and next step:** POSIX advisory locks are cooperative; unsupported directory synchronization and unknown interrupted accounting remain explicit. Selective restart can bias comparisons, and recovery does not repair the enumerative floor effect. Step 19 concerns separately authorized development-only campaign execution and analysis.

### Step 19 follow-on — local development campaign and preliminary analysis (dates not established here)

- **Objective and implementation — user/conversation-reported:** Prepare portable administrative launch/analysis tools for local Ubuntu WSL, six development ELF builds, local tool/artifact provenance and durable execution of the unchanged 126-experiment plan at research checkpoint `4cdedd2`. External preparation packages and local campaign archives are not versioned milestones established by the commits inspected here.
- **Recorded research requirements:** Keep held-out work separate; preserve all seeds, budgets, strategy settings, journal accounting and original evidence. Local firmware/toolchain provenance must not be replaced with cloud builds. Read-only analysis outputs remain separate from original archives and backups.
- **Evidence/date gap:** The conversation reports completed preliminary journal-derived analysis, but no actual Step 19 journal, original execution archive, analysis tables or local WSL files were inspected in this audit. The execution/completion date and numerical comparative findings therefore remain unestablished here; the research-code anchor is the October 9 `4cdedd2` checkpoint, not proof of campaign timing.
- **Known reported failure:** Execution verification remained **FAILED**, with supplementary evidence missing at zero-based position **7** (`multi_variable`, random seed **6**). Results were restricted to preliminary, journal-derived observations; no missing evidence may be fabricated. This is a different archive and question from the later user-reported PASSED Batch 27 Windows ZIP verification.
- **Limitations and next step:** Preserve the evidence gap, censoring/replication limitations and charged-attempt terminology. No held-out, hardware, statistical-significance, AI-guidance or general-superiority claim is supported. Research-paper work was subsequently paused for desktop product development; original research data and protocol remain preserved.

## Desktop and backend foundation

### 2026-10-11 — Batch 1: supervised ARM product foundation

- **Objective / changes (Git and recorded implementation):** add an installable CLI/product namespace, strict compatible Cortex-M3 ELF/project contract, fresh QEMU/GDB observations, a versioned supervised worker, SQLite evidence, bounded replay/export and explicit recovery/restart. [Implementation d0a42c79](https://github.com/mtalhak003/FIRMAVEX/commit/d0a42c79fd20172184135d1ccf6d2ab8907a7c69).
- **Recorded decision:** keep `firmavex.product` separate from the canonical `src.firmavex` research engine; reuse its strategies, evaluator-owned accounting and signature semantics. Inputs are injected after readiness and completion remains mandatory. [Batch 1 architecture and evidence](validation.md).
- **Validation (historically recorded, not rerun here):** 397 product tests and 1,762 complete-suite tests passed, with no failures/skips. The installed-wheel example found `[2, 1]` at charged attempt 10 and replayed it 3/3 times; 13 retained receipts and 26 reaped child processes are documented.
- **Limit / next at checkpoint:** Linux example execution only; Windows dispatch gated, macOS/WSL native execution unverified. No arbitrary MCU/BIN/hardware or hostile-workload sandbox. Add the GUI and independently qualify host supervision.

### 2026-10-12 — Batch 2: responsive desktop and portable host supervision

- **Objective / changes (Git):** add PySide6 project/configuration, background filesystem work, live progress/cancellation, results, replay/export and read-only history/recovery. [Implementation 406dfe0f](https://github.com/mtalhak003/FIRMAVEX/commit/406dfe0f3e1e26689869951e69b4b01ba486b119); [validated checkpoint 06e6c241](https://github.com/mtalhak003/FIRMAVEX/commit/06e6c241252096d258ffbd627798928d72b6bdc4).
- **Recorded decision / failure resolution:** immutable command snapshots prevent later GUI edits from changing admitted runs; original Windows path/handle metadata must agree. Repairs retain UTF-8 and byte-integrity checks instead of accepting inconsistent `stat`/`fstat` observations. [Batch 2 validation](batch2-validation.md).
- **Validation (recorded local and CI):** final local suite 1,911 passed, 4 native-Windows skips. Historical CI [38255127322](https://github.com/mtalhak003/FIRMAVEX/actions/runs/38255127322) is recorded as passing all six OS/Python jobs plus Ubuntu real-firmware regression at `84c0561f`. Earlier Batch 1 run `38166140242` failed; its inaccessible detailed logs were not replaced by a passing local reproduction.
- **Limit / next at checkpoint:** host GUI/ownership passes did not qualify native Windows/macOS ARM execution or installers. Keep those gates until actual firmware paths pass.

### 2026-10-12 — Batch 3: native packaging, runtime profiles and command-channel repair

- **Objective / changes (Git):** add distribution candidates and verified runtime-pack management in [1bc188e1](https://github.com/mtalhak003/FIRMAVEX/commit/1bc188e18c6c5d12093970968430526c10912aaa); admit only the independently tested exact Windows runtime in [32515bad](https://github.com/mtalhak003/FIRMAVEX/commit/32515bad177dfecbb02987e3608e46ea45b3fc5e).
- **Recorded decision / failures:** qualify an exact version/hash/platform combination, not tool availability alone. A vanished procfs entry is accepted only for ENOENT/ESRCH. Supervised GDB probes had inherited command stdin; [bb77217d](https://github.com/mtalhak003/FIRMAVEX/commit/bb77217d6d254d3c231723213f3b895a4ad4372c) supplies DEVNULL without relaxing timeouts. [Detailed validation](batch3-validation.md).
- **Validation (recorded):** local final suite 1,967 passed, 4 skips. CI [38282319695](https://github.com/mtalhak003/FIRMAVEX/actions/runs/38282319695) records five passing package/native jobs, including actual Windows source/Qt/frozen ARM and Apple Silicon example paths; [38282319967](https://github.com/mtalhak003/FIRMAVEX/actions/runs/38282319967) records seven passing regression jobs. [Documentation checkpoint 4a1b24f4](https://github.com/mtalhak003/FIRMAVEX/commit/4a1b24f419b822d931f0f6deee516fe629d4bb63).
- **Limit / next at checkpoint:** unsigned/unnotarized candidates and narrow example qualification only. Historical ARM-only macOS passes do not qualify the later unified resource contract. Qualify setup and compiler-free installed journeys next.

### 2026-10-13 — Batch 4: compiler-free first launch and managed runtime generations

- **Objective / changes (Git):** first-launch wizard, verified embedded MIT example, explicit Windows vendor-install consent, checksum-pinned bootstrap/signed packages, inventoried runtime generations, repair/rollback and windowed packaging. [Implementation e20bf759](https://github.com/mtalhak003/FIRMAVEX/commit/e20bf759040d5cdc300c1a82dd25717efb1ced99); [final code 11b93dca](https://github.com/mtalhak003/FIRMAVEX/commit/11b93dcab5726e372b5ce3eb2c741a7f817cfc04); [record 78f06221](https://github.com/mtalhak003/FIRMAVEX/commit/78f062217775c5e0325c7c5de973a62ba4292a7c).
- **Recorded decision / failures:** obtain publisher runtimes separately rather than silently redistribute them; keep old verified generations. Repairs covered CRLF source identities, worker-name case, vendor snapshot limits/cleanup, Qt shutdown and redundant validation. [Batch 4 record](batch4.md).
- **Validation (recorded):** local complete suite 2,022 passed, 4 skips. The document records passing regression [38414421922](https://github.com/mtalhak003/FIRMAVEX/actions/runs/38414421922), distribution [38414422195](https://github.com/mtalhak003/FIRMAVEX/actions/runs/38414422195), and beta setup [38414422220](https://github.com/mtalhak003/FIRMAVEX/actions/runs/38414422220) at `11b93dca`, including compiler-free native workflows and cleanup.
- **Limit / next at checkpoint:** rolling package feeds are not immutable dependency closure. Reinstall is not proof of every cross-version upgrade; signing, consumer acceptance, legal/source audit and WSLg remain open.

### 2026-10-14 — Batch 5: independent RV32 and HDL backends

- **Objective / changes (Git):** introduce versioned target/capability/backend contracts independent of Qt and add real QEMU RV32IM `virt` and single-file Icarus Verilog testbench execution. [Foundation a9810669](https://github.com/mtalhak003/FIRMAVEX/commit/a9810669277dad8f531f2410f40c4638d610b0f7); [ARM accounting preservation d49a85eb](https://github.com/mtalhak003/FIRMAVEX/commit/d49a85ebbefc53f76564fa5d2ae7f8e80ffc4632).
- **Recorded decision:** capabilities distinguish search, symbol observations and HDL assertions; the ARM adapter delegates to existing product services and preserves authoritative outcomes. No C++ rewrite was justified by measured administration costs. [Backend contracts and measurements](universal-backends.md).
- **Validation (recorded Linux pilot):** RV32 safe/triggering observations took 0.3159/0.3191 seconds and HDL pass 0.1282 seconds, including probes/startup/cleanup. These single observations are not comparative throughput or strategy results. Test evidence must remain scoped to the named example and host.
- **Limit / next at checkpoint:** no native Windows/macOS qualification for new backends at that point; no RISC-V signatures/search, VHDL, physical FPGA or remote service. Integrate GUI/frozen launchers and independently qualify each platform.

### 2026-10-14 — Batch 6: unified desktop, trusted execution and Windows repair

- **Objective / changes (Git):** integrate ARM/RV32/Verilog controls, trusted-workload admission, frozen launchers, persistence/reopening and exports in [c8478ce6](https://github.com/mtalhak003/FIRMAVEX/commit/c8478ce65af073e817994643afc885bd8a2a8f98). [Unified desktop record](unified-desktop.md).
- **Recorded decision / failures:** OS process ownership and resource limits are defense in depth, not a hostile-input sandbox. Failed run [38548476770](https://github.com/mtalhak003/FIRMAVEX/actions/runs/38548476770) exposed Windows zero link counts/deferred timestamp visibility; uncached no-follow metadata and byte rereads preserve fail-closed validation. HDL transport accepts LF/CRLF while retaining exactly-one-marker validation. [Repair checkpoint 993a506e](https://github.com/mtalhak003/FIRMAVEX/commit/993a506e4c082645d1a48644670aa9a2a4c78fe2).
- **Validation (recorded CI):** [38546993532](https://github.com/mtalhak003/FIRMAVEX/actions/runs/38546993532) records Ubuntu source/frozen/installed ARM/RV32/HDL example passes. The exact Windows RV32/HDL catalog identifies [38590752705/job/115944662408](https://github.com/mtalhak003/FIRMAVEX/actions/runs/38590752705/job/115944662408) at `0d3011ab` and scopes qualification to source/frozen/installed examples, replay, cancellation, cleanup and export.
- **Limit / next at checkpoint:** only matching runtime hashes gain those historical scopes; no arbitrary workloads or current rolling-runtime approval. macOS remained blocked and required a separately defensible memory boundary.

### 2026-10-14 — macOS resource-admission failure retained, preview policy recorded

- **Objective / changes (Git):** investigate Apple Silicon `RLIMIT_AS` admission with bounded native probes in [8ab7f41d](https://github.com/mtalhak003/FIRMAVEX/commit/8ab7f41d253f95e397a9b45eb178ebe4b963ecd3); retain complete findings in [0d3011ab](https://github.com/mtalhak003/FIRMAVEX/commit/0d3011abbe2f6b9b1b758d067ad7bb566f81ac66).
- **Recorded decision:** do not enlarge/disable the resource cap or substitute a polling sampler as equivalent enforcement. [Kernel/source and alternative analysis](macos-memory-admission.md) distinguishes virtual mappings from resident RAM and requires independent native enforcement evidence.
- **Validation (recorded native diagnostic):** [38590177869/job/115942649651](https://github.com/mtalhak003/FIRMAVEX/actions/runs/38590177869/job/115942649651) records small-C virtual mappings around 420 GB with resident memory around 1 MiB; AS admission still returned EINVAL. Mach footprint and memorystatus attempts failed with KERN_NO_ACCESS/EPERM. These were zero-firmware OS probes, not successful enforcement qualification.
- **Limit / next:** macOS Apple Silicon unified native execution stays unsupported/desktop preview; earlier ARM-only passes do not close this contract. A privileged helper, VM or alternate hard boundary needs separate design and native qualification; Windows/Ubuntu controls are not weakened.

### 2026-10-14–17 — Batch 7: local interface and Windows CI stall diagnosis

- **Objective / changes (Git):** readable summaries and an asynchronous, versioned local stdio interface over the existing Supervisor in [9b519184](https://github.com/mtalhak003/FIRMAVEX/commit/9b51918452eeb6f7e84585cb2fac6dea4c7bb2eb); exact Windows runtime discovery qualification recorded in [ac8e0723](https://github.com/mtalhak003/FIRMAVEX/commit/ac8e07233241eb294e2f6aa07216624b78ebb771). [Local contract](local-worker-interface.md).
- **Recorded decision:** retain one execution path, ephemeral bounded sessions and explicit trusted inputs; a local pipe/UUID is not remote authentication or a durable service. No public endpoint is added.
- **Failure / resolution (recorded):** Windows product jobs stalled before later packaging. Bounded per-test/collection/shutdown diagnostics and owned output files were added from [18e9cc5c](https://github.com/mtalhak003/FIRMAVEX/commit/18e9cc5c98ca8f28887f0d31347c0ddbb2fcf837). [1793d9ab](https://github.com/mtalhak003/FIRMAVEX/commit/1793d9abbacd84db582a0c81a9df999ef52be21a) bounded pytest IDs: a 1,048,659-character node ID had entered `PYTEST_CURRENT_TEST` and exceeded Windows limits. Payload/assertions and job budgets were retained. [Diagnostic evidence and limits](ci-diagnostics.md).
- **Evidence limit / next:** the original raw exception was not recoverable from the truncated annotation; later native outcomes must be checked at their own SHA. Missing or interrupted JUnit is not success. Preserve Windows/Ubuntu scope and macOS preview policy; remote authorization/isolation/persistence remain design work.

### 2026-10-17 — Batches 8–9: preview integrity, inventories and locked build inputs

- **Objective / changes (Git):** [b55b0dc2](https://github.com/mtalhak003/FIRMAVEX/commit/b55b0dc276189c88ead2f7c947a51f9d59ed5901) adds hash-bound release bundles and scoped Python SPDX inventory; [9d5b48b4](https://github.com/mtalhak003/FIRMAVEX/commit/9d5b48b4fd9df666c18ff884f7acdedb9579db7a) adds immutable action/build inputs and actual collected-file inventory, with portability repairs through [19cd4573](https://github.com/mtalhak003/FIRMAVEX/commit/19cd45736337243c64a2298285781a27499981fa).
- **Recorded decision:** integrity sidecars and build lineage do not establish publisher authenticity, complete native composition or legal clearance. Observable-race checks report `atomic=false`; unknown owners/licenses remain unresolved. [Batch 8 scope](batch8-release-readiness.md); [Batch 9 hardening](batch9-public-beta-hardening.md).
- **Validation (recorded local):** Batch 8 documented a frozen Linux ARM example in an externally denied network namespace, with search attempt 10 and three replay attempts, plus independent SPDX validation with zero issues. Batch 9 documented 44 focused checks and a fresh frozen ARM/RV32/HDL/cancellation/export journey. These are example/mechanism observations, not a hostile-workload sandbox or new current-commit CI claim.
- **Limit / next:** unsigned/unnotarized artifacts, unresolved native licenses/source, consumer acceptance and distinct-version lifecycle proof remain blockers. Fixed namespace checks lacked delegated aggregate quotas/VM isolation and did not authorize hostile workloads.

### 2026-10-17 — Batch 10: native ownership evidence and genuine installer transitions

- **Objective / changes (Git):** component-level byte lineage, bounded payload inspection, genuine baseline/candidate installer comparison, detached artifact signatures and fail-closed release approval in [bba2958d](https://github.com/mtalhak003/FIRMAVEX/commit/bba2958dc9260dd64c8fde802131f7cb7aa76070). Baseline installer revision is `19cd4573`, not a renamed copy of the candidate. [Batch 10 design/evidence](batch10-release-blockers.md).
- **Recorded decision / failure resolution:** Inno's initial uninstaller can exit before descendants finish removal. [b56400e4](https://github.com/mtalhak003/FIRMAVEX/commit/b56400e48f6f2025435ef70e17a794a0c652d779) waits for the entire owned tree before accepting removal or moving to another transition. Offline Ed25519 identity signatures remain distinct from Authenticode/notarization.
- **Validation (recorded partial CI):** hosted assessment [39049249940](https://github.com/mtalhak003/FIRMAVEX/actions/runs/39049249940) observed CPU throttling, process-count denial and kernel memory OOM, but Bubblewrap loopback setup failed with `Operation not permitted`; cleanup was retained. Installer workflow definitions alone are not evidence of every transition passing.
- **Limit / next:** component ownership/source review, actual signing, consumer acceptance and aggregate isolation remain open. Do not turn a successful packaging/native job into approval or conceal the failed namespace stage.

### 2026-10-17–20 — Batch 11: signed review evidence and host-policy diagnostics

- **Objective / changes (Git):** retained unresolved component diagnostics at [d9e3877f](https://github.com/mtalhak003/FIRMAVEX/commit/d9e3877fbe71489a60640855ce9994c41e852b35), followed by byte-bound notices/review attestations and restored qualification workflows in [7965ac72](https://github.com/mtalhak003/FIRMAVEX/commit/7965ac72907054130ca0e31fa56fdcdf71819744). [Batch 11 protocol and follow-up](batch11-release-evidence.md).
- **Recorded decision:** an independently provisioned reviewer policy authorizes exact checks over an exact manifest; a review signature cannot sign an installer, authenticate its substantive conclusions or override mandatory ownership/signing gates. Unknown file owners are not guessed from filenames or TOC lineage.
- **Validation / failures (recorded):** local product selection 750 passed, 4 skipped; final targeted attestation/consistency/cleanup selection 31 passed. CI [39303862810](https://github.com/mtalhak003/FIRMAVEX/actions/runs/39303862810) retained AppArmor `unprivileged_userns` denials for `setpcap`/`net_admin`. [39303862786](https://github.com/mtalhak003/FIRMAVEX/actions/runs/39303862786) retained positive quota observations but failed loopback setup. [72fe794e](https://github.com/mtalhak003/FIRMAVEX/commit/72fe794ec391f85ca432ac75110c627a5e267289) explicitly closes the Python 3.14 buffered-write fixture so destructor errors cannot falsely pass a file-limit test; production caps are unchanged. Subsequent Windows installer diagnostics include [15661b56](https://github.com/mtalhak003/FIRMAVEX/commit/15661b560f4bfb357b38f886b6efc85866984bd6).
- **Limit / next:** authentic external reviewer/signing inputs, complete native component/source evidence, standard-user/offline/low-disk consumer trials and hostile-workload isolation remain unresolved. No private trial evidence is needed or consulted to record these gaps.

## Product workflow and evidence review

### 2026-10-21 — Compiler/reproduction diagnostics and original Windows process identity

- **Objective and implementation (Git/source facts):** expose bounded Verilog compiler diagnostics and understandable ARM reproduction summaries; verify child termination with original Windows handles rather than numeric PID/exit-code assumptions. Commits: [0ddb41b](https://github.com/mtalhak003/FIRMAVEX/commit/0ddb41b10a2d1fe72001e5239527f9e1528d68ff), [b3c4e01](https://github.com/mtalhak003/FIRMAVEX/commit/b3c4e014147978b33fcaf6d6ee36442eb8eea26a), [b967c1b](https://github.com/mtalhak003/FIRMAVEX/commit/b967c1ba2ca07fe337619e75c47c191af186c20d).
- **Recorded decisions/evidence:** those commits add pure, Qt and native test assertions; [Batch 17's qualification notes](batch17-custom-workflow.md#qualification-and-limitations) retain the original-handle requirement. No numerical test result for this grouped change was independently established in this audit.
- **Limits and next recorded work:** diagnostic rendering does not prove execution; numeric PID/259 alone remains insufficient cleanup proof. Subsequent shared-workspace work added explicit result context and read-only navigation.

### 2026-10-21 — Batches 12–13: guided workspace and read-only history

- **Objective and implementation (Git/source facts):** explain disabled actions, separate administrative operation output from selected execution evidence, add bounded recent-project shortcuts, explicit history opening and saved-run comparison. Commits: [06405c9](https://github.com/mtalhak003/FIRMAVEX/commit/06405c959a27e8fd6b0dd287f6c877d65a0a6a82), [fa416e0](https://github.com/mtalhak003/FIRMAVEX/commit/fa416e0b838f5d8a98ffb7da030d1b89564826d6).
- **Recorded decisions/evidence:** [Batch 12](batch12-usability.md) and [Batch 13](batch13-review.md) reuse supervised inspection and existing formats, preserving trust/consent and selected results. They describe product/Qt coverage without a retained numerical result for this entry; no tests were rerun for this history audit.
- **Limits and next recorded work:** summaries are session observations, preferences are not an evidence ledger, and comparison is not replay or authenticity verification. Batch 14 next unified supported archive inspection while preserving scope distinctions.

### 2026-10-21 — Batch 14: scoped archive integrity and comparison

- **Objective and implementation (Git/source facts):** compare supported standalone ARM and shared ARM/RV32/Verilog archives, preserve unavailable fields and show explicit integrity scope. Commit: [0a3fca3](https://github.com/mtalhak003/FIRMAVEX/commit/0a3fca3a0a38319574d4e8e803bffc09dbb1d32a).
- **Recorded decisions/evidence:** [Batch 14](batch14-history.md) reuses established artifact/inventory verifiers; `verified` requires actual nonempty listed-artifact hash/size checks, not a recorded digest alone. No exact historical test count is retained in that document.
- **Limits and next recorded work:** listed shared-wrapper files do not establish nested ARM receipt validity; sequential checks are not atomic snapshots, authenticity or execution proof. The document explicitly proposes cancellable verification and finer progress as subsequent work.

### 2026-10-21 — Batches 15–16: cancellable verification and observation reports

- **Objective and implementation (Git/source facts):** add worker-owned verification progress/cancellation, preserve current evidence/logs, and record session/freshness provenance with bounded report export. Commits: [b082886](https://github.com/mtalhak003/FIRMAVEX/commit/b08288658037f86136d8afafcd2e22bf8c85277b), [0a097c8](https://github.com/mtalhak003/FIRMAVEX/commit/0a097c89201d3949d238a928fe714860166dbc30), plus [34e3c5e](https://github.com/mtalhak003/FIRMAVEX/commit/34e3c5e9f0e13d4dbbb0be9c76ba033fe39b745d) rejecting report destinations through path aliases.
- **Recorded decisions/evidence:** [Batch 15](batch15-verification.md) keeps verification in the supervisor, retains partial observations on interruption and fails on final consistency errors. [Batch 16](batch16-verification-reporting.md) separates historical hashes from explicit metadata-only change checks and creates reports outside original archives. The documents' historical matrix-success statements are recorded claims, not newly verified CI here; they provide no exact count for these grouped changes.
- **Limits and next recorded work:** reports are unsigned observations; metadata freshness does not rehash content or lock writers. Subsequent Batch 17 work captured reusable immutable custom-input configurations.

### 2026-10-22 — Batch 17: repeatable custom projects and revisions

- **Objective and implementation (Git/source facts):** preserve ARM project handoffs/new builds and introduce named RV32/Verilog input snapshots with explicit revision lineage and static preflight. Commits: [96ab00b](https://github.com/mtalhak003/FIRMAVEX/commit/96ab00b27b8720512f116ef8e1145a0d9599dda1) through [0b61e5a](https://github.com/mtalhak003/FIRMAVEX/commit/0b61e5a41d0c9ab07016fade67baf0af8f654b21).
- **Recorded decisions/evidence:** [Batch 17](batch17-custom-workflow.md) reuses the existing Request/Limits, managed ARM and constrained single-file HDL contracts, hashes/copies selected inputs before dispatch, and never grants consent through navigation. Pure, supervised, Qt and native fixture coverage is described; no numerical result is retained there.
- **Limits and next recorded work:** no arbitrary build system, recursive project index, archive migration or broader HDL support. macOS memory admission and Linux/release-evidence gaps remain; the document's next step is bounded failure diagnosis and identity-aware comparison.

### 2026-10-23 — Batch 18: bounded failure diagnosis

- **Objective and implementation (Git/source facts):** distinguish configured failure, infrastructure error, cancellation and unavailable evidence; add sanitized retained-log/VCD metadata inspection and identity-aware comparison. Commit: [ca8a30c](https://github.com/mtalhak003/FIRMAVEX/commit/ca8a30ca566043352e5d14ecde27760c36be6081).
- **Recorded decisions and validation (historical document):** [Batch 18](batch18-diagnosis.md#local-validation) records **1,153 passed, 13 skipped**, and a separate **266 passed** focused selection. Socket-denied sandbox runs were distinguished from host execution; existing policies were retained. Missing outcomes are not reconstructed from log text, and VCD inspection remains bounded metadata parsing.
- **Limits and next recorded work:** no waveform viewer, hardware equivalence or complete environmental reproduction is established. The report proposes explicit future-run provenance, implemented in Batch 19; these historical counts were not rerun in this audit.

### 2026-10-24 — Batch 19: explicit RV32/Verilog regression sets and provenance

- **Objective and implementation (Git/source facts):** save immutable 1–16-entry regression sets, execute explicitly consented entries in order, retain entry associations and link explicit reruns without rewriting prior results. Commit: [3d9ffcb](https://github.com/mtalhak003/FIRMAVEX/commit/3d9ffcb5cc0ef1c9b91796d7cab9a0835d389ec3).
- **Recorded decisions and validation (historical document):** [Batch 19](batch19-regression-workflows.md#validation-and-remaining-work) records **1,215 product/desktop passed, 7 skipped**; **215 backend passed, 9 skipped**; **256 focused passed**; and **3 native regression-workflow passed**. These overlapping selections are not additive. Infrastructure errors stop later admissions; no automatic retries/resume are added. The cited baseline Product run [40003710619](https://github.com/mtalhak003/FIRMAVEX/actions/runs/40003710619) concerns Batch 18, not proof of every subsequent Batch 19 change.
- **Limits and next recorded work:** ARM retains search/reproduction rather than these test sets. Host/tool declarations do not prove every dependency. Next recorded work is aggregate regression review/dashboard export.

### 2026-10-24 — Batch 20: regression reports and Windows failure repairs

- **Objective and implementation (Git/source facts):** add bounded regression dashboards, entry/artifact association checks and fresh-verification text reports; repair test-harness and native directory failures without relaxing admission. Commits: [c077ee7](https://github.com/mtalhak003/FIRMAVEX/commit/c077ee71cb093be55566ee478f530a92f65f38a0), [c7050f4](https://github.com/mtalhak003/FIRMAVEX/commit/c7050f40de2de36681cd4dc916fe5a4fe4a4752a), [d474fab](https://github.com/mtalhak003/FIRMAVEX/commit/d474fab63500e6a2e726caf77c207060efecaa55).
- **Recorded failures/decisions/evidence:** [Windows repair record](batch20-windows-repair.md) identifies a 131,073-byte pytest parameter ID exceeding Windows' environment-value limit, corrected with stable short IDs; it records Windows Python 3.11/3.12 success in [run 40022757709](https://github.com/mtalhak003/FIRMAVEX/actions/runs/40022757709). Separate RV32 and Verilog diagnostics identified `WinError 267` at 286-character native cwd paths. The repair uses an existing, validated same-directory short spelling, failing closed if unavailable; it creates no junction/evidence copy or security exception.
- **Recorded validation/limits/next:** [Batch 20](batch20-regression-review.md#baseline-and-validation) records separate **1,245 passed/7 skipped** product+desktop and **215 passed/9 skipped** backend selections. The repair document records **1,472 passed/16 skipped** locally before the path-correction commit; these are not a fresh post-correction Windows count. Aggregate integrity is not authentic execution; Batch 21 next audited native/user-visible journeys.

### 2026-10-24 — Batch 21: scoped product acceptance and four usability corrections

- **Objective and implementation (Git/source facts):** fix ARM new-project import selecting the wrong image, preserve individual evidence during regression administration, retain regression error/partial-session context, and reuse consistent padded-decimal/hex RV32 parsing. Commits: [bc55692](https://github.com/mtalhak003/FIRMAVEX/commit/bc556923b37f8d4641f95f820a89ac936afda60b), followed by [d8e071e](https://github.com/mtalhak003/FIRMAVEX/commit/d8e071ee370d5fad03b8a04958033a653e1a78aa) for path-identity/CI diagnostics.
- **Recorded evidence/failures:** [Batch 21](batch21-acceptance.md#resume-validation-2026-10-24) separates sandbox permission failures, an extracted-QEMU/module build mismatch repaired by matching publisher modules, and a baseline 300 ms timing failure left unchanged. Final separate selections recorded **1,270 product/desktop passed, 7 Windows-only skips**, including **13 native desktop tests**, and **224 backend passed, 9 skipped**. Its baseline CI links [40024230126](https://github.com/mtalhak003/FIRMAVEX/actions/runs/40024230126) and [40024229596](https://github.com/mtalhak003/FIRMAVEX/actions/runs/40024229596) apply to starting `d474fab`, not automatically to every later commit.
- **Limits and next recorded work:** programmatic native Qt journeys are not human accessibility/standard-user consumer acceptance; macOS memory, Linux isolation and release evidence remain unresolved. The report explicitly proposes discoverable retained-input verification for Batch 22.

### 2026-11-03 to 2026-11-06 — Bundled MPS2 regression and Batch 22 verification consistency

- **Objective and implementation (Git/source facts):** preserve the original bundled ARM image/linker and test the real `mps2-an385` startup/readiness/completion contract; align individual RV32/Verilog verification with regression retained-input checks. Commits: [f0e633c](https://github.com/mtalhak003/FIRMAVEX/commit/f0e633c44bd1cad6cb3a0f0f2b94f77a1de8f065) (Nov 3), [be5cdb9](https://github.com/mtalhak003/FIRMAVEX/commit/be5cdb97b8b7fba8bda6601d09866445d6eefc3d) (Nov 6).
- **Recorded decisions/evidence:** `test_actual_bundled_mps2_startup_and_behavior` adds four fresh-session scalar observations: `(2,1)`/`(2,0)` failure flags and separately initialized data, using existing executor/tool detection/cleanup. These assertions' presence is a source fact, not proof they ran in this audit. [Batch 22](batch22-verification-consistency.md#local-validation) records **138 focused passed/1 skipped** and **1,293 broader passed/17 skipped**, no failures/errors.
- **Limits and next recorded work:** retained input is opt-in; ARM wrappers do not silently traverse/reconcile nested receipt accounting. The recorded broader run lacked native RV32/Verilog tools, so it did not freshly qualify those journeys. Hash checks remain recorded-identity consistency, not authenticity. Windows runtime acquisition/qualification diagnostics became the next documented workstream.

## Windows candidate evidence and provenance

### 2026-11-07 — Batch 23A/C: diagnose runtime drift and preserve strict admission

- **Objective / implementation (Git/source):** retain sanitized expected/observed QEMU/GDB versions and hashes before private vendor cleanup. [23A `88ef1e1`](https://github.com/mtalhak003/FIRMAVEX/commit/88ef1e1f9f6dbb773f43dc30918fa6f9a16d16ef) preserves diagnostic contracts; [23C investigation](batch23-acquisition-investigation.md) records why rolling acquisition could not safely recreate the qualified older package set.
- **Recorded decision:** QEMU 11.1.3 is a different subject from the qualified 11.1.2 profile; GDB matching does not authorize the QEMU change. Missing immutable archives/dependencies cannot be repaired through a partial downgrade or weaker signatures. [Diagnostic contract](batch23-runtime-diagnostics.md).
- **Evidence / failures:** retained records attribute the mismatch to package 11.1.3-1/executable 11.1.3, while GDB 18.1 matched. This audit inspected the documents and code, not the original vendor-install artifact. A safe immutable old package closure was not established; no acquisition workaround was implemented.
- **Next recorded work / limits:** [candidate isolation `4d13cde`](https://github.com/mtalhak003/FIRMAVEX/commit/4d13cdea75df0cf6ca272430f412bcce7dbacac3) prepared a manual-only evidence workflow without changing production admission. [Runner-context fix `60d9e63`](https://github.com/mtalhak003/FIRMAVEX/commit/60d9e639a643e596860de75f8b5d014785c75d0d) corrected unsupported job-level `runner.temp` expressions; workflow acceptance alone did not qualify execution.

### 2026-11-08 — Batch 23D: candidate preflight, inventory and launcher repairs

- **Objective / changes (Git/source):** make isolated native evidence collection accept valid vendor layouts while keeping malformed/unsafe inputs rejected. Repairs cover [inherited signature policy `012adeb`](https://github.com/mtalhak003/FIRMAVEX/commit/012adeb1662bacf869bc48e38667061393a2f3a1), [case-sensitive package names `2e9a35f`](https://github.com/mtalhak003/FIRMAVEX/commit/2e9a35f7868560d09cc1426bb7d880cf9cdb9eb3), [closed vendor hardlink groups `2c1d335`](https://github.com/mtalhak003/FIRMAVEX/commit/2c1d335bdbccfa3eb8a340005d74d2c4f93f4272), [Python/module launcher `e27456c`](https://github.com/mtalhak003/FIRMAVEX/commit/e27456c297d6aacb4365005347b6afdf944f70bb), and [directory validation `237e9f6`](https://github.com/mtalhak003/FIRMAVEX/commit/237e9f64352d1aac7105f7461db5d76dacf57612).
- **Recorded decisions / failures:** only successful empty repository SigLevel inherits the global required/trusted policy; weak/failed queries still stop. All aliases in an accepted vendor hardlink group must remain inside the captured prefix; shared product checks are unchanged. Explicit setup-Python/module invocation avoids MSYS2 interpreter/direct-script import drift. Existing directories need directory validation, not a regular-file exception. [Candidate contract](batch23-runtime-candidate.md).
- **Validation:** source/tests retain focused regressions for each correction. Exact original logs and test totals for every failed attempt were not retrieved in this audit; implementation fixes do not prove every prior failure had the same cause. Later successful candidate evidence is recorded separately below.
- **Limits / next:** acquisition remains a signed rolling transaction, not an immutable distribution. Candidate-only source execution and production rejection do not qualify positive product paths, consumer acceptance or a new runtime profile.

### 2026-11-09 — Batches 24–26: candidate evidence review and offline verification

- **Objective / changes (Git/source):** [24 `0942b19`](https://github.com/mtalhak003/FIRMAVEX/commit/0942b199b9a8162854953ed29d47456e5bb59dca) classifies qualification gaps; [25 `8c4a6fa`](https://github.com/mtalhak003/FIRMAVEX/commit/8c4a6fa7d8611a93eb717b3231b84a6a5ff79dfe) adds bounded ZIP and signed-package verification; [26 `43f932a`](https://github.com/mtalhak003/FIRMAVEX/commit/43f932a2f8fa1c34762ae8088a427b328ee6fc54) links product rejection reports to identities and required native JUnit cases.
- **Recorded decisions:** distinguish archive consistency, publisher trust, complete DLL/package closure and promotion approval. Independently provisioned signing inputs must not come from the payload. Source/GUI/frozen rejection reports cannot be treated as positive execution. [24 gaps](batch24-qualification-gaps.md), [25 tooling](batch25-runtime-qualification.md), [26 readiness](batch26-promotion-readiness.md).
- **Evidence / failures:** public [source-stage run 42505041359](https://github.com/mtalhak003/FIRMAVEX/actions/runs/42505041359) succeeded at `237e9f6`; a fresh public-page check in this audit confirms the overall conclusion, not original receipt contents. Historical artifact IDs differed across requested/listed metadata; API downloads were forbidden, and missing bytes were not reconstructed. Batch 26 records 303 focused passed/5 skipped and 1,081 broader passed/21 skipped/27 deselected, not a new run here.
- **Limits / next:** actual signed archive closure, original-artifact review, full installed journeys and positive product execution remained open. Keep source/run/attempt/artifact identities bound before interpreting retained results.

### 2026-11-09 — Batch 27: installed lifecycle and normal product rejection

- **Objective / changes (Git/source):** [implementation `c42cdd0`](https://github.com/mtalhak003/FIRMAVEX/commit/c42cdd000dbd117dee558fd346aa8b653ac7bf3f) adds a private owned native installation lifecycle, console/GUI identity comparisons, installed worker/CLI rejection, startup smoke, same-package reinstall, sentinel preservation and awaited uninstall. ZIP validation links lifecycle/admission/frozen identities and the exact passed native test. [Scope and limits](batch27-qualification-closure.md).
- **Recorded decision:** refuse existing registered installations; keep binaries out of uploaded evidence roots; persist failures and preserve cancellation. No gate bypass enables candidate positive execution. Missing early uninstaller creation can leave a failed partial installation, never a successful cleanup claim.
- **Validation:** the historical local selections recorded 385 focused passed/6 skipped and 1,163 broader passed/22 skipped/27 deselected. [Run 42618949135](https://github.com/mtalhak003/FIRMAVEX/actions/runs/42618949135), attempt 1 at `c42cdd0`, subsequently passed the installed and earlier candidate checks; public job conclusions were inspected separately from its artifact. The user reports original artifact 13675538108 passed both verifier scopes with 19 receipts, 97 JUnit passed/10 skipped/zero failures/errors; original bytes/output remain independently unreviewed here. Full archive identity is preserved in the November 9 update below.
- **Limits / next:** this is rejection and narrow lifecycle evidence, not positive source/frozen/installed firmware qualification, distinct-version transition proof or real consumer acceptance. Freeze and authenticate complete runtime provenance before any separately authorized profile decision.

### 2026-11-09 — Batch 28: provenance controls and explicit readiness requirements

- **Objective / changes (Git/source):** [implementation `66fba9b`](https://github.com/mtalhak003/FIRMAVEX/commit/66fba9b9a339b300a57df0974487d675bdc9ea8c) adds read-only artifact-metadata binding and bounded static PE import auditing, with [repeatable original-ZIP procedure](batch28-artifact-verification.md), [runtime provenance workflow](batch28-runtime-provenance.md), [positive-execution proposal](batch28-positive-qualification-proposal.md) and [consumer checklist](batch28-consumer-windows-checklist.md).
- **Recorded decision:** required evidence stages fail closed; metadata/time consistency does not authenticate GitHub, and ordinary static imports do not establish complete Windows loader, package ownership or dynamic DLL closure. The unchanged production gate remains authoritative; qualification proposals do not execute or approve a new profile.
- **Validation / failures (historical record):** [readiness matrix](batch28-release-readiness.md) records 103 new-tool tests passed, 488 focused passed/6 skipped and 1,291 broader passed/26 skipped/31 deselected; overlapping selections are not additive. API `Forbidden` and publisher CONNECT HTTP 403 blocked original-archive/vendor acquisition; the later user-reported Windows ZIP pass is a separate evidence class, not an independent rerun of those blocked checks.
- **Limits / next:** authentic immutable signed packages/trust inputs, archive-to-installed ownership, native DLL behavior, notices/corresponding source, positive product journeys and standard-user/offline/accessibility/low-disk/recovery/signing acceptance remain unresolved. No production qualification or public-beta readiness is inferred.

## November 9, 2026 — Windows candidate evidence and release preparation

**CI observations.** Batch 27 native Windows [run 42618949135][run], attempt 1,
succeeded at `c42cdd000dbd117dee558fd346aa8b653ac7bf3f`. Successful checks included
ARM execution/resource behavior, source/GUI/frozen admission rejection, and the
installed-product lifecycle: installation, same-package reinstall, GUI startup,
external sentinel preservation and owned uninstall cleanup. These scoped checks
do not establish positive candidate product execution, distinct-version upgrades,
preservation of authoritative saved results or consumer-machine acceptance.

**User-reported artifact verification.** The user reports that the original
Batch 27 ZIP verifier **PASSED**, requiring both product-path and installed-path
checks: **19 receipts; 97 JUnit passed, 10 skipped, zero failures and zero errors**.
Artifact ID: `13675538108`. Original archive SHA-256:
`f66dd8611f9c149793114eaf9d3156118d93846bd96299e5cb00c7a91c793fd8`.
This result is user-reported; the original bytes and verifier output were not
independently reviewed in this Codex environment. Earlier retrieval limitations
remain historical observations, not a claim that the user's verification failed.

**Batch 28 delivery.** Commit
`66fba9b9a339b300a57df0974487d675bdc9ea8c` added read-only artifact-metadata
binding, bounded static PE import auditing, fail-closed provenance procedures,
a positive product-path qualification proposal and a consumer-Windows checklist.
Local validation recorded 488 focused tests passed with 6 skips, and 1,291 broader
regression/security tests passed with 26 skips and 31 deselections; neither
selection establishes native Windows qualification. See the
[Batch 28 readiness matrix](batch28-release-readiness.md) for scope and limitations.

**Remaining requirements.** Production qualification still requires authentic,
immutable signed packages and independent trust inputs; package/archive-to-installed
and native DLL closure; license/corresponding-source review; and separately
authorized positive source, frozen and installed product execution/reproduction/
export testing. Consumer acceptance still requires standard-user and enforced
offline operation, accessibility, low-disk/failure/recovery handling, real saved-data
preservation and release-signing review. QEMU 11.1.3 remains production-rejected;
no runtime approval or public-release readiness is claimed. Batch 29 has not begun.

[run]: https://github.com/mtalhak003/FIRMAVEX/actions/runs/42618949135

## 2026-11-10 — Batch 29: desktop project, readiness and export workflows

**Date basis:** execution/report date, November 10, 2026, UTC, from this development
session. This is a new implementation entry, not a retrospective completion-date
inference or a statement of work duration.

**Objective:** improve ordinary desktop project creation, firmware selection,
runtime feedback, cancellation states, saved-result navigation and report export
without changing execution contracts or runtime admission.

**Changes:** New Project clears the old project/result selection and asks before
discarding unsaved editor changes. A background static ELF check validates the
selected import image while distinguishing the open project's pinned image.
Recent-list reset recovers corrupt shortcut preferences without deleting projects.
Backend readiness persists visibly; cancellation remains visible despite late
progress, and terminal execution states preserve the recorded outcome. History
controls scroll and tab labels remain readable. Export feedback requires the
worker's successful response, matching destination and file/hash metadata; rejected
or malformed responses cannot leave an earlier export shown as successful. The
ARM workspace can explicitly open a confirmed export folder. See the
[operator and validation guide](batch29-desktop-workflows.md).

**Decisions and reasoning:** reuse the existing ELF validator, background project
task, supervised worker/export services and safe preference writer. Keep static
compatibility, tool availability and execution qualification distinct. Validate
export reply fields for truthful presentation; file hashing/writes remain service
responsibilities. Preserve exact error categories with bounded plain-text recovery
guidance. No evaluator, backend, protocol, runtime pin or admission changes.

**Commit references:** baseline
[`677bb7e94097ed9512be200ffb544350b4c4523e`](https://github.com/mtalhak003/FIRMAVEX/commit/677bb7e94097ed9512be200ffb544350b4c4523e);
implementation and five new test files
[`feb1fab8b65d3626a4389a2cc1424cd8f352d01f`](https://github.com/mtalhak003/FIRMAVEX/commit/feb1fab8b65d3626a4389a2cc1424cd8f352d01f).
This entry is a separate documentation follow-up to that implementation.

**Validation:** independently run on Linux x86_64, Python 3.12.14, PySide6 6.11.1,
pytest 9.1.1 and offscreen Qt. Exact commands, exclusions and skip reasons are in
the [validation section](batch29-desktop-workflows.md#validation-performed).
Overlapping selections are not additive.

| Claim | Result | Evidence class | Source and exact scope |
|---|---|---|---|
| New Batch 29 tests | PASS: 143 passed, no skips/failures/errors/deselections | Independently run local tests | Five `tests/desktop/test_batch29_*.py` files |
| Desktop and recent-project regressions | PASS within scope: 389 passed, 16 skipped | Independently run local tests | `tests/desktop tests/product/test_recents.py`; missing runtime/native platform cases skipped |
| Unfiltered application regression attempt | FAIL (environment): 2,079 passed, 106 skipped, 1 failed, 6 errors | Independently run local tests | Product/desktop/backend suites before final layout addition; missing ARM compiler causes the failure and setup errors |
| Final available-environment regressions | PASS within scope: 2,080 passed, 106 skipped, 6 deselected | Independently run local tests | Product/desktop/backend suites; one integration test excluded and six compiler-dependent cases deselected; not a complete-suite pass |
| Worker export round trips | PASS within synthetic-record scope | Independently run local tests | Real worker transport/Qt/files, synthetic saved inputs; hashes checked and source archives unchanged |
| Syntax, build inputs, workflow lint and whitespace | PASS within scope | Independently run local checks | Ten Python files; existing lock check; two relevant workflows via actionlint without unavailable ShellCheck; changed/additional files |
| Native Windows, macOS and firmware qualification of this revision | NOT PROVEN | Not run | Native hosts/runtime tools unavailable; no CI dispatch |

**Failures and resolutions:** initial new GUI tests exposed incorrect test-harness
assumptions about temporary Qt menu wrappers, wait predicates and signal-dictionary
identity. Tests now retain the menu owner, use bounded boolean/event waits and
compare record contents. Review also found stale export-success feedback on local
destination/start failures and insufficient confirmation of malformed worker
responses; implementation and regression tests address those cases. The unfiltered
ARM-tool failures remain disclosed and the existing tests remain unchanged.

**Limitations and blockers:** no ARM GCC, QEMU, ARM-capable GDB, RISC-V compiler or
Icarus here; no actual firmware execution is claimed. Linux offscreen UI and
synthetic archive tests do not establish Windows acceptance. Consumer usability,
installed/frozen journeys for this exact revision, accessibility, offline and
low-disk/recovery checks remain open. QEMU 11.1.3 remains production-rejected;
macOS remains preview-only. Prior provenance and signing blockers are unchanged.

**Next steps:** run equipped native regression/GUI checks for this revision, then
exercise project creation, real bounded execution, cancellation, saved-result
reopening and export through an installed application. Keep runtime qualification
and consumer acceptance separate from presentation improvements.

**Approval/traceability:** the user's Batch 29 task authorized implementation,
tests, commits and normal fast-forward delivery to `product/desktop-batch11`.
No CI dispatch, release or runtime-profile promotion was authorized. Main, frozen
research and protected private evidence remain outside this batch's work.

## 2026-11-11 — Batch 31: Windows-focused desktop regressions and transition fixes

**Date basis:** report/validation date, November 11, 2026, Asia/Karachi. The
implementation commit records the same local date. This resumed batch's report
does not assign all investigation or work to one day or imply elapsed effort.

**Objective:** exercise practical desktop failure/retry behavior, prepare native
Windows checks and close confirmed source-GUI defects while preserving admission,
evidence and backend execution contracts.

**Changes and reasoning:** new tests reproduced silent discard of unsaved edits
on Open/recent and stale result/export context after switching projects. The
desktop reuses a default-No discard confirmation for New, Open/recent and both
example entry points. Verification completes before the old editor/selection is
replaced. Successful project adoption clears prior result/export/progress
presentation without deleting files or resetting evaluator accounting.

Two new test files add 28 cases: real bundled-ELF import/static inspection at
multilingual/metacharacter paths; retry after invalid destinations, corrupt
preferences, synthetic runtime rejection, export/file-manager failure and
interrupted-state inspection; and six actual-Windows sharing/attributes/locking/
case-normalization cases. Native tests use real Win32 APIs and a second Python
process, and explicitly skip on other operating systems. Qt URL capture does not
launch or qualify Explorer. The [Windows procedure](batch31-windows-validation.md)
separates source host tests, admitted real ARM execution, frozen/installed paths
and manual consumer acceptance, with private outputs outside the checkout.

**Commit references:** baseline
[`bd875f22cc2604a7e397166177cd82c6e81bc07f`](https://github.com/mtalhak003/FIRMAVEX/commit/bd875f22cc2604a7e397166177cd82c6e81bc07f);
implementation and regression tests
[`31037ac904ed0affb1e3359781d40ebd546fc56d`](https://github.com/mtalhak003/FIRMAVEX/commit/31037ac904ed0affb1e3359781d40ebd546fc56d).
This documentation follows that implementation as a separate commit.

**Validation:** independently run on Linux x86_64, Python 3.12.14, PySide6 6.11.1,
pytest 9.1.1, with `QT_QPA_PLATFORM=offscreen`. Exact commands/exclusions are in
the [local validation record](batch31-windows-validation.md#validation-performed-in-this-development-environment).
Overlapping selections are not additive.

| Claim | Result | Evidence class | Scope |
|---|---|---|---|
| Existing Batch 29 baseline | PASS: 143 passed | Independently run local tests | Five existing test files before fixes |
| New regressions after fixes | PASS within scope: 22 passed, 6 skipped | Independently run local tests | Real Qt/temporary filesystem and explicit synthetic feedback; Windows-only cases skipped |
| Desktop/recent regressions | PASS within scope: 411 passed, 22 skipped | Independently run local tests | Existing runtime/native skips plus six new Windows skips |
| Unfiltered application tests | FAIL (environment): 2,102 passed, 112 skipped, 1 failed, 6 errors | Independently run local tests | ARM compiler unavailable; existing assertions retained |
| Available-environment regressions | PASS within scope: 2,102 passed, 112 skipped, 6 deselected | Independently run local tests | Product/desktop/backend suites; one integration test excluded and six runtime cases deselected; no full-suite pass claimed |
| Syntax, lock versions, workflow lint and whitespace | PASS within scope | Independently run local checks | Three Python files and existing workflow/build inputs; ShellCheck unavailable |
| Native Windows source/frozen/installed behavior at this revision | NOT PROVEN | Not run | Linux host; no Windows runner, runtime tools or PowerShell available; no CI dispatch |

**Failures and resolutions:** three initial targeted tests failed before repair,
demonstrating missing discard confirmation and stale selection. Those journeys
now pass alongside their failure/retry cases. The unfiltered missing-ARM-tool
failure and six setup errors remain visible; explicit local exclusions do not
weaken the tests or qualification policy.

**Limitations and next steps:** execute the new host tests and unchanged
required-runtime tests on native Windows using the exact reviewed revision and
admitted runtime. Keep QEMU 11.1.3 production-rejected. Obtain matching native
frozen/installed builds, then test visible GUI, actual Explorer opening,
standard-user ACLs, offline behavior, accessibility, low-disk/recovery and
data-preserving lifecycle transitions. The targeted discard guard does not
cover Quit or every configuration handoff; do not describe it as universal
unsaved-edit protection. Host CI selection already includes `tests/desktop`;
neither its definition nor old successful runs prove these new native cases ran.

**Approval/traceability:** the user authorized Batch 31 implementation, testing
and normal fast-forward delivery to the development branch. No workflow dispatch,
installer release, runtime promotion, main change or private-evidence access was
authorized or performed.

## 2026-11-12 — Batch 31 Windows regression repair: oversized test identity

**Date basis:** repair report date, November 12, 2026, Asia/Karachi. The actual
date of the user's Windows execution was not independently established.

**Original observation — user report:** native Windows at
`be355eec3760c9d0d6a01246b30a0e10d88b6c10` reported **169 passed, 1 skipped,
2 errors** in Batch 29+31, including an environment variable over 32,767
characters for the oversized corrupted-preference case. The complete original
traceback was not available; those counts are not an independently reviewed
native transcript.

**Cause and repair — independently inspected source/collection:** pytest used the
65,537-byte input as part of a 65,652-character node ID, then assigned it to
`PYTEST_CURRENT_TEST`. Both setup and teardown perform that assignment. Linux
diagnostic emulation of Windows' size admission reproduced two errors before the
test body on that case. Explicit short IDs now label all seven inputs; the full
oversized bytes and all assertions remain unchanged. A collection guard, following
the existing malformed-frame regression pattern, enforces seven stable IDs and
bounded node/stage labels. It failed before repair and passes afterward.

**Validation — independently run on Linux:** affected preference plus complete
CI-diagnostics modules: **46 passed**, zero skips/failures/errors/deselections.
Original Batch 29+31 selection: **165 passed, 6 native-Windows skips**, zero
failures/errors/deselections. The 171-case collection's largest node ID is now
169 characters; its largest full environment entry is 200 UTF-16 units. All seven
affected cases pass the limit emulation. Desktop/recent regressions passed
**411 tests, 22 skipped**, zero failures/errors/deselections. No native Windows
execution or CI dispatch occurred here. See the
[repair record and rerun procedure](batch31-windows-validation.md#native-windows-follow-up-corrupted-preference-parameter-id-repair).

**Scope and remaining evidence:** this repeats a test-identity failure class
previously seen in [Batch 7 diagnostics](ci-diagnostics.md) and
[Batch 20](batch20-windows-repair.md); application resource limits and firmware
execution are not the failing boundary. Production code, runtime pins, security
policy, frozen research and workflows are untouched. Retain the original Windows
failure alongside the forthcoming native rerun; do not infer its success from
collection checks or Linux emulation. The user authorized only this tested repair
and normal fast-forward delivery to the development branch, with no main change
or runtime promotion.

## 2026-11-12 — Batch 31 user-reported native Windows regression rerun

**Date basis and evidence:** report recorded November 12, 2026, Asia/Karachi.
The exact execution timestamp was not supplied. This is **user-reported native
Windows host/UI test execution**, not a run independently executed by Codex or
an independently reviewed original log/JUnit artifact.

**Tested revision and environment:**
[`f8efe1e109d608789a75f154a8516b8e053bc014`](https://github.com/mtalhak003/FIRMAVEX/commit/f8efe1e109d608789a75f154a8516b8e053bc014),
native Windows PowerShell **7.7**, Python **3.12.10**. The user reports
**171 passed, 1 skipped, zero failures/errors, 20.58 seconds** for the seven
selected Batch 29/31 desktop files and targeted diagnostic collection guard.
The single skip's reason and per-case output were not provided.

**Failure and repair chain:** preserve the earlier user-reported **169 passed,
1 skipped, 2 errors** at `be355eec…`. The oversized corrupted-preference input
produced an excessive pytest identity; `f8efe1e…` supplied short explicit IDs and
a collection guard while preserving the full input and assertions. The latest
user-reported rerun supports resolution of that overflow in the tested selection.
It does not relabel the Linux emulation or earlier local results as native tests.
See the [full scoped record](batch31-windows-validation.md#user-reported-native-windows-rerun-at-the-repair-revision)
and [troubleshooting chain](../development/troubleshooting-history.md#2026-11-12--batch-31-windows-test-identity-overflow-and-reported-rerun).

**Limits and next steps:** the reported duration measures the test selection,
not firmware execution. Guest execution, frozen/installed acceptance, consumer
usability and production runtime qualification remain separate outstanding
requirements. No runtime pins, admission, research or production functionality
changed; QEMU 11.1.3 remains production-unqualified. This update records evidence
without dispatching CI or accessing private Windows evidence.

## 2026-11-12 — User-reported Windows GUI launch and runtime blockers

**Evidence/date basis:** native Windows observations reported by the user on
November 12, 2026 (Asia/Karachi); not independently executed by Codex. Original
tool output/events, exact observation times, source revision and executable/DLL
hashes were not supplied for these checks. They are separate from the earlier
171-pass regression report at `f8efe1e…`.

**Reported observations:** the source GUI launched with
`.venv\Scripts\python.exe -m firmavex.desktop.app`, while the generated
`firmavex-desktop.exe` launcher was blocked by Windows Application Control and
the first-launch wizard's runtime check failed. Installed QEMU ARM was the
11.1.0 development build `v11.1.0-12130-ge470268ff4`; ARM GDB was
`16.3.90.20250906-git`. GDB version/configuration commands succeeded, but its
configuration reported `--without-python` and the embedded Python capability
test exited **1**. MSYS2 installed successfully, but launching mintty was blocked
on `msys-2.0.dll`. The user reports Code Integrity Event **3077**, policy
`0283ac0f-fff1-49ae-ada1-8a933130cad6`, and an enforced
`VerifiedAndReputableDesktop` Smart App Control policy in `CiTool --list-policies`.

**Interpretation and next steps:** preserve three separate boundaries: missing
GDB Python capability, versions outside the exact QEMU 11.1.2/GDB 18.1 production
profile, and host application-control blocks. The exact wizard failure stage
and original policy-event/file correlation remain unreviewed. Retain private
diagnostics and seek trusted compatible packages accepted by both host policy
and existing admission; keep firmware execution blocked if unavailable. Do not
disable controls, substitute DLLs or approve a different runtime. The source
module launch does not qualify the generated launcher, frozen/installed product
or guest execution. See the [full observations and safe next steps](batch31-windows-validation.md#user-reported-gui-launch-and-runtime-compatibility-findings)
and [troubleshooting entry](../development/troubleshooting-history.md#2026-11-12--windows-source-gui-launch-with-runtime-and-policy-blockers).
No production, research, admission or workflow change accompanies this record.

## 2026-11-12 — User-provided manual Windows GUI checks

**Evidence/date basis:** manual native Windows GUI observations supplied by the
user on November 12, 2026, Asia/Karachi; not independently reproduced by Codex.
Exact source revision, observation timestamps and original project/output files
were not supplied for independent review.

**Observed workflow:** FIRMAVEX launched through Python while the generated
`.exe` launcher remained blocked by Windows Application Control. The built-in
compiler-free Cortex-M3 project was created/opened and statically inspected
without QEMU/GDB execution. The UI identified ELF32, ARMv7-M, little-endian,
`mps2-an385`, and required input/failure/ready/completion symbols. The reported
firmware SHA-256 is
`bdb370112a4fe834dae7127b75c3d38f7ffaf125af6dc4e02a6f24c4cae940ff`;
it was not independently rehashed here. Consistency was `stable_observed` with
`atomic=false`, not an atomic snapshot. Configuration save and subsequent reopen
preserved the visible bindings; no byte-for-byte preservation claim follows.

**Observed failure/empty states:** Validate firmware & tools returned
`dependency_probe_failed` with GDB stderr indicating unsupported embedded Python.
Testing & progress showed no selected run, 0% progress, no observations and
disabled cancellation. Results & reproduction showed no result, triggering input
or execution evidence, with reproduction/recovery disabled. These are UI states,
not independent measurements of guest activity or execution accounting.

**Limits and next steps:** keep scoped manual host/UI acceptance separate from
static validation, runtime qualification, firmware execution and frozen/installed
acceptance. The Smart App Control/MSYS2 blocks and missing compatible admitted
runtime remain separate unresolved blockers. Preserve security controls and pins;
see the [manual GUI record](batch31-windows-validation.md#user-provided-manual-windows-gui-checks)
and [troubleshooting follow-up](../development/troubleshooting-history.md#2026-11-12--manual-static-project-workflow-with-runtime-failure).
This update records observations only; it changes no production behavior or
research and dispatches no CI.
