"""Find candidate sources for a query. The channel Deepr did not have.

Acquisition could fetch a URL but not discover one, so every corpus began with
a person naming addresses. That is the weakest of the three channels
researchers use, and it caps an expert at whatever someone already knew to
look for.

This is deliberately thin. It returns candidate URLs and nothing else: no
ranking beyond what the engine gave, no relevance judgment, no filtering on
content. Selection pressure belongs upstream in the acquisition plan, which
decides *what to ask*, and downstream in the independence measurement, which
decides whether what came back is worth anything. A search module that also
judged quality would be three decisions in one place with no way to inspect
any of them.

Costs network only. No model call, no metered surface, no API key.
"""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

_ENDPOINT = "https://lite.duckduckgo.com/lite/"
_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) DeeprResearch/1.0"
_HREF_RE = re.compile(r'href="(https?://[^"]+)"', re.IGNORECASE)

_ENGINE_HOSTS = ("duckduckgo.com", "duck.com")

_JUNK_SUFFIXES = (".jpg", ".jpeg", ".png", ".gif", ".svg", ".ico", ".css", ".js", ".zip")

_MIN_INTERVAL_S = 2.5
"""Minimum gap between searches, process-wide.

Learned the expensive way: five expert builds running concurrently put roughly
120 queries at one endpoint in a burst, and three of the five came back with
zero URLs and no error. A rate limit that answers 200-with-nothing is
indistinguishable from a topic nobody has written about, which is the worst
shape a failure can take - it looks like a finding."""

_throttle_lock: asyncio.Lock | None = None
_last_request_at = 0.0


async def _throttle(min_interval_s: float | None = None) -> None:
    """Serialize searches across every concurrent caller in this process.

    The interval is a parameter so tests can set it to zero. A throttle that
    also slows the suite by two and a half minutes buys one problem with
    another, and a slow suite is the kind of debt that gets paid by running it
    less often.
    """
    interval = _MIN_INTERVAL_S if min_interval_s is None else min_interval_s
    if interval <= 0:
        return
    global _throttle_lock, _last_request_at
    if _throttle_lock is None:
        _throttle_lock = asyncio.Lock()
    async with _throttle_lock:
        wait = interval - (time.monotonic() - _last_request_at)
        if wait > 0:
            await asyncio.sleep(wait)
        _last_request_at = time.monotonic()


@dataclass
class SearchHit:
    """One candidate source, with the query that surfaced it."""

    url: str
    query: str
    arm: str = ""

    @property
    def host(self) -> str:
        return urlparse(self.url).netloc.lower().removeprefix("www.")

    def to_dict(self) -> dict[str, Any]:
        return {"url": self.url, "query": self.query, "arm": self.arm, "host": self.host}


@dataclass
class SearchResult:
    """What a plan turned up, and what it failed to turn up."""

    hits: list[SearchHit] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    stopped_early: str = ""
    """Why the plan stopped short, named rather than left as a silent truncation."""
    unrun_queries: int = 0
    answered: int = 0
    """Queries that returned anything. Zero across a whole plan means throttled,
    not that the subject is unwritten."""
    attempted_arms: set[str] = field(default_factory=set)
    """Every arm the plan ran, so an arm can be reported as contributing nothing.

    Derived from failures alone, an arm whose every result was already seen
    showed as neither found nor failed - invisible rather than reported. That
    is a check passing because its subject is missing rather than sound."""

    @property
    def distinct_hosts(self) -> set[str]:
        return {hit.host for hit in self.hits}

    def arms_that_found_nothing(self) -> list[str]:
        """Arms that returned nothing, named rather than quietly absent.

        An adversarial arm that finds nothing is a real signal: either the
        subject genuinely has no published critics, or the phrasing did not
        reach them. Both are worth knowing before the corpus is called
        balanced.
        """
        found = {hit.arm for hit in self.hits if hit.arm}
        attempted = set(self.attempted_arms) | {q.split("::", 1)[0] for q in self.failures if "::" in q}
        return sorted(attempted - found)

    @property
    def every_arm_tried(self) -> bool:
        """True once each arm has run at least one query.

        The gate on early stopping. Coverage reached during the descriptive
        arm is not coverage; it is the popular half of the subject.
        """
        return len(self.attempted_arms) >= 5

    @property
    def looks_throttled(self) -> bool:
        """Every query silent is a rate limit wearing the costume of a result."""
        return self.answered == 0 and len(self.failures) >= 5

    def to_dict(self) -> dict[str, Any]:
        return {
            "looks_throttled": self.looks_throttled,
            "stopped_early": self.stopped_early,
            "unrun_queries": self.unrun_queries,
            "answered": self.answered,
            "hit_count": len(self.hits),
            "distinct_hosts": len(self.distinct_hosts),
            "hits": [hit.to_dict() for hit in self.hits],
            "failures": self.failures,
            "arms_that_found_nothing": self.arms_that_found_nothing(),
        }


def _is_candidate(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    if not host or any(engine in host for engine in _ENGINE_HOSTS):
        return False
    return not url.lower().endswith(_JUNK_SUFFIXES)


def parse_result_urls(html: str, limit: int) -> list[str]:
    """Pull candidate URLs out of a results page, in the order given.

    Order is the engine's, kept rather than re-scored. Deepr has no basis for
    a better ranking here and inventing one would be a judgment nobody could
    inspect.
    """
    seen: list[str] = []
    for url in _HREF_RE.findall(html or ""):
        cleaned = url.split("&amp;")[0].strip()
        if _is_candidate(cleaned) and cleaned not in seen:
            seen.append(cleaned)
            if len(seen) >= limit:
                break
    return seen


async def search_once(
    query: str, *, limit: int = 6, client: Any = None, min_interval_s: float | None = None
) -> list[str]:
    """Run one query. Returns candidate URLs, or empty on any failure.

    Never raises: one dead query must not abort a plan of thirty.
    """
    import httpx

    await _throttle(min_interval_s)
    owns_client = client is None
    # trust_env=False so proxy environment variables cannot silently reroute a
    # search, and no redirect chasing so a result page cannot walk this
    # somewhere unintended. The endpoint answers the POST directly.
    client = client or httpx.AsyncClient(timeout=25.0, trust_env=False, follow_redirects=False)
    try:
        response = await client.post(_ENDPOINT, data={"q": query}, headers={"User-Agent": _USER_AGENT})
        if response.status_code >= 400:
            return []
        return parse_result_urls(response.text, limit)
    except Exception:
        return []
    finally:
        if owns_client:
            await client.aclose()


def interleave_by_arm(queries: list[Any]) -> list[Any]:
    """Round-robin across arms rather than running each arm to exhaustion.

    Stopping early is only safe if the arms are interleaved. Run arm by arm and
    a coverage stop fires during the descriptive arm, so the adversarial and
    primary queries - the ones that exist because nobody runs them unprompted -
    never execute at all. That would be worse than not stopping.
    """
    buckets: dict[str, list[Any]] = {}
    for query in queries:
        buckets.setdefault(query.arm, []).append(query)
    ordered: list[Any] = []
    while any(buckets.values()):
        for arm in list(buckets):
            if buckets[arm]:
                ordered.append(buckets[arm].pop(0))
    return ordered


async def run_search_plan(
    plan: Any,
    *,
    per_query: int = 4,
    max_urls: int = 60,
    target_hosts: int = 0,
    client: Any = None,
    on_progress: Any = None,
    min_interval_s: float | None = None,
) -> SearchResult:
    """Execute an acquisition plan, stopping once the corpus is diverse enough.

    The plan decided what to ask, including the arms nobody asks unprompted.
    This carries those questions to the network and brings back addresses; it
    makes no judgment about which are worth reading.

    ``target_hosts`` is the important parameter and the reason for the
    interleave. Running every query of every plan put roughly 120 requests at
    one free endpoint in a burst, which got three builds rate-limited into
    returning nothing. The goal was never to run every query; it was to end up
    with a corpus spanning enough independent publishers. Once that holds, the
    remaining queries are waste for us and abuse for them.
    """
    result = SearchResult()
    seen: set[str] = set()
    queries = interleave_by_arm(list(plan.queries))

    for index, query in enumerate(queries, 1):
        if len(result.hits) >= max_urls:
            result.stopped_early = f"reached the {max_urls}-URL ceiling"
        elif target_hosts and len(result.distinct_hosts) >= target_hosts and result.every_arm_tried:
            result.stopped_early = f"reached {len(result.distinct_hosts)} distinct hosts"
        if result.stopped_early:
            result.unrun_queries = len(queries) - index + 1
            break

        result.attempted_arms.add(query.arm)
        if on_progress:
            on_progress(f"query {index}/{len(queries)} [{query.arm}] {query.text[:60]}")

        urls = await search_once(query.text, limit=per_query, client=client, min_interval_s=min_interval_s)
        if not urls:
            result.failures.append(f"{query.arm}::{query.text}")
            continue
        result.answered += 1
        for url in urls:
            if url in seen:
                continue
            seen.add(url)
            result.hits.append(SearchHit(url=url, query=query.text, arm=query.arm))

    return result
