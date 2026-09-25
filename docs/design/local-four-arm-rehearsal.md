# Local four-arm operational rehearsal

Status: unreviewed experiment protocol, 2026-09-05. This uses the existing
source preflight, corpus, study, briefing, position history, and native local
completion primitives. It is not a replacement for the attested value workbook
or a claim that the v2.51 value gate is complete.

## Decision and scope

Exercise all four treatments over the prepared three synthetic source worlds
and twelve draft cases before commissioning semantic review. Keep the original
drafts unchanged. Freeze a separate policy and question-only case inventory
before any answer collection. Construction and maintenance receive sources,
never the held-out questions, acceptance criteria, organizer roles, or answers.
Consultation receives the current sources as well as any permitted memory.

| Arm | Preparation | Memory across worlds |
| --- | --- | --- |
| Fresh research | A new local study and brief for each case | None; each case starts empty |
| Static history | Retain raw cumulative sources | Raw corpus only |
| Compiled expert | One study and brief from world 1 | Frozen initial checkpoint |
| Maintained expert | Copy the identical compiled checkpoint, then study and brief before worlds 2 and 3 | Its own last completed checkpoint and position history |

Use the same `synopsis` and `change` lenses for every preparation. Final answers
use a common prompt and the complete current-world source packet, in the same
order and with neutral content-hash labels. The normal consultation assembler
retrieves passages through study findings, so using it unchanged for a raw
corpus would mechanically deny static history the promised source access.

This is fresh local evidence reading, not live web or frontier research. Full
source packets avoid introducing a retrieval confound in this small fixture;
they cannot demonstrate retrieval scalability. Preprocessing compute differs
by treatment and must be reported separately, including fresh per-case work
and initial compilation attributable to both persistent arms.

## Binding and isolation

Use the existing native Ollama backend with per-dispatch owned-local and cloud
disable checks. Also compare the observed model digest with the frozen model
identity. Retain the application commit and runtime source hashes, server and
model metadata, exact requests and raw responses, context/output settings,
generation counts and durations, stop reasons, and errors. The native endpoint
exposes runtime generation options and timing fields; the compatibility endpoint
does not expose per-request context size. See the official
[native chat contract](https://docs.ollama.com/api/chat) and
[compatibility context guidance](https://docs.ollama.com/api/openai-compatibility).

Memory shares the context ceiling with instructions, questions, and sources.
Freeze any mechanical memory-prefix limit before execution and retain the full
memory plus the exact rendered prefix. Missing usage remains missing evidence.
Do not claim exact tokenizer verification, fixed seed, equal compute, or equal
warm-cache latency when these were not established. No native tools or fallback
are available to the model. Every dispatched attempt writes an append-only
local cost record, including unsuccessful attempts, at $0 API cost.

Separate child processes use explicit credential-free environments, disabled
dotenv loading, isolated data roots, and only their permitted input copies.
Copy each frozen memory snapshot again for consultation, hash it before and
after, and keep outputs elsewhere. Construction and maintenance run in workers
that receive no case questions. Future sources and organizer files never enter
worker inputs. Ordinary file copies and restricted prompts do not constitute
hostile-process OS confinement. Preserve original source bytes and all canonical
expert files. Keep coexisting historical versions active in the retained corpus.

## Completion and failures

A study must clear its existing usable/complete status; a brief must contain
orientation and positions before its checkpoint is accepted. Keep failed and
partial artifacts. Failed initial or fresh construction refuses the dependent
answer. Failed maintenance retains the last completed checkpoint, explicitly
reports the update failure, and does not claim completed-update latency. No
retry overwrites an attempt. Terminal cell records distinguish blocked,
failed, and answered outcomes.

Historical briefing requires an explicit information date. `build_brief` now
accepts optional `as_of_date` and passes the same effective date into the prompt
and falsifier registration. Its default remains current UTC. This avoids
discarding a prediction that is future-facing at a synthetic historical cutoff
merely because the rehearsal executes later. Execution timestamps remain real.

Operational completion requires 48 terminal cells, all distinct treatments,
chronological worlds, matching permitted source inventories, unchanged
consultation memory and canonical experts, and reconciled request/cost records.
Saved answers remain unreviewed. There are no reviewer identities, semantic
attestations, correctness scores, or claims of successful blinding. The next
value step remains review of the protocol and exact outputs, followed by the
attested longitudinal evaluation; this rehearsal cannot promote itself.

## Implementation (2026-09-24)

`deepr eval expert-value-rehearsal` implements this protocol. Its seams are
`evals/expert_value_materialize.py` (writing counterpart of the read-only copy
verifier), `evals/expert_value_rehearsal.py` (policy, arm order, terminal
cells, integrity checks), `evals/expert_value_rehearsal_worker.py` (one phase
per process), `evals/expert_value_blinding.py` (reviewer packet, private key,
label binding), and `evals/expert_value_rehearsal_workbook.py` (assembly of the
strict `deepr eval expert-value` workbook).

| Protocol requirement | Enforcement |
| --- | --- |
| Frozen model identity | `run` compares the installed digest before any work; each call compares the digest observed by the per-dispatch owned-local attestation |
| Usable capacity | A recorded `$0` warm-up must meet a tokens-per-second floor, so a contended GPU is a refusal rather than a run of timeouts |
| Explicit generation settings | Policy pins `num_ctx`, output limit, temperature, seed and `think`; the native backend refuses unknown options |
| Question-free construction and maintenance | The orchestrator refuses to put a question in their specs, and the worker refuses one if present |
| Answer bound to its question | Each answer reports its question digest; a mismatch fails the cell, and `blind` refuses criteria for a different question |
| Equal source interface | Every worker receives its own new copy of the selected world; each answer reports the source digests it actually rendered, compared per world |
| Frozen consultation memory | Answers read a private checkpoint copy; the copy and every accepted checkpoint, including fresh ones, are hashed before and after |
| Canonical experts untouched | A path, size and mtime fingerprint of the operator's experts root is compared before and after the run |
| Credential-free workers | Allowlisted environment, `PYTHON_DOTENV_DISABLED=1`, redirected home and data roots; the worker refuses credential-like names |
| Code identity | Run record holds the commit, clean-tree flag and module hashes; every worker reports the module hashes it imported |
| Failures and denominators | Failed fresh or compiled construction blocks dependent answers; failed maintenance keeps the last checkpoint and says so; timeouts, crashes, empty answers, unreadable results and orchestrator errors all end as terminal cells |
| Evidence retention | Each worker's orchestrator record (exit, timing, usage, memory digests, ledger counts) is written beside its outputs |
| `$0` accounting | Workers record every attempt before dispatch; the orchestrator mirrors every attempt, including one killed mid-call or interrupted, into the canonical ledger idempotently |
| Completion | `operationally_complete` requires every planned cell and no failed integrity check; a check with no applicable evidence reports `null`, never a vacuous pass |
| One writer | An OS-level lock on the run root refuses a second orchestrator; the OS releases it if the holder dies |
| Interruption | `run --resume` continues an interrupted run only with byte-identical policy, plan and hashed modules. It re-verifies recorded cells, answer bytes and accepted checkpoint digests, keeps finished phases, moves unfinished worker directories aside as abandoned evidence (mirroring their attempts), reuses recorded arm orders and the experts baseline, and gives every launch a unique attempt id so reruns never reuse a request id |
| Blinding | Instructions are identical for every arm; memory is rendered without harness identifiers; the packet masks harness markers an answer echoes (recording both digests), omits answer digests, refuses arm identifiers, and lists missing cells in the key; the key must live outside the packet directory |

Workbook assembly fills execution facts from recorded evidence: answer and
cell digests, worker completion times and latency, `$0` costs, and update
completion. Fresh research and static history incorporate a world's update by
construction; the compiled checkpoint does not; the maintained expert does
only when its maintenance for that world completed. Labels come only from a
frozen binding, and reviewer minutes from the labels. The protocol attestation
is filled only when the operator passes `--protocol-attested-by`. Workbook v1
cannot represent failed or blocked trials, so assembly refuses a run with
unanswered cells and names them; the rehearsal summary keeps those failures.

Remaining limits: workers keep loopback network access for the model server,
so this is process and data-root separation, not an OS sandbox. Fixed seeds do
not guarantee byte-identical local output across loads, versions or
platforms. Masking removes harness markers, not an arm a reviewer could infer
from an answer's substance; reviewers record suspected production before the
key is revealed. The run root identifies arms by file name and must be
withheld from reviewers along with the key. Label binding checks form, never
label meaning or reviewer identity. Consultation memory is the rendered brief;
earlier positions shaped that brief and remain in the checkpoint's position
history for inspection.
