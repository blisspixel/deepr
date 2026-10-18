# Startup and width validation, 2026-10-18

Issue #234. [Design](../design/terminal-banner-width.md). This is presentation
acceptance, separate from S0, semantic quality, capacity admission and spend.

Four retained pre-fix regressions reproduce seen-banner replay, reduced-motion
suppression, an unbounded requested frame rate and root help wider than 60.
The earlier real PTY captures also reproduce capacity rows/footer and doctor's
closing prose overflow. The first revised capture exposed a remaining 83-column
admission footer; source collection and JSON stay in capacity.py while all
inventory rendering now uses its existing capacity_inventory.py seam.

The final real PTY captures for help, capacity and offline doctor at 60/100
columns have zero over-width lines. Six deterministic command snapshots guard
both widths; full next commands remain the documented exception when a whole
command itself exceeds the window. Consult help preserves four example lines.
[Actual captures](../../assets/qa/terminal-width/receipt.json) include host-local
read-only inventory, not a generation or paid-capacity test.

The first actual banner capture has eight synchronized palette frames; later
seen, reduced-motion, NO_COLOR and screen-reader cases have no animated frame.
The first process takes 0.83s versus 0.15s for seen, including imports. Unit checks
verify one sleep per frame at no more than12 fps, final sync/cursor restoration,
propagated interrupts, accessible compact output, no nonterminal escapes and
setup attendance refusal before the banner or config write. A source-bound dot
projection reuses the actual dashboard SVG paths rather than an unrelated logo.

[Light](../../assets/qa/terminal-banner/banner-light.png) and
[dark](../../assets/qa/terminal-banner/banner-dark.png) were visually inspected.
They render the static seen-state PTY bytes through explicit 16-slot palettes;
the raw animated capture, timestamps, SVG hash and recipe are retained in the
[receipt](../../assets/qa/terminal-banner/receipt.json). A physical terminal's
live theme switch is not claimed. Font/viewport rendering uses locked local
Playwright with Node 24.22.0 and no external browser requests.

The final CLI/capacity run passes 1,713 tests; an earlier CLI run passed 1,663
before the final inventory footer move;
the focused banner/width/capacity/doctor run passes 120. The first full suite
retained two failures where old message assertions assumed an unwrapped phrase;
they now normalize whitespace while preserving the same capacity/overage
messages and all state/exit checks. Review also rejected POSIX-only preview
continuations; narrow help keeps a portable example and the owning model
baseline, with lifecycle checks at three widths. Strict islands pass
all 293 files. The wider type baseline remains exactly 196 errors in 60 files, with no
changed diagnostics. The final frozen revision passes 13,400 offline unit tests, with 22 existing
platform/optional skips and 85.50% combined statement/branch coverage. The
independent coverage gate also passes. Exact-head and resulting-main CI remain
required before publication. Failed prototypes and fixture setup
runs remain in the private evidence directory. No provider flag, credential,
route, cost computation or execution authority changed. No current codegraph
was available; the owning symbols, callers and tests were traced from source.
