# Selected-world source-copy validation

Date: 2026-09-21. Scope: offline structural evidence, not expert qualification.

The actual `deepr eval expert-value-sources --world WORLD --copy-root PATH`
command verified eight separate input directories on Windows with Python
3.12.13: four copies of each of two explicitly synthetic source worlds.
Source bytes and manifests were identical across the four copies within each
world. The organizer directory contained a separate review-key fixture that
was absent from every accepted copy. Verification changed no input file.

Five additional CLI invocations each exited with status 1: changed source
bytes with the same length, an extra review-key file, a missing completion
manifest, a hard-linked source, and a copy supplied for the wrong world.
Failed copies remained available for inspection. No model or provider call
was made; external validation spend was $0, within the cumulative $10 ceiling.

The [machine-readable receipt](artifacts/source-world-copies-2026-09-21.json)
contains the synthetic source text, original manifests and index, eight actual
verification reports, and five actual failure messages. Its SHA-256 is
`805dca9e393bbc34c167f85c363513a75ed84289935a6e23fb38d30a0b781eca`.
Private input directories and the construction script remain in the configured
reports root and gitignored agent workspace. These are validation fixtures,
not retained research or expert memory.

The focused suite passed 101 tests covering preparation, copied inventory,
CLI and published schemas. Checks include metadata drift, duplicate JSON keys,
source/copy overlap, links and junctions, partial copies, changed input during
inspection, and report-output contamination. Existing artifact readers retain
their compatibility; the single-link requirement is explicit for worker copies.

An initial Windows run exposed that `DirEntry.stat()` supplies zero link counts
and inode identifiers. The verifier now uses current `lstat()` metadata and
checks link counts again on opened files. The official
[Python documentation](https://docs.python.org/3.12/library/os.html#os.DirEntry.stat)
confirms this platform difference. The failed local attempt was corrected before
the CLI receipt was produced.

The archived September 5 rehearsal's preparation directory was not present in
this checkout's configured reports root. It was not reconstructed from prose
or represented as revalidated. Its controlled run, answer-to-review binding,
blinded semantic review and the S0 value gate remain open. Separate regular
files do not provide OS process confinement or prove which context reached a
model; those require execution evidence. Normal consultation remains stored-only.
