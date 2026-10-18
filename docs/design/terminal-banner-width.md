# Palette startup and terminal width

Decision for #234, 2026-10-18, after the #230 palette contract. Written before implementation.

Use the actual dashboard mark geometry (public/deepr.svg, referenced by
.deepr-mark) beside the wordmark. The component calls it the open well; do not
invent an unrelated logo. Render with the canonical accent role and attributes.
Keep a plain compact wordmark for screen readers, ASCII/legacy encodings and
small windows. Do not change the config-sourced banner marker location.

A first interactive invocation/init gets about 600 ms of reveal, then remains
static. A retained seen marker selects static on later invocations. Full/light
environment overrides remain bounded by reduced-motion constraints. CI, dumb
terminals, screen readers, NO_COLOR and animations=off get static when on a TTY;
non-TTY and --help never get a banner. Env off and explicit off always hide it.
Frames use synchronized output with cursor restoration in finally. At most
12 fps, one sleep per frame, no perf-counter polling or extra end hold by default.

Root help derives width from the real terminal and uses short command lines
with separate wrapping descriptions. Preserve Click's example block markers.
Capacity uses two-line cards below 100 columns; longer details wrap as prose.
At 100 columns retain a compact table with flexible details. Keep execution
eligibility explicitly unverified where inventory only proves presence. Doctor
closing prose uses the shared console, with complete Next:/Also: commands.

Reproduce 60/100-column PTY overflows first. Test policy, seen/static transition,
frame timing/synchronization, exception cursor restoration, no truecolor and
example layout. Retain real PTY before/after text and ANSI captures, and dark/
light screenshots. State any long unbreakable-path exceptions explicitly.

Implementation decisions: the existing six-row wordmark is 40 columns after removing its leading margin; an
8-column braille projection of the actual SVG paths plus a two-column gutter
fits in 50 columns. Retain the source SVG SHA and the deterministic dot-sampling
recipe with the capture receipt. Use compact `deepr VERSION` below 54 columns,
for screen readers or legacy encodings. Derive ANSI from Style.parse of the
owning accent role with dim/normal/bold attributes, never a second palette.

Default reveal duration is 0.6s, capped at 12 fps. Round up the frame count and
sleep once at 1/fps per frame (about 0.67s at the default). Frame rows fill upward
through dim/normal/bold, ending with bold accent. Bracket each complete redraw
in synchronized output; release sync and restore the cursor in finally even on
interrupt. A failed write may fall back to static; interrupts still propagate.

Root help preserves complete short examples with explanations in separate
wrapping paragraphs. A POSIX-continuation prototype was rejected because
Windows is a first-class platform. Wide help retains the owning pinned preview
command; narrow help uses the existing portable default preview plus a wrapping
line naming its shipped provider/model baseline from the same owner. The model
binding regression still runs at 60, 100 and 160 columns. No provider choice,
model default or dispatch capability changes.
Capacity details are literal Text and never create Rich markup from inventory.
Complete Next/Also command lines are the documented width exception when a full
command itself exceeds the window. No generic prose exception is permitted.

Four private pre-fix checks reproduce seen replay, NO_COLOR banner suppression,
a requested 600 fps not capped at 12, and help wider than 60. The retained earlier
PTY captures separately reproduce real capacity/doctor overflow.

Current owning SVG SHA256: `305c2bf97c4c5e64995a940a87cd6f647190ba1f8568385a151a2c7bb4c35b88`.
Dot sampling uses distance <=1.3 SVG units from the three owning path
segments, mapped to 16x24 pixels and the standard braille dot order. The
wordmark remains block characters. Preserve the recipe with validation.

All default inventory rendering, including quota/admission footers and local
probe details, belongs to existing capacity_inventory.py. Keep collection,
JSON and command orchestration in capacity.py, retaining its private rendering
imports for callers/tests. This closes an existing split: wrapping only source
rows left the admission footer at 83 columns. It also avoids growing an almost
1000-line command file; no new rendering module or data authority is introduced.

Normalize the stored help template before interpolating a new paragraph. Raw
indentation on older supported Python runtimes must not change Click layout;
forced-indentation snapshots guard this across all interpreter versions.
