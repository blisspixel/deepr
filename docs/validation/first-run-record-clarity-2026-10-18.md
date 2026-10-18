# First-run record clarity, 2026-10-18

Scope: #224, under the [record clarity design](../design/first-run-record-clarity.md).
The model-size and local cloud-disable advice was addressed separately by
v2.50.33. These checks inspect setup and derived records; they make no inference
or provider call and do not qualify expert advice.

Eight regression cases fail against the v2.50.33 source. The corrected candidate
passes 50 focused checks, including refusal before noninteractive setup writes,
interactive key entry, absolute path display without configuration mutation,
valid no-discovery review links, exact note deduplication, older brief provenance
and immutable regeneration. Failed checkpoint notes remain in canonical history.

Strict typing passes for 291 files. The wider tree retains the same 196 baseline
errors in 60 files, with identical normalized diagnostics. Package checks pass
57 cases. The wheel and source archive contain the packaged dashboard; fresh
Python 3.13 wheel installation passes MCP 2025-06-18 and 2026-07-28 checks and
the host profile. Four installed CLI checks cover setup refusal and absolute
doctor, unified configuration and legacy configuration displays. Generated
currentness fixtures show both matched and older-brief history.

An initial no-discovery fixture used a corpus root different from the one the
formation service owns; it was corrected to use the canonical corpus store.
The installed display probe initially compared wrapped Rich output as an
unbroken string; whitespace normalization corrected the probe without changing
the product. Both failed trials are retained. No gate was relaxed.

The full unit suite passed 13,147 tests with 20 existing skips and 85.49%
combined statement/branch coverage. Independent coverage enforcement passed.
Exact-head CI is required before merge. Exact-main artifact and public-installer acceptance are
separate publication checks. Logs and fixtures are retained under the existing
ignored `.agent/reader-evidence/` directory. No codegraph was available; source,
callers and tests supplied the implementation map.
