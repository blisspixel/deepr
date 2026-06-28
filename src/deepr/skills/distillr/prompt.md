# Distillr - Source Ingestion Skill (First-Party Native Instrument)

You have access to **distillr**, a source-ingestion engine that turns YouTube
videos, websites, and arXiv papers into a structured Markdown corpus with
cross-source synthesis. Where recon gives you fast factual grounding, distillr
gives you *depth*: a synthesized body of source material you can absorb as
durable academic knowledge with provenance.

## When to use this skill
- A knowledge gap maps to readable/watchable source material (papers, talks, articles) rather than a single fact.
- You need a literature-grounded answer, not a one-line lookup.
- You want to build or extend the expert's permanent corpus on a topic.
- You want to *stay current* on a topic you have already ingested (use `catch_up`).

## Spend discipline (important)
Distillr spends model budget and ingestion runs take minutes. Respect the budget:

1. **Always `list_topics` first, then `find_insights` (then `read_insight` or
   `list_topic_summary`).** The expert may already hold a synthesized corpus on
   the topic. If it does, answer from that and do not pay to ingest again.
2. **Use `discover` to preview** candidate sources before committing to ingestion.
   It is cheap and tells you whether ingestion is worth it.
3. **Only then ingest** (`papers` / `learn_topic` / `site_batch`),
   passing a `budget` cap. These are approval-gated by default.
4. **Use `catch_up`** instead of a full re-ingest when a topic is already in the
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
- `corpus_synthesis_path` / `synthesis_path` plus the `*_ingested` counts -> one
  high-value "academic" belief that cites the synthesis artifact for provenance.
- `insights` / `key_findings` / query `results` -> individual "academic" findings.
- `cost` is surfaced for the audit trail; it is not absorbed as a belief.

Treat distillr knowledge as **multi-source synthesis, not primary fact**:
absorb at moderate confidence and keep the citation to the corpus artifact so the
expert can trace and refresh it later.

## Invariants you must respect
- Searching the corpus (`list_topics` / `find_insights` / `read_insight` /
  `list_topic_summary` / `research_gaps`) is free; ingestion costs money.
  Never ingest when a corpus query would have answered the question.
- Treat `ask`, `find_insights_summary`, and `okf_export` as approval-gated
  unless the host explicitly provides a zero-cost guarantee. They synthesize or
  write derived artifacts and should not be auto-run as background reads.
- Always pass a `budget` on ingestion/refresh and honor approval gates.
- Keep provenance: every absorbed belief should point back to the synthesis path.

Example good flow: `find_insights("embedded finance economics")` -> if thin,
`discover(...)` to preview -> `papers(topic=..., query=..., limit=5)` -> absorb the
synthesis as academic knowledge -> later, `catch_up(topic=...)` to stay current.
