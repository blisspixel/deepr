# Typed source-world preflight

Status: read-only preparation increment for v2.51. This note does not claim
that the pilot is reviewed, runnable, or evidence of expert value.

The September 5 rehearsal contains three source-world manifests with 35 nested
source references. Their bytes match the saved hashes, but the existing review
verifier only understands top-level workbook bindings. Per-source availability
is undeclared, and organizer labels such as `role_draft` appear beside source
references. Passing the current artifact verifier cannot establish that an arm
received the right evidence at the right cutoff.

The new preflight validates this missing mechanical contract before any
answer collection and remains read-only. A separate, later materializer
can copy validated bytes into isolated arm roots, after its write and recovery
contract has dedicated tests. Separating these two stages keeps structural
readiness distinct from permission to execute an experiment.

## Executable preparation contract

Run `deepr eval expert-value-sources --from-file ./pilot/index.json
--artifact-root ./pilot --json` with a versioned preparation index inside its
artifact root. Omit `--json` for a short human-readable report. An explicit
`--output` path must be outside the evidence root; no default report is written.

The index uses `deepr-expert-value-source-index-v1`; each world uses
`deepr-expert-value-source-world-v1`. The command returns
`deepr-expert-value-source-preflight-v1`. All three experimental schemas are
published in the schema registry with their linked local-file validator.
Schema shape alone does not verify files, chain consistency, or timestamps.
The existing `eval expert-value` workbook verifier retains its compatibility
and does not silently start parsing nested manifests with this new schema.

Ceilings are 1 MiB per index or world manifest, 16 MiB per source, 64 MiB of
unique source-reference bytes, 4,096 source references, 512 sources per world,
and 64 worlds. Indexes contain at least two worlds. References use canonical
relative forward-slash paths and preserve internal spaces. Trailing periods
or spaces are refused because Win32 can resolve them as aliases of a different
reference. Ordinary changes
during a read are refused; this is not a filesystem sandbox against a hostile
concurrent writer. Process confinement belongs to the later runner.

A versioned source-world manifest names a world id, predecessor, information
cutoff, explicit clock basis, and a bounded list of source-version records.
The source version is an opaque identity; a correction receives a new identity.
Each record binds a plain relative artifact reference, lowercase SHA-256,
declared byte size, declared availability in the experiment's time domain,
and actual snapshot collection time. References preserve significant spaces.

Clock basis is explicit: a synthetic world uses constructed availability dates;
a historical world carries operator assertions about past availability.
Snapshot collection time stays separate. Fetching a document today cannot by
itself prove what its bytes were at a past cutoff. The preflight checks ordering
of declared timestamps and never promotes them into independently established
publication history.

The local preflight:

1. Parse bounded JSON with duplicate-key rejection and a strict versioned
   schema. Reject unknown fields instead of quietly carrying organizer labels
   into an executor-facing contract.
2. Compare world identity, predecessor, and timezone-aware cutoff with the
   frozen workbook or explicit preparation index. Do not require completed
   answer reviews merely to inspect preparation artifacts.
3. Require unique source-version ids and unambiguous file bindings. A repeated
   version keeps the same bytes and availability across successor worlds.
   Distinct versions can coexist where the experimental source policy allows.
4. Verify each nested digest and declared byte size under the selected root,
   with explicit file, manifest, and aggregate byte ceilings. Reject traversal,
   URLs, alternate data streams, special files, and links or junctions on the
   selected reference path. Bounds apply before reads, and changes during a
   read refuse the complete result.
5. Compare declared source availability with the world's information cutoff.
   Parse timezone offsets as instants, not lexical string order. Do not infer
   availability, support, contradiction, or importance from names or prose.
6. Return a preparation report bound to the actual manifest bytes. A report is
   a description of that inspection, never a reusable authorization token.
   Report construction re-reads inputs; materialization must repeat validation.

The report says what was checked, how many manifests and unique source
files matched, and which remaining gates were not evaluated. It keeps
`run_ready`, semantic quality, blinding, model equivalence, and process isolation
unproven. Default invocation writes nothing and makes no provider call.

## Later materialization boundary

Source inventories for the four arms must be byte-identical within each world.
Use neutral content-addressed destination names and strip organizer-only
metadata. Do not rewrite authoritative source bytes to remove a perceived clue;
that is an experiment-design review decision. A neutral filename alone does
not prove that source content is blind.

Each arm needs its own process and writable state root. Shared immutable source
bytes are acceptable only with an explicit confinement mechanism; copying to
separate roots is the simpler initial implementation. Reject an existing output
root, a source/output overlap, or any collision. Stage the complete inventory,
verify copied digests, then publish a complete marker. A partial directory is
incomplete evidence and cannot resume by treating missing files as success.
Cancellation and restart tests must show no cross-arm or organizer exposure.

An execution record must bind the effective model and generation settings,
context ceiling, source inventory, tool catalog, cache policy, and memory hashes
before and after the run. It must distinguish wall-clock latency from cold-start
and construction/maintenance overhead. None of these fields may silently use
ambient configuration when claiming a controlled comparison.

Only finalized answer bytes receive opaque randomized review ids. Keep the
private arm mapping separate from reviewer packets, and bind review labels back
to exact answer and source hashes. An actual accountable reviewer owns semantic
labels and protocol attestations. The tool cannot assert human authorship,
review completion, or a held-out benefit on a person's behalf.

## Why this sequence

The active roadmap requires evidence of persistent expert value before more
memory machinery, external runtime control, or hosted execution. The
LongMemEval-V2 case categories and Memora's valid versus invalid memory reuse
motivate distinct semantic measurements. They do not justify a lexical quality
gate or demonstrate a Deepr benefit. rliable's task/run structure also means a
case-only bootstrap is not an estimate of between-run variation.

Alternatives rejected for this increment:

- Treating a top-level manifest hash as proof of nested source integrity.
- Inferring publication time from a filename, document wording, or current
  collection time.
- Automatically converting the existing unreviewed drafts into attested
  experiment inputs.
- Giving a runner organizer manifests or answer keys because all files share
  a convenient repository root.
- Shipping a new hosted runtime or memory database before the controlled local
  experiment explains which deficiency it would resolve.

## Verification and promotion

Regression tests should cover changed nested bytes with an unchanged outer
manifest, future availability, timezone-equivalent dates, duplicate JSON keys,
identity conflicts across worlds, repeated spaces in paths, traversal and link
escapes, special files, exhausted byte ceilings, and mutation during reads.
Failure must write nothing and dispatch nothing. Happy-path fixtures must be
explicitly synthetic and cannot claim semantic correctness.

Re-run the preflight on a new preparation bundle without modifying the archived
September 5 rehearsal. Preserve the original failures and the explicit mapping
used to prepare new timing fields. The remaining human review, isolated arm
execution, blinded labels, and value analysis stay open in the roadmap.

## September 5 preparation validation

A new unreviewed bundle passed the actual CLI preflight with three worlds,
35 nested references, 15 unique source files, and 12,167 verified source
bytes. The archived rehearsal remained byte-unchanged. Changing a source byte
in a separate copy while retaining its original outer manifest hashes caused
the CLI to refuse the input with a failure exit status.

The new files use neutral content-addressed names. Their availability dates
are explicitly constructed from first inventory membership; snapshot collection
time records the copy. No historical publication claim, semantic label, or
human attestation was fabricated. This preparation root still contains separate
organizer metadata and is not an arm sandbox. The reports are under the
configured reports root in `validation/source-world-preflight-2026-09-05` and
the adjacent `.result.json` and `.audit.json` files. Provider calls and paid
API spend were zero.

Primary references checked September 5, 2026:

- [LongMemEval-V2](https://arxiv.org/abs/2605.12493)
- [Memora](https://arxiv.org/abs/2604.20006)
- [rliable](https://github.com/google-research/rliable)
