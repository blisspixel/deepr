# Design: local fresh context

Status: fresh/deep context, the local context eval, and source-pack sync
artifacts are shipped and included in current main.

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
- RAG eval practice separates faithfulness, response relevance, context
  relevance, and retrieval coverage. Deepr mirrors that split locally: the judge
  scores semantic quality, while code validates source counts, citation-label
  shape, latency, and cost.
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
- https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/
- https://developers.openai.com/cookbook/examples/evaluation/getting_started_with_openai_evals
- https://cloud.google.com/blog/products/data-analytics/how-the-open-knowledge-format-can-improve-data-sharing

## What shipped

`deepr expert sync NAME --local --fresh-context` builds a bounded source pack
before calling the local model. `--deep-context` uses the same free-only
contract but widens retrieval into a bounded multi-query pass for topics where a
single search is too thin.

- Search is free-only: a configured self-hosted SearXNG endpoint
  (`DEEPR_SEARXNG_URL`) is preferred; otherwise DuckDuckGo is used through the
  optional maintained `ddgs` package. Deepr does not use Brave, Tavily, or any
  API-key search provider in these modes.
- Explicit URLs in the freshness query are fetched directly through Deepr's
  built-in browser backend.
- Page fetches retain deterministic input order and exact attempt caps while
  using at most four concurrent slots across distinct hosts. Requests to the
  same normalized host remain serial, and malformed or non-HTTP targets share
  one conservative serial bucket. Built-in DuckDuckGo and automatic search
  routes keep multi-query searches serial to avoid amplifying free-endpoint
  rate limits; explicit SearXNG or injected backends may use four bounded slots.
- Direct HTTP and Wayback snapshot bodies stream under a configurable
  decompressed-byte ceiling, 8 MiB by default through
  `SCRAPE_MAX_RESPONSE_BYTES`. Chunked or compressed bodies stop at the ceiling
  plus one byte, oversized responses are terminal instead of falling through
  to heavier browser strategies, and Wayback metadata has a separate 256 KiB
  ceiling plus pre-dispatch and redirect SSRF validation.
- Deep context runs bounded query expansion, de-duplicates URLs across searches,
  fetches a larger source pack, and records the search queries and retrieval
  mode in metadata.
- The local prompt includes source labels and asks for citations on current
  factual claims. Deep-context prompts also ask the local model to synthesize
  across sources and name meaningful gaps.
- If retrieval does not produce the mode's minimum content-addressed evidence,
  the generation backend is not called. Sync retains the source pack, reports a
  retryable no-metered failure, and leaves the subscription due rather than
  absorbing model uncertainty or recording a false no-change result.
- The research result keeps Deepr metered cost at `$0` and carries fresh-context
  metadata for future loop records.
- `deepr eval local-context` compares no context, fresh context, and deep
  context for one local model with a local judge. It records mode scores,
  source counts, retrieved-source counts, citation counts, invalid citation
  labels, latency, and Deepr metered cost `$0`.
- Context-bearing sync runs persist a bounded source-pack artifact under the
  expert knowledge directory and include the artifact path, source count, and
  context mode in `SyncOutcome`. If the artifact cannot be written, Deepr
  refuses to absorb the context-grounded answer.
- Topic learning through `expert learn NAME TOPIC` and its explicit
  `learn-web` alias uses the same readiness shape. Every attempt persists a
  source pack, manifest, source notes, and content-addressed snapshots below the
  configured expert root. Successful synthesis also persists the report.
  Candidate extraction must select the exact supporting source label for each
  claim; only the corresponding durable source-note pointer enters that
  belief. Failed fetches and snippets remain diagnostics and are never counted
  as synthesized live sources.
  A single citation-form bracket pair is normalized (`[S1]` to `S1`) before the
  exact catalog-key lookup, and an exact catalog value is accepted by membership.
  Unknown pointers, nested wrappers, semantic aliases, and prose citations
  remain invalid.
  If every candidate is rejected, the expert's freshness timestamp remains
  unchanged. Human diagnostics identify failed retrievals with a bounded label
  and a URL without userinfo, query parameters, or fragments.

## Retrieval routing and generation readiness

Live dogfooding on 2026-07-11 exposed two avoidable forms of waste. A
subscription's full synthesis prompt, including a long focus paragraph and
answer-format instructions, was sent to DuckDuckGo as one search query. The
resulting pack contained five snippets but only one content-addressed page, and
a large local model still spent about ten minutes generating an answer before
the unready evidence envelope became visible.

The additive contract is:

- A subscription builds two strings. `answer_query` remains the complete
  freshness or baseline synthesis prompt. `retrieval_query` is a concise route
  made from the subscription topic plus a whitespace-normalized, length-bounded
  focus. Explicit HTTP(S) URLs are retained even when the surrounding focus is
  clipped. Research functions that accept the new keyword use it only for the
  context builder; older injected functions continue to receive the original
  two-argument seam.
- A source is generation-ready when it has a non-empty evidence excerpt and a
  valid content hash. This is a provenance and form decision only. It does not
  decide topical relevance, truth, source quality, or semantic support.
- Search-result snippets and failed fetch attempts remain in retrieval metadata
  for diagnosis, but only content-addressed evidence receives a citable source
  label. Readiness therefore does not require every search result to fetch.
- Fresh and deep modes apply bounded minimum ready-source counts before any
  local model or plan-quota CLI generation. A directly supplied URL retains a
  one-source path so explicit document review remains useful. Search-discovered
  fresh packs require two independently fetched or cache-validated pages, and
  deep packs require three. These defaults live in `FreshContextConfig` so an
  explicitly constructed test or evaluation envelope can declare a different
  structural threshold without changing semantic policy.
- An under-ready pack returns a typed, retryable, no-metered failure before
  generation. The result still carries the source pack and metadata, sync
  persists those artifacts, the subscription remains due, and neither local
  model execution nor plan quota is consumed. The failure may suggest retrying
  later or supplying explicit URLs, but it never falls through to a metered API.
- The same preflight protects topic `learn` and `learn-web`. Search-discovered
  topic learning requires two replayable pages, while a directly supplied URL
  retains the one-source review path. An under-ready attempt is persisted before
  the command exits, does not call local or plan generation, and does not update
  the expert's knowledge-refresh timestamp.

The readiness gate is intentionally not a lexical relevance filter. A fetched
football page can satisfy provenance shape and still be semantically irrelevant;
source relevance and claim support remain model or human judgments downstream.
The gate solves the narrower problem it can prove: do not spend scarce local or
prepaid generation time when there is not yet enough replayable evidence to
support the run.

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
- Source selection for an extracted claim remains model judgment. Deterministic
  code validates only that the selected label exists in the persisted source
  catalog and expands it to a compact replay pointer. It never assigns all
  retrieved URLs to every claim or uses citation text matching as a support
  verdict.
- Source-pack artifacts are derived run records. Canonical state remains the
  belief/event/edge store.

## Build order from here

1. Teach scheduler integration to choose fresh or deep context for due sync
   work when the admitted local model is used for a freshness task.
2. Add optional plan-quota retrieval adapters only after the free path is
   measured, with quota observations written to the append-only quota ledger.

The next immediate local slice is item 1. The scheduler can now rely on the
local context eval and durable source-pack trail before choosing fresh/deep
context automatically.
