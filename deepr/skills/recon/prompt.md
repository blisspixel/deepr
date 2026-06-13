# Recon - Passive Domain Intelligence Skill (First-Party Native Instrument)

You have direct access to **recon**, a fast, zero-cost, zero-credential passive reconnaissance tool.

## When to use this skill
- The research target is (or contains) a domain name (company, vendor, product site, etc.).
- You need grounding facts about technology stack, email security posture, identity providers, or related infrastructure **before** doing deeper strategic or academic research.
- You want to discover related domains or subdomains that may be relevant to the query.
- You see references to "M365", "Google Workspace", "DMARC", "tenant", "SSO", "CDN", etc. in the conversation.

## Core tool: lookup_tenant (preferred)
Always prefer `format=json` when you intend to absorb the result into your knowledge.

The JSON response contains:
- `services`: concrete detected SaaS/infrastructure (high signal)
- `related_domains` and `tenant_domains`
- `insights`: hedged but useful derived observations
- `email_security_score` + DMARC/SPF/DKIM details
- `slugs` for stable fingerprint matching
- `posterior_observations` (Bayesian 80% credible intervals on high-level claims)
- `evidence` for provenance

Treat confidence levels honestly: "High" means 3+ corroborating sources; "Medium" or "Low" should be qualified when you surface the fact.

## Companion tools
- `analyze_posture(domain, profile=...)` - apply a lens (e.g. fintech, healthcare) for more targeted observations.
- `assess_exposure(domain)` - quick defensive posture score (0-100) useful for security-adjacent questions.

## Absorption guidance (KnowledgeAbsorber)
When you receive recon output (especially JSON), map the findings as follows:
- `services` and `slugs` → concrete infrastructure / SaaS facts (very high confidence when present)
- `insights` and `related_domains` → supporting context
- Always note that these are *passive external observables*, not authenticated truth.

Prefer recon early in a research thread. It is extremely cheap and often dramatically improves the quality of later work by giving the expert real grounding instead of hallucinated stack assumptions.

## Invariants you must respect
- Recon is strictly passive. It never performs active scanning or credentialed access.
- Output is intentionally hedged on sparse evidence. Do not overstate certainty.
- This tool is free and local. Use it liberally for any domain-bearing question.

Example good trigger: "What does acme.com actually run for email and identity?"
Example good usage: Call lookup_tenant with format=json, absorb the services + insights, then proceed with higher-cost tools only for gaps that recon could not fill.
