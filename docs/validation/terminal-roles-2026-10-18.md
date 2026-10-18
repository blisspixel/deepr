# Terminal role validation, 2026-10-18

Issue #230. See [design](../design/terminal-roles.md). This is presentation
acceptance, separate from expert quality, currentness, S0 and spend authority.

The retained baseline reproduced ANSI white/bright-white provenance and stance
text becoming faint on the light palette, inconsistent status/hint forms and
implicit magenta path highlighting. Ten initial role tests failed before the
migration. A separate test with `NO_COLOR` removed reproduced ANSI escaping into
piped output when the first factory forced a color system; capability detection
now precedes the standard-palette cap. Both ordinary and explicitly nonterminal
streams retain plain output.

One palette owner supplies all explicit styles and shared Rich progress defaults.
Doctor projects existing passed, optional, warning, failed and unverified fields;
its machine report remains unchanged by rendering. Costs doctor preserves full
names and error details in aligned rows. Complete command hints use a shared
formatter, including when a caller supplies its own console. Source guards check
style and prefix syntax only; they make no semantic verdict. Human word wrapping
is normalized in refusal assertions without removing their side-effect checks.

The focused CLI/profile/thought-stream/batch run passed 1,754 tests before the
last shared-progress aliases and detail/hint checks; all 15 final role checks
pass. Existing assertion failures, including table-layout and wrapping failures,
remain retained in `.agent/reader-evidence/`. The final frozen revision passes
13,370 offline unit tests, with 22 existing platform/optional skips and 85.47%
combined statement/branch coverage. The independent coverage gate also passes.
All 293 strict island files pass; the wider baseline remains exactly 196 errors
in 60 files, with no added or removed diagnostics. Source lint/format, size,
complexity/security ratchets, paid boundaries and documentation checks pass.
Exact-head CI and merge acceptance remain required.

[Doctor light](../../assets/qa/terminal-roles/doctor-light.png),
[doctor dark](../../assets/qa/terminal-roles/doctor-dark.png),
[profile light](../../assets/qa/terminal-roles/profile-light.png) and
[profile dark](../../assets/qa/terminal-roles/profile-dark.png) render retained
actual PTY bytes through explicit 16-slot palettes. Raw captures and their
hashes accompany the images. The profile reloads a canonical synthetic fixture;
its empty appearance prevents portrait generation. It establishes no subject
expertise and is not a replacement Python-expert exemplar. These are palette
renders, not a physical terminal's live theme-switch test.

The 60/100-column captures still reproduce root-help and capacity overflow and
one long doctor closing sentence. They are retained for #234, not called width
acceptance. No current codegraph was available; source/callers were inspected.
No provider SDK, model, execution eligibility or budget gate changed.
