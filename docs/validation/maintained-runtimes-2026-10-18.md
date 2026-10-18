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

The widened lock changes only the necessary NumPy branches, lxml 6.1.3,
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
