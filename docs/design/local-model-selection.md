# Local model selection: hardware-aware defaults instead of "first in the list"

Date: 2026-07-25. Status: design + evidence; implementation staged.

## The defect this replaces

`deepr/backends/local.py::default_local_model()` returns `DEEPR_LOCAL_MODEL` if set,
otherwise whichever model the Ollama daemon lists first. There is no notion of task
fitness or hardware. Measured consequence on one machine: the default resolved to a
code-specialized 32B model for natural-language entailment, and the default grounding
configuration scored at the trivial-baseline level on a third-party benchmark while a
thinking-generation model made the same eval unusable (hours instead of minutes).
Deepr must work on any machine - a 24GB GPU box, an Apple Silicon laptop, a CPU-only
server - so the default has to be chosen, not inherited from list order.

## Hardware tiers and current candidates (sourced, late July 2026)

These are candidate DEFAULTS, not a lock-in; the selection policy below always defers
to `DEEPR_LOCAL_MODEL` and to measured evals over static lists.

| Tier | Example hardware | Candidate defaults (2026-07) | Notes |
| --- | --- | --- | --- |
| 24GB GPU | RTX 4090/3090 | Qwen3.5 27B Instruct; Gemma 4 26B (~85 tok/s reported); 30B-class MoE | 32B is the practical ceiling; 70B needs Q2 or offload (not worth it) |
| 16GB unified | Apple Silicon M-series | Qwen3.5 9B Q4 (~6.6GB); Gemma 3 12B Q4; Phi-4 Mini | 7-9B Q4 is the everyday sweet spot; Metal/MLX acceleration |
| 8-12GB GPU | RTX 4070/3060 class | 7-9B Q4 models | Same class as 16GB unified |
| CPU-only | servers, older laptops | 3-8B Q4 models | Quality-tolerant workloads only; expect slow syncs |

Sources: apxml.com RTX-40 guide, modelfit.io RTX-4090 (Gemma 4 26B ~85 tok/s),
promptquorum Apple Silicon 2026, atomic.chat 16GB Mac guide, turingpost SLM list.

## Selection policy (deterministic, observable, overridable)

Order of resolution for a local task's model:

1. `DEEPR_LOCAL_MODEL` - explicit operator choice always wins.
2. A per-task-admitted model from `deepr capacity admit` observations, when present -
   measured fitness beats any static preference.
3. A preference table filtered to models the local daemon actually has, ranked by
   task class:
   - `entailment/verification` (grounding checker): prefer general instruct models,
     EXCLUDE code-specialized (`*-coder*`) and thinking-generation models (latency
     makes evals and absorb impractical; measured 11.7h vs 40s/case).
   - `extraction/synthesis` (absorb, sync): general instruct, largest that fits.
   - `embedding` (semantic recall): embedding models only (`*embed*`).
4. If nothing suitable is installed: fail with a typed reason naming the tier-matched
   pull command, instead of silently using an unfit model. Silent unfitness is how the
   default configuration ended up at chance on a third-party benchmark.

Hardware detection stays minimal and honest: total VRAM via the daemon's own model
listing is unreliable, so the tier hint comes from what is already pulled (a user with
27B models pulled has the hardware for them) plus an optional `DEEPR_LOCAL_TIER`
override. No probing, no telemetry.

## Evaluation harness (already shipped)

`deepr eval grounding-correctness` is the fitness eval for the checker role: the
built-in 50-case curated set for a quick screen, `--benchmark-file` (HaluBench
adapter) for external comparability. Reports record the checker identity, so sweeps
are comparable across models and machines. The measured results that motivated all of
this (one day, one machine, five checkers) are in the session findings: an arbitrary
default is not a neutral choice.

## Staging

1. Shipped already: checker identity on eval reports; benchmark adapter; this design.
2. Next: implement the policy above in `default_local_model` (pure function over the
   installed-model list + env; unit-testable with a fake list; no daemon probing).
3. Then: wire `expert sync/absorb/eval` call sites through the task-class parameter.
4. Then: a short sweep matrix in CI-adjacent tooling is NOT planned - evals cost real
   local compute; they stay operator-run via the shipped eval commands.

## Measured addendum (2026-07-25 sweep)

Five local checkers (qwen2.5-coder:32b, qwen2.5:14b, gemma4:26b, qwen3:30b,
mistral-openorca:7b) all score at or below the trivial always-reject baseline on a
HaluBench faithfulness screen while scoring 0.97-1.00 on the curated entailment set.
Two of them produced identical verdict distributions. Conclusion: for the grounding
checker role specifically, model selection is not the binding constraint - the checker
prompt's framing does not transfer to long-passage QA-faithfulness inputs. The
selection policy above still holds for latency and task-hygiene reasons, but checker
fitness requires the prompt fix first, then re-measurement on a fresh benchmark slice.
