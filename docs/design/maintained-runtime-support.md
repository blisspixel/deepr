# Maintained runtime support and verified installation

Decision for issue #225, 2026-10-18. Written before implementation.

Support ordinary CPython 3.11 through 3.15 and make 3.15 the development,
managed-install and single-version CI default after the actual matrix passes.
The package floor, classifiers, Ruff/mypy target and deployment helper package
must agree. Rewrite the three PEP 695 aliases in two modules as equivalent TypeAlias
assignments.
The 3.11 baseline parser identified exactly those two syntax failures.

Preserve OKF link refusal with the existing symlink check and a shared junction
helper based on lstat and the Windows mount-point reparse tag. Missing paths and
junction-probe errors stay false, preserving the existing standard-library
behavior. Root validation, inventory and no-follow cleanup use that helper.
Test synthetic tags
and real Windows junctions, including protection of external target contents.
Do not introduce a compatibility dependency or ctypes bridge.

Change both frozen core and full-test matrices to all five maintained minors.
Add Windows installed/core and boundary tests at the floor and default; retain
all ordinary unit coverage gates. Installer and upgrade verification accepts
only final CPython in that same explicit set. Managed uv install requests 3.15;
pipx ownership and existing-environment refusal remain intact. Public-installed
acceptance and clean-wheel stdio smoke run on the promoted default.

The observed stable NumPy 2.5.4 and lxml 6.1.3 distributions supply cp315 Linux,
Windows and macOS wheels. Upgrade only those lock entries plus resolver-required
3.11 branches, inspecting every changed package. PyYAML 6.0.3 remains canonical;
verify its source install and safe parsing rather than bypassing it. Run locked
full unit suites at 3.11 and 3.15 locally, all minors in CI, and a dependency audit.

Use official python:3.15-slim multiarch digest recorded in the evidence receipt
for all three Dockerfiles. Build and smoke all three with no cloud deployment.
Local Docker socket is inaccessible and sudo requires a password; use standard
public hosted CI runners for the actual isolated image builds. No fabricated
local container acceptance claim.

Pin setup-uv v10.3.0 to its observed commit. Pin Node 24.22.0 LTS, retain npm
12.0.1, change engines to >=24 and reconcile package-lock metadata. Run npm ci,
lint, tests, build, existing browser workflows and archive byte verification.
Node 26 is not LTS on the observation date and is not promoted in this change.

Primary observations and source URLs are retained in platform-current-primary,
platform-python315-docker-receipt, platform-latest-wheels and the baseline
syntax receipt. Publication requires exact-head green PR, current base,
title-only squash, exact resulting main green, exact-main artifacts, checksums,
clean-wheel checks and public installer acceptance.

Primary sources checked 2026-10-18:

- https://www.python.org/downloads/release/python-3150/
- https://docs.python.org/3.11/library/os.html#os.stat_result.st_reparse_tag
- https://raw.githubusercontent.com/python/cpython/v3.12.0/Lib/ntpath.py
- https://nodejs.org/dist/index.json
- https://github.com/astral-sh/setup-uv/releases/tag/v10.3.0
- https://github.com/astral-sh/uv/releases/tag/0.13.0
- https://github.com/pydantic/pydantic/releases/tag/v2.14.1
- https://pypi.org/project/aiohttp/3.14.5/
- https://pypi.org/project/jiter/0.17.0/
- https://pypi.org/project/numpy/2.5.4/
- https://pypi.org/project/lxml/6.1.3/
- https://pyyaml.org/wiki/PyYAMLDocumentation
- https://pypi.org/project/pip-api/0.0.35/
- https://learn.microsoft.com/en-us/windows/win32/fileio/reparse-point-tags

The complete tracked Python syntax probe at 3.11 finds only the two alias
modules. It does not prove runtime compatibility. Source callers and tests are
traced directly because no current codegraph is available. No spend, mutation
or provider capability contract is widened by the toolchain promotion.

The first regression run exposed that POSIX stat does not export the Windows
mount-point tag constant. Keep its documented numeric identity in the owning
helper, and use lstat's optional Windows field without traversing the target.
The first installed-wheel check preserved the same failure before correction.

NumPy 2.5's installed type stubs require Python 3.12 syntax. A mypy 3.11
language target cannot parse those stubs from the 3.15 runtime environment.
CI therefore resolves a second frozen 3.11 environment and uses mypy's
`--python-executable` to inspect its actual compatible dependency types, then
checks the promoted runtime separately at 3.15. Strictness and imported types
remain enabled. This follows the [mypy dependency-discovery contract](https://mypy.readthedocs.io/en/stable/command_line.html#cmdoption-mypy-python-executable).

The audit command also reproduced pip-api 0.0.34 importing the removed
`sre_constants` module at 3.15. The verified upstream Apache-2.0 0.0.35
release removes that vendored parser path. Upgrade that existing transitive
tool dependency in the lock; do not add a standard-library shim or disable
the audit. The original failure log and inspected wheel hash are retained.

Hosted acceptance revealed two additional platform boundaries. uv 0.11.32's
managed-download manifest selected CPython 3.15.0b4, and the stable-only
installer correctly refused it. Pin uv 0.13.0 and request managed 3.15.0 exactly
in setup, self-upgrade and the development pin. A missing final download must
fail before replacing a managed installation; a beta is not a substitute.

Update the existing native dependencies to their verified current compatible
releases with cp315 wheels: aiohttp, jiter, librt, MarkupSafe, msgpack, Pydantic
and its core, and setproctitle, with resolver-required yarl and typing-inspection.
Their declared licenses remain Apache/MIT/BSD compatible. Source-only Brotli
remains in the full/search extras and requires a C toolchain. The HTTP image
compiles its frozen environment in a build stage, then copies the application
into the same pinned slim runtime without compilers. Core and worker images
retain the direct frozen install. Docker smoke checks run without network and
assert the final images have no gcc.

The contained-plugin job previously downloaded source distributions into its
offline wheelhouse, which cannot build PyYAML without build dependencies.
Export the frozen core requirements with hashes, build their wheels before
the offline phase, then install only those wheels without network. This keeps
the containment proof and the lock authority instead of bypassing isolation.

A subsequent clean Windows 3.15 wheel install exposed PyYAML 6.0.3 attempting
its optional C accelerator without MSVC. Its upstream setup contract supports
`PYYAML_FORCE_LIBYAML=0`. Default that setting only in managed installation and
upgrade subprocesses, preserve explicit operator values, and restore the
PowerShell caller environment. Frozen uv source builds carry the same
package-specific setting. Prebuilt wheels are unchanged. Deepr uses canonical
`safe_load`, never a C-specific loader; do not replace YAML or weaken unsafe-tag
refusal. Clean-wheel acceptance uses a private cold uv cache so the full-test
environment cannot mask dependency compilation. Manual installers document the
source-build setting. Primary setup source and uv configuration were inspected:

- https://github.com/yaml/pyyaml/blob/6.0.3/setup.py
- https://docs.astral.sh/uv/reference/settings/#extra-build-variables

Final compatibility inspection found another floor-sensitive no-follow boundary:
Agent Plugin validation treated an absent `Path.is_junction` as no junction.
Reproduce root/nested package junction acceptance without that 3.12 API. Move
the existing lstat/tag identity into utils.paths as a shared compatibility seam;
OKF keeps its prior false-on-probe-error wrapper, while package validation keeps
its fail-closed error policy. Native Windows package tests join both platform
jobs. A package whose files otherwise match the immutable manifest must still
refuse junctions before archive creation. Preserve external target bytes.

## Advisory-driven lock repair (2026-10-20, #277)

The first #275 PR run stopped at both existing dependency audit gates:
Certifi 2026.7.22, follow-redirects 1.16.0 and Vite 8.1.5 are now covered by
upstream advisories. Preserve the failed logs and update the affected locked
packages in a separate increment before updating the historical-review PR.

Use Certifi 2026.10.19, follow-redirects 1.16.1 and Vite 8.1.6. These are the
compatible patched releases on the existing lines. The registry metadata
retains MPL-2.0 for Certifi and MIT for both npm packages; Certifi has a universal
Python wheel and requires Python 3.7+, while Vite supports the pinned Node 24.
Keep Python, Node 24.22.0, npm 12.0.1, uv 0.13.0 and all audit thresholds fixed.
Tighten Vite's declared minimum patch and change only the affected locks and
required coupled packages. Do not suppress advisory IDs or disable TLS checks.
Declare Certifi's patched minimum in core metadata as well: an existing wheel
installation must not retain an affected transitive version merely because it
satisfies HTTPX's broader constraint. This promotes an existing dependency;
it does not add another library or cap future trust-store security updates.

Certifi's CA-store repair intentionally changes trust in affected emSign roots.
It adds no request, credential, spend or model capability. The Vite advisories
cover its bundled editor-launch helper, including Windows paths. Rebuild the
existing frontend archive with the pinned tooling, run frontend lint, tests,
build and browser checks, inspect actual dashboard captures, and verify wheel
contents. Both Python dependency branches must pass their audits, full offline
tests and strict type checks. Existing audit gates are the regression for these
upstream dependency versions; do not replace them with a version-only test.

Primary records checked before the lock update:

- [Certifi advisory](https://github.com/pypa/advisory-database/blob/main/vulns/certifi/PYSEC-2026-4320.yaml).
- [follow-redirects array headers](https://github.com/advisories/GHSA-q3jh-wrc6-jgq8)
  and [header escaping](https://github.com/advisories/GHSA-8r9p-f939-6h3c).
- [Editor argument escaping](https://github.com/advisories/GHSA-698v-4r3x-3vcv),
  [editor flag handling](https://github.com/advisories/GHSA-r825-w8mm-5pxw) and
  [Windows path validation](https://github.com/advisories/GHSA-587h-7wmj-h5pm).

Registry metadata and original audit failures are retained in the existing
gitignored task evidence. A green audit is dependency evidence, not a claim
that every application path has been exhaustively assessed.
