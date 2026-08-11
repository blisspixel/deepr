"""Acquire sources into an expert's corpus (Deepr fetches; nobody hands it files).

`expert retain` takes a path, which means a person has to go and get the source
first. That leaves acquisition outside the system: the expert cannot extend its
own corpus, cannot re-fetch when a source moves, and cannot act on a gap it
found. This module closes that.

Uses the existing fetch stack rather than a second one, so the same address
pinning, redirect handling, and content extraction apply as everywhere else in
Deepr.

Refresh is idempotent by content, not by HTTP: an unchanged page re-fetches and
re-hashes to the same sha, so nothing new is written. There are no
conditional-GET validators - a re-fetch is a full download that is then
discarded. That costs bandwidth and saves correctness, and the correctness is
what the corroboration counts depend on.

Costs network only. No model call, no metered surface.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from deepr.experts.corpus_store import CorpusStore

ACQUIRE_SCHEMA_VERSION = "deepr-expert-acquire-v1"

_MIN_USEFUL_CHARS = 200
"""Below this a fetch produced a nav shell or an error page, not a source."""

_MAX_SOURCE_CHARS = 400_000


@dataclass
class AcquiredSource:
    """One fetch attempt. Failure is recorded, not raised."""

    url: str
    status: str
    """retained | unchanged | too_short | too_large | fetch_failed | blocked"""
    sha256: str = ""
    origin_key: str = ""
    title: str = ""
    byte_len: int = 0
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AcquireResult:
    """What one acquire run fetched and retained."""

    expert_name: str
    schema_version: str = ACQUIRE_SCHEMA_VERSION
    sources: list[AcquiredSource] = field(default_factory=list)
    cost_usd: float = 0.0
    limitations: list[str] = field(default_factory=list)

    @property
    def retained(self) -> list[AcquiredSource]:
        return [s for s in self.sources if s.status == "retained"]

    @property
    def failed(self) -> list[AcquiredSource]:
        return [s for s in self.sources if s.status in {"fetch_failed", "blocked"}]

    @property
    def exit_code(self) -> int:
        """0 all fetched, 1 partial, 2 nothing usable."""
        if not self.sources:
            return 2
        usable = [s for s in self.sources if s.status in {"retained", "unchanged"}]
        if len(usable) == len(self.sources):
            return 0
        return 1 if usable else 2

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "expert": self.expert_name,
            "cost_usd": self.cost_usd,
            "totals": {
                "attempted": len(self.sources),
                "retained": len(self.retained),
                "failed": len(self.failed),
            },
            "sources": [s.to_dict() for s in self.sources],
            "limitations": self.limitations,
        }


def _origin_key_for(url: str) -> str:
    """Publisher identity, so a site's many pages stay one origin."""
    from deepr.experts.beliefs import _canonical_url_source_key

    return _canonical_url_source_key(url) or "url:unknown"


def _as_source_text(page: Any, url: str) -> str:
    """Render fetched content as the markdown the corpus retains.

    Only the body is hashed. Anything that varies between two fetches of the
    same document must stay out, because this text is what decides identity.

    A ``fetched_at`` date in the body made every refresh a new sha, so one page
    refreshed daily read as seven independent sources by the end of a week. The
    URL was the same bug half-fixed: the identical document mirrored at two
    addresses hashed differently, counted as two entries, and therefore as two
    independent origins - which is exactly the inflation the independence
    measurement exists to catch, defeated before it ever runs.

    URL and title are per-entry metadata on ``CorpusEntry``, where they are
    kept and do not change identity.
    """
    return (getattr(page, "text", "") or "").strip()


async def acquire_sources(
    *,
    expert_name: str,
    urls: list[str],
    corpus: CorpusStore,
    fetch_page: Any,
    trust_class: str = "secondary",
) -> AcquireResult:
    """Fetch each URL and retain what came back.

    ``fetch_page`` is injected (an awaitable url -> page) so this is unit
    testable with no network. One failed URL never aborts the run: a partial
    corpus is more useful than none, and the failures are reported.
    """
    result = AcquireResult(expert_name=expert_name)
    seen: set[str] = set()

    for raw_url in urls:
        url = str(raw_url).strip()
        if not url or url in seen:
            continue
        seen.add(url)

        try:
            page = await fetch_page(url)
        except Exception as exc:
            result.sources.append(AcquiredSource(url=url, status="fetch_failed", detail=str(exc)[:300]))
            continue

        status_code = int(getattr(page, "status_code", 200) or 200)
        if status_code >= 400:
            result.sources.append(AcquiredSource(url=url, status="fetch_failed", detail=f"HTTP {status_code}"))
            continue

        text = _as_source_text(page, url)
        body_len = len((getattr(page, "text", "") or "").strip())
        if body_len < _MIN_USEFUL_CHARS:
            # A near-empty fetch is a nav shell or a soft error page. Retaining
            # it would add an origin that carries nothing and inflate coverage.
            result.sources.append(
                AcquiredSource(
                    url=url,
                    status="too_short",
                    detail=f"{body_len} chars of body; likely a nav shell or error page",
                )
            )
            continue
        if len(text) > _MAX_SOURCE_CHARS:
            result.sources.append(AcquiredSource(url=url, status="too_large", detail=f"{len(text)} chars"))
            continue

        entry, was_new = corpus.add(
            text,
            origin_key=_origin_key_for(url),
            title=(getattr(page, "title", "") or url)[:200],
            url=url,
            publisher=_origin_key_for(url).removeprefix("url:"),
            kind="web_page",
            trust_class=trust_class,
            fetched_at=datetime.now(UTC).isoformat(),
        )
        result.sources.append(
            AcquiredSource(
                url=url,
                status="retained" if was_new else "unchanged",
                sha256=entry.sha256,
                origin_key=entry.origin_key,
                title=entry.title,
                byte_len=entry.byte_len,
            )
        )

    origins = {s.origin_key for s in result.sources if s.origin_key}
    if len(origins) == 1 and len(result.retained) > 1:
        result.limitations.append(
            f"All sources came from one origin ({next(iter(origins))}). Agreement "
            "within one publisher is not corroboration."
        )
    if result.failed:
        result.limitations.append(
            f"{len(result.failed)} URL(s) could not be fetched; the corpus reflects only what arrived."
        )
    return result


def default_fetch_page() -> Any:
    """The standard Deepr fetch path, so acquisition inherits its safeguards."""
    from deepr.tools.browser_backend import BuiltinBrowserBackend

    backend = BuiltinBrowserBackend()

    async def _fetch(url: str) -> Any:
        return await backend.fetch_page(url)

    return _fetch
