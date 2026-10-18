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
