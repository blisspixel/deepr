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
