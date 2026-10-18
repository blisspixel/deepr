# Terminal roles and shared guidance

Decision for issue #230, 2026-10-18. Written before implementation. Source and callers were traced directly; no codegraph was present.

Keep one palette contract in cli/colors.py. Expose text, accent, success, live,
warning, destructive, error, info, muted, money and quote. Only this owner maps
roles to terminal colors and attributes. Default foreground is body text;
muted dims it instead of choosing ANSI white. A shared console factory selects
standard terminal colors, disables implicit Rich highlighting, and retains
normal TTY/NO_COLOR policy. Replace command-specific console constructors.

Existing helper names and public Python imports remain compatible. Keep old
symbol table names as aliases to one authoritative text-label map if callers
need them. Shared status labels are lowercase ok, warning, failed, skipped and
unverified; one width derives from those labels. Diagnostic rendering projects
existing passed/severity/verification fields; do not change diagnostic JSON,
exit codes, provider eligibility or the underlying result. Capacity presence is
unverified execution even when installed/configured. Quarantined remains a
warning; actual failed probes are failed. No inferred advice-quality state.

Migrate render styles to roles. Commands and names request accent. Stance
changes request live, with their existing active words. Money requests money.
Fleet grades use default foreground except F, which fails; letter grades
and triage limits remain visible. Quoted source passages get a dim italic gutter
without modifying source bytes in machine records. Remove ornamental diamonds
and bullets; preserve functional quote gutters and truncation.

Guidance uses Next: and optional Also: with complete executable commands.
Replace conflicting output prefixes only, not prose discussing test or check
concepts. Do not turn a lexical scan into a writing-quality or evidence verdict.
The new source guard inspects presentation syntax: markup tags, explicit style
arguments and guidance literals. It protects form only. Effects must use role
attributes rather than truecolor so they cannot bypass the contract; banner
motion and width behavior remain the separately sequenced #234 change.

Tests reproduce bad ANSI white/magenta/highlight/status/hint behavior first.
Retain actual PTY doctor and profile output, render its exact bytes using named
light/dark 16-slot palettes, and inspect both. Profile screenshots reload a
canonical synthetic fixture written with owning stores; label it synthetic and
run no portrait or model. These establish appearance, not expertise or a live
physical-terminal theme switch. NO_COLOR retains every state word. Full offline
unit coverage, strict islands, source/gate checks and exact-head CI precede merge.

Implementation notes from installed-library inspection: Rich does not resolve
`bold accent` as a combined style unless a complete theme alias exists. Normalize
physical-color tags to single roles, including the four dynamic bold-color
expressions; do not create invalid mixed role/attribute strings. Plain bold/
italic attributes may remain for hierarchy. Click calls can be rewritten with
AST source offsets (not whole-file unparse), retaining original argument text.
Money columns and statements need manual role review after mechanical migration.
Use Style objects for role-aware helpers accepting arbitrary caller Consoles
(such as consult rendering), avoiding reliance on a caller-installed theme.
Only F is colored in fleet triage; D and all higher letters use body foreground.
New role tests and source guards protect presentation form, not meaning.

Manual pass after mechanical role migration: active jobs/progress use live;
queued states stay muted; money columns/amount lines use money; destructive
confirmations use destructive, with the requested verb. Do not infer new runtime
states from message text. Thought-stream decisions/confidence are recorded model
signals, so do not color them as passed/anchored work or use a numeric confidence
cutoff as a success color. Keep structured payloads unchanged. Generic success/
warning/error helpers should retain explicit state words when color is removed.
Guard arbitrary user brackets with existing escaping/Text seams; disabling Rich's
implicit highlighter should not introduce new markup interpretation.
