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

HaluBench ships as a single parquet file (14,900 rows across six source
datasets: halueval, DROP, pubmedQA, FinanceBench, RAGTruth, covidQA), so reading
it directly needs `pyarrow` or `pandas`. Neither is a Deepr dependency. Use the
Hugging Face datasets-server instead, which returns rows as JSON and needs
nothing beyond the standard library:

```python
import json, urllib.request, pathlib

# Evenly spaced offsets so the sample spans every source dataset rather than the
# head of the file. Deterministic, so the same slice is reproducible.
rows = []
for offset in range(0, 14900, 596):
    url = (
        "https://datasets-server.huggingface.co/rows"
        "?dataset=PatronusAI%2FHaluBench&config=default&split=test"
        f"&offset={offset}&length=4"
    )
    with urllib.request.urlopen(url, timeout=60) as response:
        rows.extend(item["row"] for item in json.load(response)["rows"])

pathlib.Path("halubench-sample.jsonl").write_text(
    "\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8"
)
```

Sample deliberately rather than running all 14,900 cases: each case is one
checker call, so a local model at roughly 40 seconds per case takes about an
hour per hundred cases. Report the sample size with the result.

One caveat worth knowing before reading a number: DROP-sourced rows carry a
stringified list of candidate answer spans (for example
`"['Rams', 'second', 'Marc Bulger']"`) rather than a single sentence. That is
HaluBench's own content and the adapter passes it through unchanged, but it is a
harder and less natural entailment target than a prose claim.

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
