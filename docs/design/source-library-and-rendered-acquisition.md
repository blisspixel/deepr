# Source libraries and rendered web acquisition

Reviewed 2026-09-20, America/Los_Angeles. Source observations use UTC.
Implementation priority: source integrity and reference retrieval now; bounded
rendered acquisition within S1. No external crawler framework is added.

## What Deepr already does

`corpus_search.py` supplies free search. `corpus_acquire.py` retains fetched
content by hash through `BuiltinBrowserBackend`, `ContentFetcher` and the
existing pinned HTTP transport. The transport bounds decoded response bytes
and validates actual connection destinations and redirects. Fresh-context
maintenance already has conditional HTTP validators and observation records.
Search results help discover sources; snippets do not replace reference content.

The browser extra already includes Playwright. However, the old browser fetch
entry points return before navigation: their subrequests and redirects do not
yet have equivalent destination and decoded-size enforcement. Merely enabling
that code would weaken the current fetch contract. This is a known
implementation prerequisite, not a requirement to import another framework.

The formation trial retained one of four attempted sources. The failures are
evidence of acquisition limits; they do not establish that all three failures
were caused by JavaScript. Inspect each failure before choosing a renderer.
An acquisition bug also coerced transport status zero to HTTP 200, allowing a
sufficiently long error message to become source content. The repair rejects
non-success responses and records observation time, final URL and actual status.

## Selected upstream review

These are inspected patterns, not reproduced performance or anti-bot claims.
The source revisions were fetched directly; no repository was vendored.

| Project and inspected revision | Verified shape | Useful idea for Deepr |
| --- | --- | --- |
| Crawl4AI `862f6bccb9c063f49b9d42701baa0eea17a4993f` | Playwright strategy, separate navigation/interactions/waits/capture, bounded scroll steps. Its license contains Apache 2.0 text plus an additional attribution requirement. | Separate fetching, rendering and extraction. Support explicit content readiness and bounded incremental capture; retain evidence of incomplete loading. |
| Stagehand `ea2789ca56e8a7ee154850de37657823c98604f8` | MIT license. Current v3 documents its own CDP engine, local/browser-service environments, and observe/act/extract interfaces. The older description as simply a Playwright wrapper is incomplete. | Separate observation, a proposed interaction, execution and verification. Keep interactions small and inspectable. A local browser does not itself prove local inference or zero external cost. |
| Crawlee `458cf6cf1ac5632bdddd57a3110230650cac4d88` | Apache 2.0. Playwright crawler delegates lifecycle to a browser crawler. Its navigation phase shares one remaining deadline across hooks and navigation; failed-request handling preserves exhausted work. | One end-to-end deadline, bounded attempts, explicit terminal failures, cleanup and recoverable request identity. Start with one page, not a fleet of browsers. |
| Nodriver `a71cda374651d13815a42c5eeb61af04a711eaa7` | Current repository is AGPL-3.0, not MIT. It advertises direct asynchronous CDP and browser-detection resistance. | Direct browser protocols are a design option, not proof of reliable access. No source code is copied. Challenge handling is not a prerequisite for obtaining authoritative public references. |

Primary sources:
[Crawl4AI strategy](https://github.com/unclecode/crawl4ai/blob/862f6bccb9c063f49b9d42701baa0eea17a4993f/crawl4ai/async_crawler_strategy.py),
[interaction order](https://github.com/unclecode/crawl4ai/blob/862f6bccb9c063f49b9d42701baa0eea17a4993f/docs/md_v2/core/page-interaction.md),
[license](https://github.com/unclecode/crawl4ai/blob/862f6bccb9c063f49b9d42701baa0eea17a4993f/LICENSE);
[Stagehand API](https://github.com/browserbase/stagehand/blob/ea2789ca56e8a7ee154850de37657823c98604f8/packages/docs/v3/references/stagehand.mdx),
[action dispatch](https://github.com/browserbase/stagehand/blob/ea2789ca56e8a7ee154850de37657823c98604f8/packages/extension/handlers/handlerUtils/actHandlerUtils.ts),
[engine overview](https://github.com/browserbase/stagehand/tree/ea2789ca56e8a7ee154850de37657823c98604f8),
[license](https://github.com/browserbase/stagehand/blob/ea2789ca56e8a7ee154850de37657823c98604f8/LICENSE);
[Crawlee browser lifecycle](https://github.com/apify/crawlee/blob/458cf6cf1ac5632bdddd57a3110230650cac4d88/packages/browser-crawler/src/internals/browser-crawler.ts),
[Playwright crawler](https://github.com/apify/crawlee/blob/458cf6cf1ac5632bdddd57a3110230650cac4d88/packages/playwright-crawler/src/internals/playwright-crawler.ts),
[license](https://github.com/apify/crawlee/blob/458cf6cf1ac5632bdddd57a3110230650cac4d88/LICENSE.md);
[Nodriver repository](https://github.com/ultrafunkamsterdam/nodriver/tree/a71cda374651d13815a42c5eeb61af04a711eaa7),
[license](https://github.com/ultrafunkamsterdam/nodriver/blob/a71cda374651d13815a42c5eeb61af04a711eaa7/LICENSE.txt).

Stagehand's inspected action dispatcher resolves a target, selects from an
explicit method map, records execution details, and rejects unsupported methods.
That separation is useful for Deepr's future interaction boundary. Its handlers
also include form entry and other actions outside reference acquisition; a
research reader should expose only the subset its task requires.

## Delivery order

1. Build the reference library around the expert's practical scope. Retain
   original documents, versions, publisher identity, citations, worked examples,
   publication dates where known and observation history. Independent analyses
   explain tradeoffs; duplicated publisher pages are not independent confirmation.
2. Retrieve original text as well as notes. Current consultation now searches
   bounded retained text, including details omitted from findings. Save the
   exact delivered passages and omissions. Test retrieval on real questions;
   text overlap only routes candidates.
3. Add a renderer behind the existing browser-backend interface. HTTP stays the
   cheap first attempt. A rendered fallback needs a concrete reason, isolated
   ephemeral browser state, no ambient account cookies, the same destination
   protections for every network path, and total page/request/byte/time limits.
   Explicit public feeds or documented JSON endpoints can avoid rendering when
   they contain the needed reference content.
4. Use content readiness with a deadline. A live page can poll forever, so
   network-idle alone is insufficient. Record the wait condition and result.
   Expand or scroll only within an explicit interaction budget. Capture content
   incrementally when a virtual list replaces earlier DOM nodes. Do not label
   a captured window as the complete source.
5. Extract structure without inference first: headings, prose, lists, tables,
   code, links and citations. Keep rendered evidence and source hashes separate
   from cleaned Markdown and model interpretation. An LLM can help interpret
   complex content using admitted owned capacity; rendering requires no LLM.
6. Add question-directed interaction only after single-page rendering passes.
   Observe, propose, execute a permitted bounded action, verify the result and
   stop on success, denial, exhausted limits or repeated failure. Broader crawl
   queues and concurrency are later optimizations justified by measured demand.

Both local rendering and local inference can have zero incremental external
API cost. Browser services, proxies, paid search and remote inference are
separate capacity sources; an open-source license does not establish their cost.
Any future copied source must retain its applicable copyright, license and
NOTICE requirements. Independently implemented patterns avoid importing a
framework's dependency tree or copying an incompatible module.

## Acceptance before enabling rendering

Use controlled pages for delayed hydration, perpetual polling, replaced virtual
lists, tables/code, nested frames, redirects, oversized decoded responses,
unavailable runtimes, cancellation and denied access. Include adversarial
subrequests and alternate browser network channels. Verify that cleanup stops
work and that every receipt binds original URL, final URL, status, actual
observation time, extraction method, bounds, source identity and incomplete
content. Add a small dated public-source smoke test after the controlled suite.
Then test whether the newly accessible material improves advice. A rendered
page or successful search is not itself evidence that the expert understood it.
