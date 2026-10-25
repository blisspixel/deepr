# Filelock security floor

Status: proposed compatible dependency repair, 2026-10-25.

The full-environment audit after the narrow Brotli lock repair reports
CVE-2026-112940, CVE-2026-112913 and CVE-2026-112907 against filelock 3.32.2.
The existing `<4` dependency ceiling excludes the patched 4.2.1 release.
These are affected dependency selections, not evidence of exploitation.

## Decision

Require `filelock>=4.2.4,<5.0.0` and update only its authoritative lock record
and the matching project dependency metadata. Keep the separate Brotli repair
limited to its two decoder records. Do not change locking or persistence code.

Deepr imports `FileLock` and `Timeout`; it does not use `SoftReadWriteLock`,
whose reader/writer protocol changed at 4.0. The existing string paths,
timeouts, `thread_local=False`, context managers and explicit acquire/release
remain supported. The installed locked virtualenv accepts filelock `<5`.
Filelock 4.2.4 retains the project's Python 3.11 floor, MIT license and pure
Python wheel. Include 4.2.3's Python 3.15 exit repair rather than stopping at
the first security fix. No new dependency or automatic update policy is added.

## Alternatives

- Staying below 4 leaves the blocking advisories unresolved.
- Ignoring advisories would weaken the existing audit gate.
- Replacing the cross-platform locking implementation would enlarge risk in
  accounting, expert writes and lifecycle admission without a demonstrated need.

## Acceptance

Exercise existing overlap, belief transaction, lifecycle, atomic I/O and cost
authority regressions, strict types against the documented floor environment,
the full unit coverage gate, dependency audit, wheel/sdist build and isolated
Windows wheel/stdio installation checks. Record failures and unavailable
platform checks. No installed environment, container or deployment is repaired
merely by changing source; owners must refresh those separately.

Sources: [upstream changelog](https://py-filelock.readthedocs.io/en/latest/changelog.html),
[patched release](https://github.com/tox-dev/filelock/releases/tag/4.2.1),
[Windows soft-lock advisory](https://github.com/advisories/GHSA-567q-5qvw-pf92),
[4.2.4 package metadata](https://pypi.org/pypi/filelock/4.2.4/json).
