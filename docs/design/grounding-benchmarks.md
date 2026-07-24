# Proof by benchmark: grounding checker

Date: 2026-07-24

`deepr eval grounding-correctness` measures whether the grounding checker's
SUPPORTED verdicts are actually correct. By default it runs a small, built-in
curated set of human-labeled `(claim, evidence, label)` triples. That set is
enough to show the checker is not obviously broken, but it is authored in-repo,
so a good number on it is not comparable to anything the field publishes.

The `--benchmark-file` option closes that gap: it scores the checker against a
public, third-party-labeled benchmark, so the number can be compared to
externally reported results instead of being self-asserted.

## What this is and is not

- It measures **agreement between the checker's verdict and the benchmark's
  human ground-truth label**, scored deterministically. The model owns the
  entailment judgment (meaning); this harness only counts matches (form).
- It is **not** proof of world-truth, and a single benchmark is still bounded.
  The report discloses the source and the case count so a number is never
  over-read.
- It stays **$0 by default** (a local Ollama checker). A plan-quota checker can
  be selected with `--checker-plan`; no metered fallback is ever taken.

## Datasets are not vendored

The benchmark datasets are large and separately licensed, so Deepr does not
bundle or download them. You supply a local file; Deepr only reads it.

### HaluBench (`--benchmark-format halubench`)

HaluBench (PatronusAI/HaluBench) is a QA-faithfulness benchmark. Each row has a
`passage` (the grounding source), a `question`, an `answer`, and a binary
`label` (`PASS` = the answer is faithful to the passage, `FAIL` = hallucinated).

Deepr maps each row to a grounding case as:

| Grounding case | HaluBench field |
| --- | --- |
| `claim` | `answer` |
| `evidence` | `passage` |
| `label` | `supported` if `PASS`, else `unrelated` |

The question is dropped: the checker decides answer-against-passage entailment,
which is the faithfulness core. `FAIL` becomes a generic not-entailed label
because HaluBench does not separate contradiction from fabrication, and the
scorer treats every non-`supported` label identically (a SUPPORTED verdict on
any of them is the same false support).

To obtain it, download the dataset from its Hugging Face page and export the
rows as a JSON array or JSON Lines file with at least the `passage`, `answer`,
and `label` fields.

## Running it

```bash
# $0 local checker against a HaluBench export (JSON array or JSON Lines):
deepr eval grounding-correctness --benchmark-file halubench.jsonl --benchmark-format halubench

# Machine-readable report, including case_source and the headline metrics:
deepr eval grounding-correctness --benchmark-file halubench.jsonl --json

# Save the report under the benchmarks directory:
deepr eval grounding-correctness --benchmark-file halubench.jsonl --save
```

The headline metrics are unchanged from the curated run: **support precision**
(when the checker says SUPPORTED, how often the evidence truly entails),
**false-support rate** (the dangerous error; low is safe), **support recall**,
and **abstention rate**.

## Adding another benchmark

Adapters live in `src/deepr/evals/benchmark_adapters.py`. Add a function that
maps the benchmark's rows to `GroundingCase` objects and register it in
`BENCHMARK_ADAPTERS`; the `--benchmark-format` choices are derived from that
registry. Keep the mapping deterministic and preserve the benchmark's own
labels rather than re-deriving them with any lexical rule.
