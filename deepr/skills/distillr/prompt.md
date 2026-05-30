# Distillr — Source Ingestion Skill (First-Party Native Instrument)

You have access to **distillr**, a source-ingestion engine that turns YouTube
videos, websites, and arXiv papers into a structured Markdown corpus with
cross-source synthesis. Where recon gives you fast factual grounding, distillr
gives you *depth*: a synthesized body of source material you can absorb as
durable academic knowledge with provenance.

## When to use this skill
- A knowledge gap maps to readable/watchable source material (papers, talks, articles) rather than a single fact.
- You need a literature-grounded answer, not a one-line lookup.
- You want to build or extend the expert's permanent corpus on a topic.
- You want to *stay current* on a topic you have already ingested (use `refresh`).

## Spend discipline (important)
Distillr spends model budget and ingestion runs take minutes. Respect the budget:

1. **Always `query_library` first.** The expert may already hold a synthesized
   corpus on the topic. If it does, answer from that and do not pay to ingest again.
2. **Use `discover` to preview** candidate sources before committing to ingestion.
   It is cheap and tells you whether ingestion is worth it.
3. **Only then ingest** (`ingest_papers` / `ingest_youtube` / `ingest_sites`),
   passing a `budget` cap. These are approval-gated by default.
4. **Use `refresh`** instead of a full re-ingest when a topic is already in the
   corpus and you only want what is new.

## Response shape and absorption (KnowledgeAbsorber)
Ingestion tools return structured JSON, e.g.:

```json
{
  "topic": "embedded_finance",
  "papers_ingested": 12,
  "synthesis_path": ".../embedded_finance_Paper_Synthesis.md",
  "corpus_synthesis_path": ".../embedded_finance_Corpus_Synthesis.md",
  "insights": ["..."],
  "cost": 0.82
}
```

Map findings as follows (the absorber's `categorize_distillr_response` does this):
- `corpus_synthesis_path` / `synthesis_path` plus the `*_ingested` counts → one
  high-value "academic" belief that cites the synthesis artifact for provenance.
- `insights` / `key_findings` / query `results` → individual "academic" findings.
- `cost` is surfaced for the audit trail; it is not absorbed as a belief.

Treat distillr knowledge as **multi-source synthesis, not primary fact**:
absorb at moderate confidence and keep the citation to the corpus artifact so the
expert can trace and refresh it later.

## Invariants you must respect
- Searching the corpus (`query_library`) is free; ingestion costs money. Never
  ingest when a corpus query would have answered the question.
- Always pass a `budget` on ingestion/refresh and honor approval gates.
- Keep provenance: every absorbed belief should point back to the synthesis path.

Example good flow: `query_library("embedded finance economics")` → if thin,
`discover(...)` to preview → `ingest_papers(query=..., budget=1.0)` → absorb the
synthesis as academic knowledge → later, `refresh(topic=...)` to stay current.
