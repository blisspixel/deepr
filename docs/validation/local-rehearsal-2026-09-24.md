# Local four-arm rehearsal validation, 2026-09-24

Unreviewed operational evidence for the S0 harness. No answer has been
scored, no reviewer has seen a packet, and nothing here is a value claim.
Paid API spend: `$0`. All model calls used the owned local Ollama server.

## Environment

- Ollama 0.34.3, cloud disabled (`source: both`), RTX 4090 (24 GB).
- Model `qwen3.6:27b`, digest
  `a50eda8ed977ab48a12431878896b27ffd5cef552c17af3317d9623b939a7f1e`,
  `think: false`, temperature 0, seed 20260924, `num_ctx` 32768.
- Source worlds: the September 5 synthetic preflight bundle (3 worlds,
  12 sources in world 2; cumulative inventories). Cases: 12 question-only
  cases extracted from the unreviewed r2 draft blueprint.
- Inputs and outputs live under the configured reports root in
  `validation/expert-value-rehearsal-2026-09-24*`; they are not committed.

## One-phase smoke

A single construct worker on world 1 completed in 402 s including model load:
3 calls, 9 findings, 4 cited positions, digest bound on every call, `$0`
ledger records written. The worker spec contained no question.

## First full attempt: interrupted

Run root `expert-value-rehearsal-2026-09-24`, code `1dff3562` from a clean
frozen worktree. The compiled world-1 checkpoint completed (3 calls; 121 s,
42 s and 101 s; 9 findings, 4 positions). The next worker, fresh construction
for the first case, stalled: Ollama reported generation falling to about
0.25 tokens per second while an unrelated GPU transcription process held the
device at 100% utilization. After 15 minutes with no completed call the run
was stopped. The attempt is preserved with an explicit interruption event;
it was not resumed or overwritten, and it has no summary because the
orchestrator was terminated.

Consequence: `run` now performs one recorded `$0` warm-up generation and
refuses to start below a tokens-per-second floor (default 5), so contention
yields a refusal rather than a run of timeout cells.

## Full run

Pending. It needs the GPU to itself and uses a new run root.
