# Dependency audit repair, 2026-10-20

Issue #277. See the [dependency decision](../design/maintained-runtime-support.md#advisory-driven-lock-repair-2026-10-20-277)
and [bounded receipt](artifacts/dependency-audit-repair-2026-10-20/receipt.json).
This is an Unreleased compatible dependency repair based on `034877e7`.

The first exact-head run of PR #276 failed its Python 3.11 dependency audit,
native security audit and frontend dependency audit. Certifi 2026.7.22,
follow-redirects 1.16.0 and Vite 8.1.5 were affected. Original job logs and
the complete check snapshot remain under the ignored task evidence. Remaining
jobs in the obsolete workflow were cancelled, not accepted as passing.

Only those three resolved package versions change: Certifi 2026.10.19,
follow-redirects 1.16.1 and Vite 8.1.6. Certifi's repaired minimum is also a core
package requirement, so an installed wheel upgrade cannot retain an affected
transitive version. Vite's declared minimum moves to 8.1.6. There are no new
libraries, advisory suppressions, weakened audit thresholds or TLS bypasses.
The CA-store change intentionally removes the compromised trust described in
the upstream advisory. Licenses, compatible engines and universal Python wheel
metadata were checked against primary registries before changing the locks.

The machine's defaults differed from CI. Lock updates and frontend checks used
isolated uv 0.13.0, Node 24.22.0 and npm 12.0.1. An initial floor resync selected
3.15 and failed on NumPy's newer stub syntax; an explicit Python 3.11 resync
restored the actual floor dependency branch. No ignore was added. The first
browser attempt lacked the matching Playwright executable; installing that
browser corrected the setup without changing operating-system packages.

Both frozen dev/full environments pass their dependency audits and all 296
strict island files. The complete offline suites and independent coverage
gates pass:

| Runtime | Passed | Existing skips | Combined statement/branch coverage |
| --- | ---: | ---: | ---: |
| Python 3.15.0 | 13,596 | 22 | 85.68% |
| Python 3.11.17 | 13,596 | 22 | 85.76% |

Unit runs keep dotenv disabled and the socket guard enabled, with separate
task-local temporary and coverage roots. Ruff, formatting, file-size and
complexity ratchets, paid API boundaries and documentation consistency pass.
No source gate or baseline was relaxed.

An overly broad pre-commit invocation also reached existing test lint findings
and rewrote unrelated snapshots. Its log and mutation diff were retained;
all 37 unrelated hook edits were restored exactly to index bytes. The normal
staged-file hooks then passed unchanged. No whole-repository hook acceptance
is claimed, and no fixture or lint baseline was changed to hide that result.

The frozen frontend install, npm audit, lint, 89 unit tests, production build
and all 102 existing browser layout/state checks pass. The regenerated archive
is byte-identical to its committed version. Wheel/sdist frontend checks pass,
and built wheel metadata contains `Requires-Dist: certifi>=2026.10.19`.
A clean core wheel installation in a path with spaces passes the existing
Agent Plugin stdio and OpenClaw host-profile smoke checks on final Python
3.15.0, without provider dispatch.

Actual production dashboard checks capture 12 screens in each theme against
isolated canonical zero-cost demo state. All 24 captures pass the existing
observations, with zero outgoing connection attempts, zero ledger events and
the owned backend stopped. Visual inspection covers the light overview and
expert profile, dark research studio and costs. That inspection found a
contradictory key-and-submit banner, now tracked separately as #278 and in the
roadmap. Passing layout checks do not accept that guidance.

Hosted Windows/macOS installs, all five Python minors, containers and exact-head
and exact-main CI remain separate acceptance checks recorded on the issue and
PR. Local Linux success alone does not prove those platforms. The unchanged
audit jobs provide the regression for these advisory versions; no brittle
version-only test substitutes for them.

No new model or paid API calls were made. Frozen diagnostic answers, withheld
assignment keys and unreviewed labels remain unchanged; this repair does not
qualify advice or promote S0.
