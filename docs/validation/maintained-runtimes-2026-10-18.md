# Maintained runtime validation, 2026-10-18

Issue #225. See the [decision](../design/maintained-runtime-support.md).
This record separates local evidence from the required hosted platform and
publication checks. Logs and original failed trials remain in the ignored
`.agent/reader-evidence/` directory.

The baseline CPython 3.11 syntax probe inspected all 1,522 tracked Python files
and found two incompatible modules, containing three PEP 695 aliases. Removing
the 3.12-only Path API reproduced publication failure before mutation. Root
validation, inventory and cleanup now share the documented Windows mount-point
tag check; symlinks retain their existing treatment.

The first repair run failed 18 export tests because POSIX stat does not export
the Windows-only tag constant. The initial installed wheel preserved that same
failure. Keeping the tag's documented numeric identity in the owning helper
corrected it: all 28 local export tests passed. The added native Windows
junction test is intentionally platform-specific and must pass on Windows;
Linux does not establish that acceptance. It checks root and nested junctions
and preserves an external protected file during forced replacement.

An initial standalone installed-wheel probe also omitted a required `force`
argument. That probe was corrected to call the actual publication contract.
No publication assertion or safety gate was relaxed.

Clean core wheels were then installed in new directories with spaces at both
ends of the supported range. CPython 3.11 used NumPy 2.4.6; CPython 3.15 used
NumPy 2.5.4. Both used canonical PyYAML 6.0.3 and passed safe YAML parsing,
unsafe-tag refusal, vector arithmetic and no-follow export checks. Native CLI
entry points passed version/help, offline doctor, empty expert inventory and
write-free research preview. Existing clean-wheel stdio checks passed both MCP
protocol eras and host-profile integration. These were offline checks at `$0`.

The first widened lock changed the necessary NumPy branches, lxml 6.1.3,
pip-api 0.0.35 and three resolver-required backports for Python 3.11. The
new NumPy/lxml releases provide cp315 wheels on the observed ordinary Linux,
Windows and macOS platforms. PyYAML remains a source install at 3.15; a locally
built C extension worked, but no C-extension requirement is imposed.

Strict typing passed all 293 island files at both 3.11 and 3.15. An initial
3.11-target check against installed NumPy 2.5 stubs failed on newer stub syntax.
CI now resolves the actual frozen 3.11 dependency branch for floor checking,
then separately checks the promoted runtime; imported types stay enabled.
The wider floor baseline has the same 196 error locations/codes in 60 files;
two messages render the older pathlib signature. At 3.15, nine existing
asyncio annotation errors disappear, leaving 187 in 55 files. No ignore was
added. The changed export module also passes a separate strict check.

The initial 3.15 dependency audit reproduced pip-api 0.0.34's import of the
removed `sre_constants` module. The inspected Apache-2.0 0.0.35 upstream wheel
removes that vendored-parser path. After the targeted lock update, the audit
passed. The 3.11 dependency branch also passed its audit. There is no local
standard-library shim or audit bypass.

Node 24.22.0 LTS with the existing npm 12.0.1 completed frozen installation,
lint, unit tests, production build and all 102 browser layout/state checks.
The rebuilt frontend archive is byte-identical to the committed archive.
The npm audit found no vulnerabilities. Node 26 is not yet LTS at observation.

The local Docker client could not access its daemon, and passwordless sudo
was unavailable. No local image-build acceptance is claimed. Blocking hosted
jobs build all three digest-pinned 3.15-slim images and exercise imports and
MCP conformance with runtime networking disabled. Native Windows/macOS jobs
exercise boundary tests, installer ownership and isolated installed wheels at
3.11 and 3.15. Their exact-head results, complete unit/coverage results and
public-installer acceptance accompany the matching PR and release.

No current codegraph was available; source callers and tests were traced.
Runtime compatibility does not qualify expert advice or advance S0.

The first full local suites each recorded 13,324 passes, 21 skips and three
failures: the existing container contract still expected the old 3.12 image.
Its expected immutable image and uv pins are updated, with an added guard for
the compiler-free HTTP runtime stage. No test of frozen dependency authority
was removed. These runs do not establish acceptance of the later native lock.

Initial hosted container builds failed compiling aiohttp without gcc. The
Windows full environment built, but its seven installer/upgrade failures
exposed that uv 0.11.32 had selected managed Python 3.15.0b4. The plugin job
also exposed source distributions in an offline wheelhouse without their
build dependencies. All three failures and native wheel inventories remain
retained. uv now uses 0.13.0; managed setup/upgrade request final 3.15.0 exactly;
the platform receipt refuses a prerelease. The HTTP compiler stays in a build
stage, and the plugin's frozen, hash-checked core wheelhouse is built before
offline installation. Compatible native-package lock updates supply the other
missing cp315 wheels. Brotli remains source-only in full/search extras.

Two later concurrent unit reruns exhausted the workstation's tmpfs inode
capacity. Their setup errors include durable-write quota failures; these are
retained as environment failures rather than assertion acceptance. Both were
interrupted. The task's completed and interrupted temporary roots were archived
with verified tar integrity and SHA256 receipts before releasing their inodes.
Subsequent local full suites run serially with explicit free-byte and free-inode
admission, preserving coverage and the socket guard. No source gate was lowered.

The serial full local suites at commit `3c9f9b09` each passed 13,328 tests with
21 skips, with independently enforced coverage of 85.46% on 3.15 and 85.53%
on 3.11. These precede the final installer build-setting correction. Their
temporary roots were archived with integrity and hash receipts.

Hosted Windows 3.15 then passed the installer tests on final 3.15.0 but failed
a clean core wheel install: PyYAML tried its optional C accelerator without
MSVC. A cold-cache source build with upstream `PYYAML_FORCE_LIBYAML=0` passed
on final 3.15 with no accelerator, nested/alias parsing and unsafe-tag refusal.
Seven default-setting regressions failed before the fix; explicit operator
choices already passed. Managed installers and upgrade now scope that default
to installation, preserving explicit values and caller/runtime environments.
All 328 focused installer, upgrade, release, container and plugin checks pass.
Final exact-head native acceptance must include the same production build
setting and a private cold cache; prior Windows success is not substituted.
