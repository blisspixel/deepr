"""Frozen development case set for the correction-survival diagnostic (#259).

Three chronological source worlds about one small, fictional subject: the
retry behaviour of a job scheduler called Tern. The subject is invented so no
model has prior knowledge of it and every obligation can only be met from the
supplied sources.

- World 1 (2026-01-15): the v2 manual. Retries are safe because idempotency
  keys are on by default, and the queue alarm belongs at 1,000 pending jobs.
- World 2 (2026-04-10): a release note corrects one assumption in one
  environment. On v3 Windows agents idempotency keys are off by default. The
  alarm advice is untouched. An unsourced forum post claims retries are always
  unsafe.
- World 3 (2026-07-20): a genuine exception (external payment calls after a
  24-hour provider window) and an unresolved disagreement about the backoff cap.

Each world carries the study findings and the brief positions a deterministic
fixture produces for it. They stand in for model output so the first
diagnostic exercises the production selection and packing path without any
inference. Expected obligations and the review rubric are frozen here, before
any answer exists. Nothing in this module judges an answer.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from typing import Any

CASE_SET_VERSION = "correction-survival-v2"

REVIEW_LABELS: tuple[str, ...] = ("used_correctly", "ignored", "misapplied", "appropriately_deferred")
"""Reviewer verdicts for one obligation. Assigned by an accountable reviewer only."""

RUBRIC = (
    "For each obligation, judge only from the frozen world's sources and the answer text. "
    "used_correctly: the answer applies the obligation's evidence within its stated scope and explains it. "
    "ignored: the answer does not use the evidence where the question needs it. "
    "misapplied: the answer uses the evidence outside its scope, contradicts it, or uses knowledge the "
    "world did not contain. "
    "appropriately_deferred: the answer explicitly declines or scopes the point because the world cannot "
    "settle it, and says what would. "
    "Citation strings and matching words are not evidence of use."
)


@dataclass(frozen=True)
class FixtureSource:
    source_id: str
    origin: str
    observed_at: str
    trust_class: str
    text: str


@dataclass(frozen=True)
class FixtureFinding:
    finding_id: str
    lens: str
    source_id: str
    title: str
    payload: dict[str, str]
    anchor: str


@dataclass(frozen=True)
class FixturePosition:
    question: str
    stance: str
    reasoning: str
    supported_by: tuple[str, ...]
    would_change_my_mind: str = ""
    unresolved_dissent: str = ""
    resolution: str = "single"


@dataclass(frozen=True)
class World:
    world_id: str
    cutoff: str
    sources: tuple[FixtureSource, ...]
    findings: tuple[FixtureFinding, ...]
    positions: tuple[FixturePosition, ...]
    live: tuple[str, ...] = ()
    unknown: tuple[str, ...] = ()


@dataclass(frozen=True)
class Obligation:
    obligation_id: str
    expectation: str
    """use, preserve, correct_premise, retain_conflict, defer, or isolate."""
    description: str
    source_id: str = ""
    finding_id: str = ""


@dataclass(frozen=True)
class Case:
    case_id: str
    case_class: str
    world_id: str
    question: str
    obligations: tuple[Obligation, ...]
    forbidden_sources: tuple[str, ...] = ()
    """Sources that must not reach any arm, such as later worlds for a historical question."""
    cycles: int = 1
    """Brief/consult repetitions over unchanged evidence; repetition is not new evidence."""


_MANUAL = FixtureSource(
    "manual-v2",
    "docs.tern.example",
    "2026-01-15",
    "primary",
    "Tern 2 operations manual, section 7 (retries). Tern retries a failed job up to max_retries times "
    "with exponential backoff. A retry is safe because every job carries an idempotency key, and "
    "idempotency keys are enabled by default on Linux, Windows and container agents, so the worker discards a "
    "duplicate execution. We recommend max_retries = 5 for ordinary jobs. Section 9 (monitoring). "
    "Trigger the queue-depth alarm at 1,000 pending jobs; below that, backlog clears within one "
    "scheduling interval on the reference cluster.",
)
_RELEASE = FixtureSource(
    "release-v3",
    "docs.tern.example/releases",
    "2026-04-10",
    "primary",
    "Tern 3.0 release notes. Breaking change: on the Windows agent, idempotency keys are now disabled "
    "by default because the Windows key store is optional. Linux and container agents are unchanged "
    "and keep keys enabled. On a Windows agent without keys, a retry can execute a job's side effects "
    "twice. Either enable idempotency_keys explicitly or set max_retries = 0 for jobs with side "
    "effects. Monitoring defaults are unchanged in this release.",
)
_FORUM = FixtureSource(
    "forum-post",
    "forum.example/t/4411",
    "2026-04-12",
    "tertiary",
    "Forum post by an anonymous user: retries are always unsafe in every job scheduler, so turn them "
    "off everywhere. No measurement, version or platform is given.",
)
_PAYMENTS = FixtureSource(
    "payments-note",
    "docs.tern.example/integrations/payments",
    "2026-07-02",
    "primary",
    "Integration note for jobs that call external payment providers. Even with idempotency keys "
    "enabled, providers deduplicate requests only within their own window, typically 24 hours. A "
    "retry that lands after that window can charge twice. Cap total retry time below the provider "
    "window for payment jobs.",
)
_BACKOFF_VENDOR = FixtureSource(
    "backoff-vendor",
    "vendor-blog.example/tern-backoff",
    "2026-07-08",
    "secondary",
    "Vendor engineering blog: cap Tern's exponential backoff at 60 seconds; longer caps leave queues "
    "idle during short outages. Measured on our hosted clusters only.",
)
_BACKOFF_MAINTAINER = FixtureSource(
    "backoff-maintainer",
    "github.example/tern/issues/982",
    "2026-07-15",
    "primary",
    "Maintainer comment on issue 982: a 60 second backoff cap amplified load during the March regional "
    "outage; we suggest 300 seconds for self-hosted clusters. The thread remains open and no benchmark "
    "settles the difference.",
)

_W1_FINDINGS = (
    FixtureFinding(
        "mechanism-1",
        "mechanism",
        "manual-v2",
        "Worker keys suppress duplicate executions",
        {"concept": "The worker uses an enabled idempotency key to discard a duplicate job execution."},
        "the worker discards a duplicate execution",
    ),
    FixtureFinding(
        "synopsis-1",
        "synopsis",
        "manual-v2",
        "Tern 2 keys are on by default on the documented platforms",
        {
            "note": "Tern 2 idempotency keys are enabled by default on Linux, Windows and container agents; "
            "max_retries = 5 is recommended for ordinary jobs."
        },
        "idempotency keys are enabled by default on Linux, Windows and container agents",
    ),
    FixtureFinding(
        "synopsis-2",
        "synopsis",
        "manual-v2",
        "Queue alarm at 1,000 pending jobs",
        {"note": "Trigger the queue-depth alarm at 1,000 pending jobs on the reference cluster."},
        "Trigger the queue-depth alarm at 1,000 pending jobs",
    ),
)
_W2_FINDINGS = (
    *_W1_FINDINGS,
    FixtureFinding(
        "change-1",
        "change",
        "release-v3",
        "Windows agent keys off by default in 3.0",
        {
            "change": "On Tern 3.0 Windows agents idempotency keys are disabled by default; Linux and "
            "container agents are unchanged.",
        },
        "on the Windows agent, idempotency keys are now disabled by default",
    ),
    FixtureFinding(
        "failure-1",
        "failure",
        "release-v3",
        "Retries can duplicate side effects without keys",
        {"trigger": "Windows 3.0 agent without keys", "correction": "enable idempotency_keys or max_retries = 0"},
        "a retry can execute a job's side effects twice",
    ),
    FixtureFinding(
        "contention-1",
        "contention",
        "forum-post",
        "Forum claims retries are always unsafe",
        {"tension": "An unsourced forum post says to disable retries everywhere; it gives no version or platform."},
        "retries are always unsafe in every job scheduler",
    ),
)
_W3_FINDINGS = (
    *_W2_FINDINGS,
    FixtureFinding(
        "failure-2",
        "failure",
        "payments-note",
        "Payment retries after the provider window can charge twice",
        {
            "trigger": "retry after the actual provider deduplication window, typically 24 hours",
            "correction": "cap total retry time below that provider-specific window",
        },
        "A retry that lands after that window can charge twice",
    ),
    FixtureFinding(
        "contention-2",
        "contention",
        "backoff-vendor",
        "Vendor recommends a 60 second backoff cap",
        {"tension": "Vendor measured a 60 second backoff cap on its hosted clusters only."},
        "cap Tern's exponential backoff at 60 seconds",
    ),
    FixtureFinding(
        "contention-3",
        "contention",
        "backoff-maintainer",
        "Maintainer suggests a 300 second cap for self-hosted clusters",
        {
            "tension": "The maintainer reports amplified outage load at 60 seconds and suggests 300 for "
            "self-hosted clusters; no supplied benchmark settles the difference."
        },
        "we suggest 300 seconds for self-hosted clusters",
    ),
)

_RETRY_V2 = FixturePosition(
    "Is max_retries = 5 safe?",
    "For ordinary jobs on Tern 2 Linux, Windows and container agents, keys are enabled by default.",
    "The worker discards duplicate executions using the key.",
    ("mechanism-1", "synopsis-1"),
    would_change_my_mind="A platform where keys are off by default.",
)
_ALARM = FixturePosition(
    "Where should the queue-depth alarm trigger?",
    "On the reference cluster, at 1,000 pending jobs.",
    "Below that the backlog clears within one scheduling interval on the reference cluster.",
    ("synopsis-2",),
)
_RETRY_V3 = FixturePosition(
    "Is max_retries = 5 safe?",
    "For ordinary jobs on Linux and container agents yes; on Tern 3.0 Windows agents only with keys enabled.",
    "Keys make retries safe, and 3.0 turned them off by default on Windows only.",
    ("mechanism-1", "change-1", "failure-1"),
    would_change_my_mind="A release note changing the Linux default.",
    unresolved_dissent="An unsourced forum post says retries are always unsafe; it names no version or platform.",
    resolution="conditional",
)
_BACKOFF = FixturePosition(
    "What backoff cap should Tern use?",
    "Unresolved: 60 seconds on hosted clusters per the vendor, 300 seconds self-hosted per the maintainer.",
    "The vendor reports hosted measurements. The maintainer reports amplified load at 60 seconds and "
    "suggests 300 seconds for self-hosted clusters. No supplied benchmark settles the difference.",
    ("contention-2", "contention-3"),
    would_change_my_mind="A benchmark comparing both caps on the same cluster during an outage.",
    unresolved_dissent="Vendor and maintainer disagree and the issue thread is open.",
    resolution="irreducible",
)
_PAYMENT = FixturePosition(
    "Are payment job retries safe with keys enabled?",
    "Only if total retry time stays below the provider's deduplication window.",
    "Keys let the worker suppress duplicate executions. External providers separately deduplicate requests "
    "within their own window, typically 24 hours; local keys do not extend that provider window.",
    ("failure-2", "mechanism-1"),
    would_change_my_mind="A provider documenting unbounded deduplication.",
    resolution="conditional",
)

_RETRY_V3_PAYMENTS = replace(
    _RETRY_V3,
    stance=_RETRY_V3.stance + " Payment jobs additionally require total retry time below the provider window.",
    reasoning=_RETRY_V3.reasoning + " Retry count and local keys alone do not settle external payment safety.",
    supported_by=(*_RETRY_V3.supported_by, "failure-2"),
)

WORLDS: tuple[World, ...] = (
    World("w1", "2026-01-31", (_MANUAL,), _W1_FINDINGS, (_RETRY_V2, _ALARM)),
    World(
        "w2",
        "2026-04-30",
        (_MANUAL, _RELEASE, _FORUM),
        _W2_FINDINGS,
        (_RETRY_V3, _ALARM),
        live=("Whether other platforms change key defaults in later releases.",),
    ),
    World(
        "w3",
        "2026-07-31",
        (_MANUAL, _RELEASE, _FORUM, _PAYMENTS, _BACKOFF_VENDOR, _BACKOFF_MAINTAINER),
        _W3_FINDINGS,
        (_RETRY_V3_PAYMENTS, _ALARM, _BACKOFF, _PAYMENT),
        live=("The right backoff cap for self-hosted clusters.",),
        unknown=("Tern 3.0 defaults on agent platforms other than Linux, containers and Windows.",),
    ),
)

_LATER_THAN_W1 = ("release-v3", "forum-post", "payments-note", "backoff-vendor", "backoff-maintainer")

CASES: tuple[Case, ...] = (
    Case(
        "warranted-correction",
        "warranted_correction",
        "w2",
        "We run Tern 3.0 agents on Windows. Is max_retries = 5 still safe for jobs with side effects?",
        (
            Obligation(
                "use-correction", "use", "Keys are off by default on 3.0 Windows agents.", "release-v3", "change-1"
            ),
            Obligation("keep-mechanism", "preserve", "Keys are what make retries safe.", "manual-v2", "mechanism-1"),
            Obligation(
                "scope-linux", "preserve", "Linux and container agents are unaffected.", "release-v3", "change-1"
            ),
        ),
    ),
    Case(
        "inapplicable-contrary",
        "inapplicable_contrary",
        "w2",
        "A forum post says retries are always unsafe. Should we disable retries on our Linux Tern 3.0 agents?",
        (
            Obligation("keep-advice", "preserve", "Linux keeps keys on; retries stay safe.", "release-v3", "change-1"),
            Obligation(
                "weigh-forum",
                "use",
                "The post gives no version, platform or measurement.",
                "forum-post",
                "contention-1",
            ),
        ),
    ),
    Case(
        "unresolved-disagreement",
        "unresolved_disagreement",
        "w3",
        "What backoff cap should we configure for Tern?",
        (
            Obligation(
                "vendor-view", "retain_conflict", "Vendor: 60 seconds, hosted.", "backoff-vendor", "contention-2"
            ),
            Obligation(
                "maintainer-view",
                "retain_conflict",
                "Maintainer: 300 seconds, self-hosted; open.",
                "backoff-maintainer",
                "contention-3",
            ),
        ),
    ),
    Case(
        "historical",
        "historical",
        "w1",
        "As of January 2026, what did the Tern documentation recommend for max_retries on Windows agents?",
        (
            Obligation(
                "answer-from-w1",
                "use",
                "Tern 2 Windows keys are on by default; max_retries = 5 for ordinary jobs.",
                "manual-v2",
                "synopsis-1",
            ),
            Obligation("no-later-knowledge", "isolate", "No 3.0 or later source may inform the answer."),
        ),
        forbidden_sources=_LATER_THAN_W1,
    ),
    Case(
        "false-premise",
        "false_premise",
        "w2",
        "Since Tern 3.0 turned idempotency keys off on every platform, should we turn retries off on Linux too?",
        (Obligation("correct-premise", "correct_premise", "Only Windows agents changed.", "release-v3", "change-1"),),
    ),
    Case(
        "sound-premise-control",
        "sound_premise_control",
        "w2",
        "Since Tern 3.0 Windows agents have idempotency keys off by default, what should we change there?",
        (
            Obligation(
                "direct-answer",
                "use",
                "Enable keys or set max_retries = 0 for side effects.",
                "release-v3",
                "failure-1",
            ),
        ),
    ),
    Case(
        "missing-evidence",
        "missing_evidence",
        "w3",
        "What retry settings should we use for Tern 3.0 agents on macOS?",
        (
            Obligation(
                "defer-macos",
                "defer",
                "No provided source establishes Tern 3.0 macOS defaults; scope the gap and name a relevant check.",
            ),
        ),
    ),
    Case(
        "answerable-control",
        "answerable_control",
        "w3",
        "At what queue depth should the Tern alarm trigger?",
        (
            Obligation(
                "alarm",
                "preserve",
                "1,000 pending jobs on the reference cluster, unchanged since the v2 manual.",
                "manual-v2",
                "synopsis-2",
            ),
        ),
    ),
    Case(
        "near-match-version",
        "near_match_context",
        "w3",
        "On Tern 2 Windows agents, are idempotency keys on by default?",
        (
            Obligation("v2-default", "use", "Yes: the change applies to 3.0 only.", "manual-v2", "synopsis-1"),
            Obligation("v3-scope", "preserve", "The 3.0 change does not apply to v2.", "release-v3", "change-1"),
        ),
    ),
    Case(
        "synonymous-correction",
        "near_match_context",
        "w2",
        "Could automatic re-attempts run side effects twice on hosts with the Microsoft OS on release three?",
        (
            Obligation(
                "low-overlap-correction", "use", "Yes, without keys on 3.0 Windows agents.", "release-v3", "failure-1"
            ),
        ),
    ),
    Case(
        "repeated-compression",
        "repeated_compression",
        "w3",
        "Are retries safe for payment jobs?",
        (
            Obligation(
                "payment-window", "use", "Cap retry time below the provider window.", "payments-note", "failure-2"
            ),
            Obligation(
                "keys-mechanism",
                "preserve",
                "Local worker keys still suppress duplicate executions; the external provider has its own window.",
                "manual-v2",
                "mechanism-1",
            ),
        ),
        cycles=2,
    ),
)


def world(world_id: str) -> World:
    return next(item for item in WORLDS if item.world_id == world_id)


def _plain(value: Any) -> Any:
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    return value


def case_set_document(cases: tuple[Case, ...] = CASES) -> dict[str, Any]:
    """The frozen case set, or the named subset of it, as plain data for hashing."""
    return {
        "version": CASE_SET_VERSION,
        "rubric": RUBRIC,
        "review_labels": list(REVIEW_LABELS),
        "worlds": [_plain(asdict(item)) for item in WORLDS],
        "cases": [_plain(asdict(item)) for item in cases],
    }


def case_set_sha256(cases: tuple[Case, ...] = CASES) -> str:
    """Hash of exactly the cases a run scheduled; a subset never shares the full set's hash."""
    payload = json.dumps(case_set_document(cases), sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def distractor_sources(count: int) -> list[tuple[str, str]]:
    """Deterministic on-topic filler that shares vocabulary but carries no obligation.

    Small worlds fit every bound, so retrieval and packing cannot fail there.
    Filler is what makes those stages observable. It is recorded in the run.
    """
    return [
        (
            f"distractor-{index}",
            f"Tern operations note {index}: agents, retries, backoff, queues and idempotency keys are "
            f"discussed for planning exercise {index} in general terms. This note sets no default, names "
            "no version or platform, and makes no recommendation. " + "Background detail. " * 20,
        )
        for index in range(1, count + 1)
    ]


def source_inventory(item: World, distractors: int) -> tuple[FixtureSource, ...]:
    """The complete bytes and metadata used to materialize this source world."""
    return (
        *item.sources,
        *(
            FixtureSource(source_id, f"notes.example/{source_id}", item.cutoff, "secondary", text)
            for source_id, text in distractor_sources(distractors)
        ),
    )


def source_inventory_sha256(sources: tuple[FixtureSource, ...]) -> str:
    """Bind runtime additions as well as base sources, including their metadata."""
    payload = json.dumps(
        [asdict(source) for source in sources], sort_keys=True, ensure_ascii=True, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
