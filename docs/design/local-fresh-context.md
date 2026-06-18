# Design: local fresh context

Status: first slice shipped in v2.16 main.

Local Ollama execution gives Deepr a zero-dollar maintenance path, but local
models do not automatically know what changed online. Freshness is a retrieval
problem before it is a model problem: Deepr must fetch bounded source context,
then ask the local model to answer from that context and cite it.

## Research grounding

- Anthropic's agent guidance favors simple, composable workflow envelopes before
  wider autonomy. For Deepr this means retrieval, prompt assembly, cost gates,
  and stop reasons stay deterministic while the model handles synthesis.
- Anthropic's long-running harness work calls out structured handoff artifacts
  and end-to-end testing as the antidote to self-declared completion. A fresh
  context pack is that handoff artifact for a local sync iteration.
- Ollama's OpenAI-compatible endpoint makes the local model adapter simple, but
  web search is a separate capability that requires an Ollama account API key.
  Deepr therefore treats local model execution and web retrieval as separate
  rungs.
- OKF reinforces the same context lesson: agents need portable, file-shaped
  knowledge with enough metadata to inspect source and freshness.

Primary references:

- https://www.anthropic.com/engineering/building-effective-agents
- https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents
- https://www.anthropic.com/engineering/harness-design-long-running-apps
- https://www.anthropic.com/engineering/writing-tools-for-agents
- https://docs.ollama.com/api/openai-compatibility
- https://docs.ollama.com/capabilities/web-search
- https://cloud.google.com/blog/products/data-analytics/how-the-open-knowledge-format-can-improve-data-sharing

## What shipped

`deepr expert sync NAME --local --fresh-context` now builds a bounded source
pack before calling the local model. The first slice is intentionally narrow:

- Search is free-only: DuckDuckGo through the optional `duckduckgo-search`
  package. It does not use Brave, Tavily, or any API-key search provider.
- Explicit URLs in the freshness query are fetched directly through Deepr's
  built-in browser backend.
- The local prompt includes source labels and asks for citations on current
  factual claims.
- If no sources are retrieved, the prompt tells the model to say that current
  context is unavailable.
- The research result keeps Deepr metered cost at `$0` and carries fresh-context
  metadata for future loop records.

This is not full local deep research. It is a retrieval-grounded local sync
adapter for scheduled expert maintenance.

## Boundaries

- Free-only means no Deepr provider calls and no API-key search backends.
- Network access is still network access. Fetching public pages is not offline
  and can fail, rate-limit, or return sparse snippets.
- Search results are context, not authority. Absorb still goes through the same
  source-trust, contradiction, dedup, and confidence gates.
- The source pack is disposable prompt context today. Canonical state remains
  the belief/event/edge store.

## Build order from here

1. Ingest saved `deepr eval local --save` artifacts into `deepr capacity admit`
   so admission can be derived from reviewed local evidence instead of manual
   score entry.
2. Add a local freshness eval prompt set that compares local sync with and
   without fresh context on time-sensitive questions.
3. Persist fresh-context source packs as run artifacts so `ExpertLoopRun` can
   report which sources drove accepted or rejected changes.
4. Teach scheduler integration to choose `--fresh-context` for due sync work
   when the admitted local model is used for a freshness task.
5. Add optional plan-quota retrieval adapters after the free path is measured,
   with quota observations written to the append-only quota ledger.

The next immediate implementation slice is item 1: turn local eval artifacts
into capacity admission evidence. That closes the manual gap between
measurement and routing without widening autonomy.
