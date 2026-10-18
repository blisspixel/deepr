# Optional Brim presentation

Decision for #235, 2026-10-18. Written before implementation and revised with
observed rendering findings. Adopt the recommended owl with explicit opt-outs.
Its own silhouette represents a watchful companion; turning the existing mark
into a character would obscure its actual geometry. A plain interface remains
available through the opt-outs.

This is presentation only. No question classification, routing, spending,
knowledge write, research expansion or answer revision belongs to the companion.
Idle, working, success, skeptical and error each retain their state word. A
technical completion or recorded anchoring count does not qualify advice.

One renderer owns a 16x8 pixel canvas, four terminal rows of full/half blocks,
and four-row ASCII equivalents. Body uses the owning default foreground, eyes
accent and the skeptical brow warning. Each vertical pixel pair is single-colored
or transparent, so no terminal foreground needs a guessed RGB background.
Distinct half-block eye shapes preserve readability under NO_COLOR. Snapshots
cover every still pose and the working scan/blink cycle.

Eligibility requires stdout TTY, at least 80 columns, and no CI/dumb/screen-reader
veto. NO_COLOR permits a monochrome static figure. DEEPR_ANIMATIONS=off keeps
all poses static. DEEPR_COMPANION=off, root --no-companion and config's
cli.companion on/off alias use the existing persisted-env seam. A lazy root
callback scopes a ContextVar token through nested interactive invocations and
resets it on Click close, without mutating caller environment. JSON integrations
explicitly disable rendering even if their stdout is a TTY.

Reuse LiveShimmerStatus's existing active-work Event-wait timer. An optional
renderer/fps cap preserves default callers while refreshing the companion at
most four times per second. Custom progress updates buffer the latest message;
canonical checkpoints retain their own callbacks. Start, refresh and stop use
the shared synchronized-output seam. Reduced-motion work prints once without
a thread; idle never starts a timer. Exceptions/cancellation clean up before a
static error pose, preserving the original exception. Consult refusals own their
error pose to avoid duplication.

Study/build display working during the owning operation. Study success requires
an existing clean result with nonempty findings all anchored by its structural
match counts; missing counts cannot earn a success pose. A completed formation
alone does not prove that condition. Consult final state uses recorded completion
and the same assembled Pushback rows already shown in the answer. Agreements
and fallback text do not create skeptical state. Partial and empty consultations
cannot appear successful. The existing payload, cost footer and exit codes keep
their owners; the renderer receives literal Text and owning Style objects.

The idle capture exposed a pre-existing menu form bug: padding cropped numeric
keys, and Rich parsed [q] as markup. Literal Text and a padding-aware key column
repair the same prompt where the companion appears. No input parser changes.

Three pre-fix checks reproduce the shared shimmer policy ignoring explicit
screen-reader settings. Detection now belongs to effects.py; banner and
companion reuse it, with their distinct static/hidden display contracts.

Verify opt-outs, fresh private config binding, all poses and pixel projection,
active refresh buffering/cleanup, JSON parity and unchanged transaction arguments.
Retain actual PTY timing and light/dark/monochrome captures. A paired Linux idle
CPU sample is bounded evidence, separate from Windows thread lifecycle checks.
Synthetic screenshots make no claim of a formed or calibrated expert. Existing
ANSI-to-SVG tooling does not emulate animation cursor motion, so render static
captures only; retain animated bytes/timing separately. Source/callers were
traced directly because no current codegraph was available.
