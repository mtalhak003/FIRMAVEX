# Installing the Batch 1 product foundation

Batch 1 is an installable command-line engine and supervised worker foundation.
It is not a finished desktop application or a native installer. No GUI is
included. Linux real-firmware validation is recorded in `batch1.md`; Windows
and macOS are not established as supported by Linux tests.

Python 3.11 or newer is required. The Python runtime dependency is
`pyelftools>=0.32,<1`. QEMU and ARM-capable GDB are external executable
dependencies, not Python packages. ARM GCC is required only when building
firmware, including the independent product example. GDB must support embedded
Python, `hashlib`, ARM remote debugging, and the stop events used by the runtime.

## Ubuntu and WSL2 source installation

Run in a checkout of the reviewed product branch. Keep outputs outside the
checkout. Installation and these commands do not use the research campaign.

```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip \
  gcc-arm-none-eabi qemu-system-arm gdb-multiarch

python3 -m venv "$HOME/.venvs/firmavex-product"
source "$HOME/.venvs/firmavex-product/bin/activate"
python -m pip install --upgrade pip
python -m pip install '.[dev]'
firmavex --help
firmavex doctor
```

`doctor` checks actual executable capabilities. A missing or incompatible tool
is a blocking runtime error; no simulated measurement replaces it. The product
resolves ARM-capable GDB directly and does not require the research-era
`arm-none-eabi-gdb` symlink. Tool paths can be set explicitly in project JSON.

`firmavex` and `python -m firmavex` invoke the same CLI. Existing research code
retains the `src.firmavex` namespace; it is not also loaded as
`firmavex.evaluation` or another engine alias. `firmavex.product` uses that
single research-engine identity.

## Independent example and bounded demonstration

These commands execute new, independent product firmware. They do not read or
run the development/held-out research corpus or Step 19 campaign. Destinations
must not already exist; change the suffix before repeating a command.

```bash
firmavex build-example --output-dir "$HOME/firmavex-product/example-1"
# Read the reported configuration path, then:
firmavex validate "$HOME/firmavex-product/example-1/project.json"
firmavex run "$HOME/firmavex-product/example-1/project.json" \
  --output-dir "$HOME/firmavex-product/run-1"
firmavex inspect "$HOME/firmavex-product/run-1"
firmavex reproduce "$HOME/firmavex-product/run-1" \
  --output-dir "$HOME/firmavex-product/replay-1" --attempts 3
firmavex export "$HOME/firmavex-product/run-1" \
  --output-dir "$HOME/firmavex-product/export-1"
```

For the full bounded demonstration in one command:

```bash
firmavex demo --output-dir "$HOME/firmavex-product/demo-1"
```

Outputs distinguish configured failures, non-discovery, infrastructure errors,
and interruption. Charged evaluator attempts are not independently verified
physical execution counts. Saved triggering vectors can be replayed under the
recorded image/configuration/tool context. This is emulated firmware testing,
not hardware validation or a claim that non-discovery establishes safety.

## Importing compatible user firmware

The initial boundary is a symbolized ARM Cortex-M3 ELF compatible with QEMU
`mps2-an385`. The firmware needs a function reached after input initialization,
a distinct completion function, and named uint32 inputs and failure status.
The initial interface accepts scalar symbols or individual array elements,
with one inclusive domain shared by the ordered input vector. It does not
support arbitrary MCU images, raw BIN files, peripheral simulation outside
the board, physical hardware, arbitrary GDB expressions, or automatic detection
of every fault/vulnerability.

The example's generated `project.json` is a starting point for the version-1
JSON configuration. Paths relative to the configuration file resolve from that
file's directory. Configure firmware, input bindings, input-ready/completion
functions, failure binding/value, strategy/seed, budget, and timeouts. Validate
before running. Random and guided require explicit seeds; guided requires
signature collection. Defaults for product projects are separate from frozen
research settings.

## Tests and distributable source

```bash
python -m pytest -q tests/product
python -m build --outdir "$HOME/firmavex-product/distributions"
```

The wheel contains the product namespace and the unchanged `src.firmavex`
research modules. For installed research API compatibility, it also contains
the already-public corpus source/support files and manifests at the path
expected by the legacy compiler. It does not contain research oracles, campaign
archives, results, generated ELFs, tests, or a prebuilt runtime. Product commands
do not select research or held-out fixtures. A future native installer can
reduce its research resources once a compatible resource interface exists.
The source distribution includes product tests and product documentation.

The optional `desktop` extra installs PySide6 for future interface work; it
does not create a GUI. Do not install it to obtain functionality absent from
this batch.

## Windows and macOS status

Python packaging and platform-neutral tests can be exercised natively. Actual
QEMU/GDB firmware behavior, descendant-process cleanup, tool distribution,
code signing, installers, and supported OS/version matrices still require
native qualification. No Windows/macOS compatibility claim follows from a
Linux or WSL2 run. A future runtime manager must use tested tool packs; Batch 1
currently depends on externally installed tools and explicit capability checks.
Native Windows firmware dispatch is blocked in Batch 1 until descendant-process
ownership and cleanup are implemented and qualified, for example with Job
Objects. A successful `doctor` or Python installation does not override that
execution gate or establish Windows firmware support.
