# Native local attempt accounting, 2026-10-18

Scope: the retained local-consult missing-ledger finding and the
[native accounting design](../design/native-local-attempt-accounting.md).
This validates execution records, not advice quality or the S0 rehearsal.

The baseline regression failed at the native POST boundary because no ledger
receipt existed. The correction records intent before request validation and
proof, dispatch after current cloud/model attestation, and a terminal status
before returning or propagating failure. Receipt metadata excludes prompts,
answers and raw exception text. Inspection-only preflight writes no ledger.

115 focused checks pass across the native transport, readiness, new accounting,
rehearsal worker/orchestrator and CLI. They include failed proof, unsupported
options, transport and malformed-response errors, cancellation during proof and
transport, persistence failure at each phase, stale digest prevention, repeated
caller correlations, idempotent worker mirroring and retained legacy records.
Rehearsal doubles now exercise the actual native recorder around synthetic
responses, instead of replacing its accounting boundary.

Review caught that lifecycle rows could be mistaken for distinct attempts in
the rehearsal summary. Distinct attempt IDs now drive the call-completeness
check and the count of attempts lacking completion artifacts. A regression
proves three rows from one attempt cannot cover two completed calls. The shared
accounting module is included in the frozen rehearsal code identity. The first
full suite was interrupted for this correction; its partial log is retained.
An earlier focused failure came from the old warm-up double's signature and
was corrected by exercising the actual native backend. No gate was lowered.

A fresh installed candidate made one real local consult on isolated synthetic
expert/source records, using the already installed `qwen3.8:27b`. Ollama reported
cloud disabled by configuration and attested digest
`aaee06c39dcf2437cde036998d960e1fc1494b8191be7cc9657d01e509097813`.
The CLI completed with a consult trace and exactly three native ledger events:
requested, dispatching and returned. They share one attempt ID, record 870 input
and 263 output tokens, and total `$0.00`. No model was downloaded and no paid
provider was called. The later summary-count correction does not change this
native completion path.

The answer contained 201 whitespace-delimited words despite a request for fewer
than 100. That repeated output-adherence finding remains open in the roadmap.
The response, delivered context, source bytes, observation times, model digest,
trace and ledger remain retained; no semantic score or expert-quality claim is
assigned. Earlier failed trials were not overwritten.

Strict types pass for 292 island files and separately for the native backend;
the wider baseline remains 196 normalized errors in 60 files. Lint, formatting,
size/complexity/security ratchets, paid-API boundaries and documentation checks
pass. Package and host checks pass 68 cases. Fresh wheel checks cover both MCP
protocols and the host profile; the final installed wheel reads the retained
live receipts as three events and one attempt. Full-suite results accompany the
matching PR and release. Exact-head CI precedes merge; exact-main CI, artifact
verification and public installer acceptance precede release completion. No codegraph
was available; the shared transport, callers, ledger and tests were traced from
source. Scratch, installed fixtures and failed runs are retained under the
existing ignored `.agent/reader-evidence/` directory.
