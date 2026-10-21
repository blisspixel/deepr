# Frozen dashboard guidance, 2026-10-20

Issue #278. See the [interface decision](../design/local-first-interface-polish.md#frozen-research-guidance-correction-2026-10-20-278)
and [bounded receipt](artifacts/dashboard-guidance-2026-10-20/receipt.json).

Actual production validation for #277 showed Research Studio correctly
blocking paid dispatch while recommending that a user add an OpenAI key and
restart before submitting. The owning dashboard gate is unconditionally
blocked in this release. No eligible dashboard state was invented to preserve
that instruction: the obsolete banner is removed. Existing readiness and
submit guards, drafts, estimates, money-state disclosure and local CLI guidance
remain in place.

The new rendered regression failed on the old source at `c8eacc80`: after a
draft was saved and the estimate/approval control was ready, the forbidden
instruction appeared once instead of zero times. An initial test locator
timed out because it requested an exact draft-status string whose element also
contains the context-file notice. That attempt is retained; correcting the
locator produced the actual old-source assertion failure before the source
repair. The test also reads the saved draft rather than inferring persistence
from the status label.

Pinned Node 24.22.0 and npm 12.0.1 pass frozen installation, vulnerability
audit, lint, all 89 frontend unit tests, production build and 126 browser
layout/state checks. The browser fixture separates key presence from funding.
It covers frozen accounting with a missing or present key, funded accounting
without a key, unknown money without a key and the existing funded/key-present
control. All three widths in both themes keep drafts and estimates usable,
submission disabled and job POSTs absent. These are isolated synthetic HTTP
fixtures, not funded production dispatch trials.

The rebuilt canonical archive is checked against the built wheel: all 125
frontend members match byte for byte, the old instruction is absent and the
preview remains. Existing wheel/sdist frontend checks pass. Actual production
captures cover 12 pages in each theme against isolated canonical zero-cost
demo state, with zero ledger events, zero outgoing connections and the owned
backend stopped. Research Studio was visually inspected in both themes.

The local Python 3.15 offline suite passes 13,596 tests with 22
existing skips and 85.68% combined statement/branch coverage. The independent
coverage gate, Ruff, formatting, file-size and complexity ratchets, paid API
boundaries and documentation consistency pass. This local trial starts from
the dependency-repair source at `c8eacc80`; acceptance after rebasing requires
fresh exact-head and exact-main CI on the final combined tree. An earlier
green run does not validate a later revision.

No provider, credential, spend or canonical knowledge authority changes. No
new model or paid API calls were made. Answer review and S0 remain open.

## Combined v2.50.43 candidate

After rebasing the UI correction onto accepted main `6b36ce1c`, package,
plugin, skill metadata and the host fixture align at 2.50.43. The lock changes
only Deepr's own project version; dependency versions stay frozen. The owning
plugin checksum helper regenerates the manifest and the existing validator
and deterministic archive builder pass. Completed roadmap repairs move to the
release changelog, with S0, semantic review and the maintenance limit still open.

The combined candidate passes 13,611 offline tests with 22 existing
skips, 85.69% combined coverage and the independently enforced gate.
Both actual Python branches pass vulnerability audits and all 296 strict
island files. Source gates and all 21 documentation references pass. An initial
documentation gate rejected a changed threat-model status prefix; restoring
its established version field corrected that format without changing the
checker or the actual 2026-10-19 review date. The failed attempt is retained.

Pinned frontend installation, audit, lint, 89 unit tests and production build
pass again. UI source, the rendered regression and the canonical archive are
byte-identical to the retained 126-check trial above; this binding is recorded
instead of claiming another local browser run. Fresh final CI must repeat all
126 checks on the combined version. Actual v2.50.43 production QA passes all
24 captures with no outgoing connections or ledger events and its backend
stopped. Research Studio and Help were visually inspected. Built wheel/sdist
frontend checks also pass. Exact-head/current-base and resulting-main CI,
clean-wheel installed checks and public-installer acceptance remain separately
recorded in the final PR, issue and release evidence.
