"""CLI: `deepr expert source` - go and find material, then retain it.

The link that was missing. `expert acquire` fetches URLs somebody already
chose; `corpus_search` and `acquisition_plan` know how to *find* them and were
never wired to a command, so sourcing an expert meant hand-assembling a list of
links.

Two ways to decide what to look for, and the second is the point:

- **From a topic.** Six acquisition arms - descriptive, adversarial, genre,
  primary, recency, terminology - because a searcher left to itself asks the
  descriptive question six times and builds a corpus that agrees with itself.
  The arms are enforced in code; the queries inside them are written by a
  model, since templated queries are the brittle pattern.
- **From the expert's own practice.** Its live pursuits *are* the queries. A
  question the expert decided to chase is a better search than the subject
  name, and an expert that keeps asking the topic string has learned nothing
  about where to look. This is what makes acquisition month two differ from
  acquisition month one.

Politeness is structural rather than advisory. Queries are interleaved across
arms so an early stop cannot skip the adversarial ones, requests are throttled,
and the run stops as soon as the corpus spans enough distinct publishers -
because the goal was never to run every query. Running them all put roughly 120
requests at one free endpoint in a burst and got three builds rate-limited into
returning nothing.

$0. Free search, free fetch, and one model call to write the queries.
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

import click

from deepr.cli.colors import console, print_header, print_key_value, print_success, print_warning
from deepr.cli.commands.semantic.experts import expert
from deepr.cli.commands.semantic.study_backend import StudyBackendError, build_study_backend
from deepr.experts.paths import canonical_expert_dir


def _load_profile(name: str) -> Any:
    from deepr.experts.profile import ExpertStore

    profile = ExpertStore().load(name)
    if not profile:
        click.echo(f"Error: Expert not found: {name}", err=True)
        sys.exit(2)
    return profile


def _pursuit_queries(expert_name: str, limit: int) -> list[str]:
    """The expert's own live questions, if it has a practice."""
    from deepr.experts.research_practice import ResearchPractice

    path = canonical_expert_dir(expert_name) / "practice.json"
    try:
        practice = ResearchPractice.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return []
    return [p.question for p in practice.live_pursuits[:limit]]


def _plan_from_pursuits(topic: str, questions: list[str]) -> Any:
    """Wrap the expert's own questions as a plan.

    Marked as one arm rather than spread across six: these queries were not
    generated to cover the arms, and labelling them as though they were would
    misreport the coverage the search actually achieved.
    """
    from deepr.experts.acquisition_plan import ARM_DESCRIPTIVE, AcquisitionPlan, AcquisitionQuery

    plan = AcquisitionPlan(topic=topic)
    plan.queries = [
        AcquisitionQuery(text=q, arm=ARM_DESCRIPTIVE, rationale="a question this expert is chasing") for q in questions
    ]
    return plan


def _resolve_queries(expert_name: str, topic: str, *, from_practice: bool, limit: int) -> list[str]:
    """Decide what this run is searching for, refusing before any network call.

    Both refusals exit rather than falling back to the topic string. An expert
    asked to search its own pursuits and quietly given a generic topic search
    instead would report success for work it did not do.
    """
    if not from_practice:
        if not topic.strip():
            click.echo("Error: give a TOPIC, or use --from-practice to search what the expert is chasing.", err=True)
            sys.exit(2)
        return []

    if pursuits := _pursuit_queries(expert_name, limit):
        return pursuits
    click.echo(
        f'Error: {expert_name} has no live pursuits to search. Run: deepr expert practice "{expert_name}"',
        err=True,
    )
    sys.exit(2)


async def _build_plan(topic: str, *, backend: Any, from_practice: list[str]) -> tuple[Any, str]:
    """Decide what to search for. Returns the plan and how it was chosen."""
    if from_practice:
        return _plan_from_pursuits(topic, from_practice), "the expert's own live pursuits"

    from deepr.experts.query_proposal import propose_plan

    plan = await propose_plan(topic, completion=backend.completion)
    return plan, "a six-arm acquisition plan"


@expert.command(name="source")
@click.argument("name")
@click.argument("topic", required=False, default="")
@click.option("--from-practice", is_flag=True, help="Search the expert's own live pursuits instead of a topic")
@click.option("--target-hosts", default=8, show_default=True, help="Stop once the corpus spans this many publishers")
@click.option("--max-urls", default=40, show_default=True, help="Ceiling on URLs collected")
@click.option("--per-query", default=4, show_default=True, help="Results taken per query")
@click.option("--local", is_flag=True, help="Use local Ollama to write the queries ($0)")
@click.option("--plan", "plan_backend", default=None, help="Prepaid plan backend id (e.g. grok)")
@click.option("--plan-model", default=None, help="Model for the plan backend")
@click.option("--model", default=None, help="Explicit local model")
@click.option("--dry-run", is_flag=True, help="Show the queries and the URLs found, retain nothing")
def expert_source(
    name: str,
    topic: str,
    from_practice: bool,
    target_hosts: int,
    max_urls: int,
    per_query: int,
    local: bool,
    plan_backend: str | None,
    plan_model: str | None,
    model: str | None,
    dry_run: bool,
) -> None:
    """Find material for NAME on TOPIC and retain it ($0).

    With --from-practice the expert searches the questions it decided to chase
    rather than the subject name, which is what makes a later acquisition
    different from the first one.

    Stops as soon as the corpus spans enough distinct publishers. The goal is a
    corpus with independent origins, not a completed query list, and hammering
    a free endpoint for queries that add nothing is both waste and abuse.

    EXAMPLES:

      deepr expert source "TKG Expert" "temporal knowledge graphs" --plan grok
      deepr expert source "My Expert" --from-practice --plan grok
    """
    from deepr.experts.corpus_acquire import acquire_sources, default_fetch_page
    from deepr.experts.corpus_search import run_search_plan
    from deepr.experts.corpus_store import CorpusStore

    profile = _load_profile(name)

    pursuits = _resolve_queries(profile.name, topic, from_practice=from_practice, limit=per_query * 3)

    try:
        backend = build_study_backend(
            profile=profile, local=local, plan=plan_backend, plan_model=plan_model, model=model
        )
    except StudyBackendError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(2)

    print_header(f"Source: {profile.name}")
    print_key_value("Capacity", backend.cost_note)

    async def _run() -> tuple[Any, Any]:
        plan, how = await _build_plan(topic or profile.name, backend=backend, from_practice=pursuits)
        print_key_value("Searching", f"{len(plan.queries)} query(ies) from {how}")
        for query in plan.queries[:6]:
            console.print(f"  [dim]{query.arm}: {query.text}[/dim]")

        found = await run_search_plan(
            plan,
            per_query=per_query,
            max_urls=max_urls,
            target_hosts=target_hosts,
            on_progress=lambda note: console.print(f"  [dim]{note}[/dim]"),
        )
        return plan, found

    try:
        _, found = asyncio.run(_run())
    except Exception as exc:
        click.echo(f"Error: the search failed: {type(exc).__name__}: {exc}", err=True)
        sys.exit(2)

    urls = [hit.url for hit in found.hits]
    print_key_value("Found", f"{len(urls)} URL(s) across {len(found.distinct_hosts)} publisher(s)")
    if found.stopped_early:
        console.print(f"[dim]Stopped early: {found.stopped_early}[/dim]")

    if not urls:
        print_warning("Nothing found. The endpoint may be throttling; try again later rather than harder.")
        sys.exit(2)

    if dry_run:
        for url in urls[:20]:
            console.print(f"  {url}")
        print_warning("Dry run: nothing retained.")
        return

    store = CorpusStore(profile.name)
    before = len(store.active_entries())
    report = asyncio.run(
        acquire_sources(expert_name=profile.name, urls=urls, corpus=store, fetch_page=default_fetch_page())
    )
    after = len(store.active_entries())

    console.print()
    print_key_value("Retained", f"{after - before} new source(s), {after} in the corpus")
    if failures := getattr(report, "failures", None):
        print_warning(f"{len(failures)} fetch(es) failed and were skipped.")
    print_success(f'Next: deepr expert study "{profile.name}" --plan {plan_backend or "grok"}')
