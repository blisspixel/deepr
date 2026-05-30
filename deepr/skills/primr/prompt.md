# Primr — Strategic Company Intelligence Skill (First-Party Native Instrument)

You have access to **primr**, a strategic company-intelligence engine. It does
adaptive scraping plus AI synthesis to produce consultant-grade briefs:
competitive positioning, hiring signals, strategic initiatives, tech stack, and
constraints. It folds a recon pre-flight (infrastructure facts) into synthesized
strategic analysis, so it is the deepest company tool you have.

## When to use this skill
- The question is about a specific company's strategy, competitive position, hiring, or initiatives.
- You need a full strategic brief or a sector map across several companies.
- Recon-level facts and a quick scrape are not enough; you need synthesis.

## Cost and time discipline (critical)
Primr is the **heaviest, most expensive** instrument: a full analysis takes
35-50 minutes and costs real money. Treat it accordingly.

1. **Always `estimate_run` first.** It is free and returns the expected cost and
   duration so the run can be approved deliberately. Never start a full run blind.
2. **Prefer `quick_lookup` when you only need fast context** (recon + scrape, ~5
   min, ~$0.10) instead of a full 35-50 min `research_company`.
3. **Pass the approved `budget`** to every cost-incurring tool. All of them are
   approval-gated by default.
4. **Treat runs as async.** `research_company` / `batch_analyze` stream progress
   and survive disconnects. Poll with `check_jobs`; the run can be resumed via
   the MCP task-durability layer rather than restarted from scratch.

## Response shape and absorption (KnowledgeAbsorber)
`research_company` returns structured JSON, e.g.:

```json
{
  "company": "Stripe", "domain": "stripe.com", "mode": "full",
  "report_path": "output/Stripe_Strategic_Overview.md",
  "strategy_path": "output/Stripe_AI_Strategy.md",
  "sections": 23, "citations": 48,
  "recon_summary": {"provider": "AWS", "services_count": 14},
  "hiring_signals": {"total_roles": 127, "ml_roles": 52, "top_initiatives": ["..."]},
  "cost": 0.74, "duration_minutes": 38
}
```

`KnowledgeAbsorber.categorize_primr_response` maps this across categories:
- `recon_summary` → **infrastructure** facts (factual, higher confidence).
- the brief, `hiring_signals`, and strategic initiatives → **strategic**
  knowledge (synthesized, moderate confidence), each citing the report artifact.
- `cost` / `duration_minutes` are surfaced for the audit trail, not absorbed.

Keep provenance: every absorbed belief should point back to `report_path` /
`strategy_path` so the expert can re-open the source and refresh later (use
`delta` to re-run and integrate only what changed).

## Invariants you must respect
- Estimate before you run; never start a paid analysis without an approved budget.
- Distinguish infrastructure facts (high confidence) from strategic synthesis
  (moderate confidence) when you surface findings.
- Quick context belongs in `quick_lookup`; reserve `research_company` for when a
  full brief is genuinely needed.

Example good flow: `estimate_run("stripe.com", mode=full)` → on approval,
`research_company(domain="stripe.com", budget=1.0)` → absorb infrastructure +
strategic findings with report provenance → later `delta` to stay current.
