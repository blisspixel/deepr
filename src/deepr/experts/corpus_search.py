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

import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

_ENDPOINT = "https://lite.duckduckgo.com/lite/"
_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) DeeprResearch/1.0"
_HREF_RE = re.compile(r'href="(https?://[^"]+)"', re.IGNORECASE)

_ENGINE_HOSTS = ("duckduckgo.com", "duck.com")

_JUNK_SUFFIXES = (".jpg", ".jpeg", ".png", ".gif", ".svg", ".ico", ".css", ".js", ".zip")


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

    def to_dict(self) -> dict[str, Any]:
        return {
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


async def search_once(query: str, *, limit: int = 6, client: Any = None) -> list[str]:
    """Run one query. Returns candidate URLs, or empty on any failure.

    Never raises: one dead query must not abort a plan of thirty.
    """
    import httpx

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


async def run_search_plan(
    plan: Any,
    *,
    per_query: int = 5,
    max_urls: int = 60,
    client: Any = None,
    on_progress: Any = None,
) -> SearchResult:
    """Execute an acquisition plan and collect what it found.

    The plan decided what to ask, including the arms nobody asks unprompted.
    This only carries those questions to the network and brings back
    addresses; it makes no judgment about which are worth reading.
    """
    result = SearchResult()
    seen: set[str] = set()

    for index, query in enumerate(plan.queries, 1):
        if len(result.hits) >= max_urls:
            result.failures.append(
                f"stopped at {max_urls} candidate URLs; {len(plan.queries) - index + 1} queries unrun"
            )
            break
        result.attempted_arms.add(query.arm)
        if on_progress:
            on_progress(f"query {index}/{len(plan.queries)} [{query.arm}] {query.text[:60]}")

        urls = await search_once(query.text, limit=per_query, client=client)
        if not urls:
            result.failures.append(f"{query.arm}::{query.text}")
            continue
        for url in urls:
            if url in seen:
                continue
            seen.add(url)
            result.hits.append(SearchHit(url=url, query=query.text, arm=query.arm))

    return result
