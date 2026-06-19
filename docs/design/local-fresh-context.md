# Design: local fresh context

Status: first two slices shipped in v2.16 main.

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
  web search is a separate capability. Deepr therefore treats local model
  execution and web retrieval as separate rungs.
- Gemini Deep Research and OpenAI/Azure deep research expose the same core
  contract at managed scale: long-running background research, iterative
  searching and reading, source citations, and explicit tool/data-source
  availability. Deepr's local path should mimic that harness shape with free
  components before using paid APIs.
- Open local research projects converge on Ollama or another OpenAI-compatible
  local endpoint plus a search layer such as SearXNG, then repeat search,
  read, reflect, and synthesize for bounded cycles.
- OKF reinforces the same context lesson: agents need portable, file-shaped
  knowledge with enough metadata to inspect source and freshness.

Primary references:

- https://www.anthropic.com/engineering/building-effective-agents
- https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents
- https://www.anthropic.com/engineering/harness-design-long-running-apps
- https://www.anthropic.com/engineering/writing-tools-for-agents
- https://docs.ollama.com/api/openai-compatibility
- https://ai.google.dev/gemini-api/docs/interactions/deep-research
- https://developers.openai.com/api/docs/guides/tools-web-search
- https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/deep-research
- https://github.com/langchain-ai/local-deep-researcher
- https://github.com/LearningCircuit/local-deep-research
- https://docs.gptr.dev/docs/gpt-researcher/llms
- https://docs.searxng.org/dev/search_api.html
- https://cloud.google.com/blog/products/data-analytics/how-the-open-knowledge-format-can-improve-data-sharing

## What shipped

`deepr expert sync NAME --local --fresh-context` builds a bounded source pack
before calling the local model. `--deep-context` uses the same free-only
contract but widens retrieval into a bounded multi-query pass for topics where a
single search is too thin.

- Search is free-only: a configured self-hosted SearXNG endpoint
  (`DEEPR_SEARXNG_URL`) is preferred; otherwise DuckDuckGo is used through the
  optional `duckduckgo-search` package. Deepr does not use Brave, Tavily, or any
  API-key search provider in these modes.
- Explicit URLs in the freshness query are fetched directly through Deepr's
  built-in browser backend.
- Deep context runs bounded query expansion, de-duplicates URLs across searches,
  fetches a larger source pack, and records the search queries and retrieval
  mode in metadata.
- The local prompt includes source labels and asks for citations on current
  factual claims. Deep-context prompts also ask the local model to synthesize
  across sources and name meaningful gaps.
- If no sources are retrieved, the prompt tells the model to say that current
  context is unavailable, and sync records no changes rather than absorbing the
  local model's uncertainty as expert beliefs.
- The research result keeps Deepr metered cost at `$0` and carries fresh-context
  metadata for future loop records.

This is not full local deep research yet. It is a retrieval-grounded local sync
adapter with a deeper source-gathering mode for scheduled expert maintenance.

## Boundaries

- Free-only means no Deepr provider calls and no API-key search backends.
- SearXNG still sends queries to whichever engines the user's SearXNG instance
  enables. A local SearXNG container improves control and avoids Deepr API
  spend, but it is not the same as an offline local index.
- Network access is still network access. Fetching public pages is not offline
  and can fail, rate-limit, or return sparse snippets.
- Search results are context, not authority. Absorb still goes through the same
  source-trust, contradiction, dedup, and confidence gates.
- The source pack is disposable prompt context today. Canonical state remains
  the belief/event/edge store.

## Build order from here

1. Add a local freshness/deep-context eval prompt set that compares no context,
   fresh context, and deep context on time-sensitive questions.
2. Persist source packs as run artifacts so `ExpertLoopRun` can report which
   sources drove accepted or rejected changes.
3. Teach scheduler integration to choose fresh or deep context for due sync
   work when the admitted local model is used for a freshness task.
4. Add optional plan-quota retrieval adapters only after the free path is
   measured, with quota observations written to the append-only quota ledger.

The next immediate local slice is item 1. That gives local deep context an
acceptance metric before schedulers choose it automatically.
