"""CLI: retain a corpus, study it through several lenses, render a notebook.

The loop this completes:

    expert retain   -> keep a source, with its origin and trust
    expert corpus   -> see what is retained
    expert study    -> read it through several lenses ($0 local or prepaid plan)
    expert notebook -> render what was found, in reading order

Study proposes; it never writes beliefs. Promoting a finding into an expert's
belief store stays an explicit absorb, because admission is a separate decision
from reading.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import click

from deepr.cli.colors import console, print_header, print_key_value, print_success, print_warning
from deepr.cli.commands.semantic.experts import expert
from deepr.cli.commands.semantic.study_backend import StudyBackendError, build_study_backend
from deepr.experts.corpus_store import CorpusStore
from deepr.experts.notebook import NOTEBOOK_MARKER, build_notebook
from deepr.experts.study import run_study
from deepr.experts.study_lenses import DEFAULT_LENS_KEYS, LENSES, resolve_lenses

_MAX_SOURCE_CHARS = 400_000


def _load_profile(name: str) -> Any:
    from deepr.experts.profile import ExpertStore

    profile = ExpertStore().load(name)
    if not profile:
        click.echo(f"Error: Expert not found: {name}", err=True)
        sys.exit(2)
    return profile


def _default_origin_key(url: str, path: Path) -> str:
    """Collapse to publisher, not file.

    Many files routinely come from one publisher. Counting each as its own
    origin would let a single site's crawl read as broad corroboration, which is
    the accounting error that makes quality reporting lie.
    """
    if url:
        from deepr.experts.beliefs import _canonical_url_source_key

        if key := _canonical_url_source_key(url):
            return key
    return f"path:{path.parent.name or path.stem}"


@expert.command(name="retain")
@click.argument("name")
@click.argument("source", type=click.Path(exists=True, dir_okay=False, path_type=str))
@click.option("--url", default="", help="Source URL, used to derive publisher origin")
@click.option("--publisher", default="", help="Publisher label for the sources table")
@click.option("--title", default="", help="Human title for this source")
@click.option("--origin-key", default="", help="Override the derived origin key")
@click.option(
    "--trust-class",
    type=click.Choice(["primary", "secondary", "tertiary"]),
    default="secondary",
    help="primary=operator-attested stance, secondary=official/first-party, tertiary=web",
)
@click.option("--json", "as_json", is_flag=True, help="Emit JSON")
def expert_retain(
    name: str,
    source: str,
    url: str,
    publisher: str,
    title: str,
    origin_key: str,
    trust_class: str,
    as_json: bool,
) -> None:
    """Retain SOURCE in NAME's corpus so it can be studied and re-read ($0).

    Retention is what makes a second reading possible. Without it an expert
    cannot be studied through another lens, cannot show the passage behind a
    finding, and cannot be re-derived when understanding of the field moves.

    Idempotent by content: retaining the same text twice is a no-op.

    EXAMPLES:

      deepr expert retain "My Expert" ./docs/spec.md --url https://example.org/spec
    """
    profile = _load_profile(name)
    path = Path(source)
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) > _MAX_SOURCE_CHARS:
        click.echo(f"Error: source exceeds {_MAX_SOURCE_CHARS} chars; split it first", err=True)
        sys.exit(2)

    store = CorpusStore(profile.name)
    try:
        entry, was_new = store.add(
            text,
            origin_key=origin_key or _default_origin_key(url, path),
            title=title or path.stem,
            url=url,
            publisher=publisher,
            trust_class=trust_class,
        )
    except ValueError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(2)

    if as_json:
        click.echo(json.dumps({**entry.to_dict(), "was_new": was_new, "cost_usd": 0.0}, indent=2))
        return
    if was_new:
        print_success(f"Retained {entry.sha256[:12]} ({entry.byte_len} bytes) as {entry.trust_class}")
    else:
        console.print(f"[dim]Already retained ({entry.sha256[:12]}); nothing written.[/dim]")
    print_key_value("Origin", entry.origin_key)
    console.print(f'[dim]Next: deepr expert study "{profile.name}" --local[/dim]')


@expert.command(name="acquire")
@click.argument("name")
@click.option("--url", "urls", multiple=True, help="URL to fetch (repeatable)")
@click.option(
    "--from-file",
    type=click.Path(exists=True, dir_okay=False, path_type=str),
    default=None,
    help="File of URLs, one per line (# comments allowed)",
)
@click.option(
    "--trust-class",
    type=click.Choice(["primary", "secondary", "tertiary"]),
    default="secondary",
    help="Trust tier for everything fetched in this run",
)
@click.option("--json", "as_json", is_flag=True, help="Emit JSON")
def expert_acquire(name: str, urls: tuple[str, ...], from_file: str | None, trust_class: str, as_json: bool) -> None:
    """Fetch sources into NAME's corpus (network only, no model, $0).

    The expert does its own acquisition: it fetches, extracts, and retains,
    rather than waiting for someone to hand it files. Idempotent by content, so
    re-running after a source changes retains the new revision and re-running
    against an unchanged one writes nothing.

    One failed URL does not abort the run; failures are reported.

    EXAMPLES:

      deepr expert acquire "My Expert" --url https://example.org/spec
      deepr expert acquire "My Expert" --from-file sources.txt
    """
    profile = _load_profile(name)
    target_urls = list(urls)
    if from_file:
        for line in Path(from_file).read_text(encoding="utf-8").splitlines():
            candidate = line.strip()
            if candidate and not candidate.startswith("#"):
                target_urls.append(candidate)
    if not target_urls:
        click.echo("Error: pass --url (repeatable) or --from-file", err=True)
        sys.exit(2)

    from deepr.experts.corpus_acquire import acquire_sources, default_fetch_page

    store = CorpusStore(profile.name)
    if not as_json:
        print_header(f"Acquire: {profile.name}")
        console.print(f"[dim]{len(target_urls)} URL(s), network only, $0[/dim]\n")

    result = asyncio.run(
        acquire_sources(
            expert_name=profile.name,
            urls=target_urls,
            corpus=store,
            fetch_page=default_fetch_page(),
            trust_class=trust_class,
        )
    )

    if as_json:
        click.echo(json.dumps(result.to_dict(), indent=2, sort_keys=True))
        sys.exit(result.exit_code)

    _render_acquire_result(result, store, profile.name)
    sys.exit(result.exit_code)


def _render_acquire_result(result: Any, store: CorpusStore, expert_name: str) -> None:
    for source in result.sources:
        if source.status == "retained":
            console.print(f"  [green]retained[/green]  {source.byte_len:>7,}b  {source.url}")
        elif source.status == "unchanged":
            console.print(f"  [dim]unchanged[/dim]           {source.url}")
        else:
            console.print(f"  [red]{source.status}[/red]  {source.url}  [dim]{source.detail}[/dim]")

    console.print("")
    print_key_value("Retained", str(len(result.retained)))
    print_key_value("Distinct origins", str(store.stats().distinct_origins))
    for item in result.limitations:
        print_warning(item)
    console.print(f'[dim]Next: deepr expert study "{expert_name}" --local[/dim]')


@expert.command(name="corpus")
@click.argument("name")
@click.option("--json", "as_json", is_flag=True, help="Emit JSON")
def expert_corpus(name: str, as_json: bool) -> None:
    """Show what NAME has retained ($0, no model).

    Counts are structural. They say what is held, never whether it is any good.
    """
    profile = _load_profile(name)
    store = CorpusStore(profile.name)
    stats = store.stats()

    if as_json:
        click.echo(json.dumps({**stats.to_dict(), "cost_usd": 0.0}, indent=2, sort_keys=True))
        return

    print_header(f"Corpus: {profile.name}")
    print_key_value("Sources retained", str(stats.active_count))
    print_key_value("Distinct origins", str(stats.distinct_origins))
    print_key_value("Total bytes", f"{stats.total_bytes:,}")
    print_key_value("Trust mix", str(stats.trust_mix) if stats.trust_mix else "-")
    if not stats.active_count:
        console.print("\n[yellow]Nothing retained yet.[/yellow] A study pass over an empty corpus finds nothing.")
        console.print(f'[dim]Retain a source: deepr expert retain "{profile.name}" ./doc.md[/dim]')
        return
    if stats.distinct_origins < 2:
        print_warning(
            "Single origin: agreement within one publisher is not corroboration, "
            "and the contention lens will have nothing independent to compare."
        )
    console.print("\n[bold]Origins[/bold]")
    for origin in sorted(store.distinct_origins()):
        count = len(store.entries_for_origin(origin))
        console.print(f"  {origin}  ({count} source(s))")


@expert.command(name="study")
@click.argument("name")
@click.option(
    "--lens", "lenses", multiple=True, help=f"Lens to run (repeatable). Default: {', '.join(DEFAULT_LENS_KEYS)}"
)
@click.option("--all-lenses", is_flag=True, help="Run every available lens")
@click.option("--local", is_flag=True, help="Use local Ollama ($0, default)")
@click.option("--plan", default=None, help="Prepaid plan backend id (e.g. claude)")
@click.option("--plan-model", default=None, help="Model for the plan backend")
@click.option("--model", default=None, help="Explicit local model")
@click.option(
    "--max-corpus-chars",
    default=400_000,
    show_default=True,
    help="Corpus budget per lens. Sources are whole; the run reports what it skipped.",
)
@click.option("--out", type=click.Path(dir_okay=False, path_type=str), default=None, help="Write the study JSON here")
@click.option("--notebook", "write_notebook", is_flag=True, help="Also render the notebook")
@click.option(
    "--keep-warm",
    is_flag=True,
    help="Leave the local model resident after the run (default: release VRAM)",
)
@click.option("--json", "as_json", is_flag=True, help="Emit the study JSON to stdout")
def expert_study(
    name: str,
    lenses: tuple[str, ...],
    all_lenses: bool,
    local: bool,
    plan: str | None,
    plan_model: str | None,
    model: str | None,
    max_corpus_chars: int,
    out: str | None,
    write_notebook: bool,
    keep_warm: bool,
    as_json: bool,
) -> None:
    """Read NAME's retained corpus through several lenses ($0 local or plan).

    Each lens asks a different question of the same material and runs
    independently; they are never asked to agree, and disagreement between them
    is a result rather than an error.

    Findings are proposed, not written. Nothing here alters the belief store.
    There is no --api option: a study pass is many calls, and paid dispatch is
    frozen.

    EXAMPLES:

      deepr expert study "My Expert" --local
      deepr expert study "My Expert" --lens failure --lens adversarial --local
      deepr expert study "My Expert" --plan claude --notebook
    """
    profile = _load_profile(name)
    lens_keys: list[str] | None = list(LENSES) if all_lenses else (list(lenses) or None)
    resolved, store, backend = _prepare_study(
        profile=profile, lens_keys=lens_keys, local=local, plan=plan, plan_model=plan_model, model=model
    )

    if not as_json:
        print_header(f"Study: {profile.name}")
        print_key_value("Capacity", backend.cost_note)
        print_key_value("Lenses", ", ".join(lens.key for lens in resolved))
        console.print("[dim]Independent passes; lenses are not asked to agree.[/dim]\n")
        if backend.capacity_source.startswith("local:"):
            _report_vram_headroom(quiet=as_json)

    async def _run() -> Any:
        local_model = (
            backend.capacity_source.removeprefix("local:") if backend.capacity_source.startswith("local:") else ""
        )
        try:
            if local_model:
                await _warn_if_cpu_bound(local_model, quiet=as_json)
            return await run_study(
                expert_name=profile.name,
                corpus=store,
                completion=backend.completion,
                lens_keys=[lens.key for lens in resolved],
                max_corpus_chars=max_corpus_chars,
                capacity_source=backend.capacity_source,
            )
        finally:
            # Pin weights during the run, release at the end. Leaving a large
            # model resident for the rest of the keep-alive window blocks every
            # other GPU user on the machine for work that is already finished.
            if local_model and not keep_warm:
                from deepr.backends.local import release_local_model

                await release_local_model(local_model)

    result = asyncio.run(_run())

    payload = result.to_dict()
    if out:
        Path(out).write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    if write_notebook:
        _write_notebook(profile, result, store, quiet=as_json)

    if as_json:
        click.echo(json.dumps(payload, indent=2, sort_keys=True))
        sys.exit(result.exit_code)

    _render_study_summary(result)
    sys.exit(result.exit_code)


def _prepare_study(
    *,
    profile: Any,
    lens_keys: list[str] | None,
    local: bool,
    plan: str | None,
    plan_model: str | None,
    model: str | None,
) -> tuple[list[Any], CorpusStore, Any]:
    """Resolve lenses, corpus, and capacity, or exit before any model call."""
    try:
        resolved = resolve_lenses(lens_keys)
    except ValueError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(2)

    store = CorpusStore(profile.name)
    if not store.active_entries():
        click.echo(
            f"Error: {profile.name} has no retained corpus. Acquire or retain sources first: "
            f'deepr expert acquire "{profile.name}" --url https://...',
            err=True,
        )
        sys.exit(2)

    try:
        backend = build_study_backend(profile=profile, local=local, plan=plan, plan_model=plan_model, model=model)
    except StudyBackendError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(2)

    return resolved, store, backend


def _report_vram_headroom(*, quiet: bool) -> None:
    """Say what is holding VRAM, so a downgrade is a choice rather than a surprise.

    A study pass that quietly picks a weaker model because a browser and a screen
    recorder hold 8 GB is making a decision the operator would likely overrule if
    they could see it.
    """
    if quiet:
        return
    from deepr.backends.vram_report import collect_vram_report, describe_headroom

    report = collect_vram_report()
    # Roughly what a capable 24B model needs at 32K context.
    lines = describe_headroom(report, needed_bytes=21_500_000_000)
    for line in lines:
        console.print(f"[dim]{line}[/dim]")
    if lines:
        console.print("")


async def _warn_if_cpu_bound(model: str, *, quiet: bool) -> None:
    """Say when a model spilled to CPU instead of appearing to hang.

    A model whose weights plus context exceed VRAM runs on CPU, where a study
    pass takes hours instead of minutes. The run is still $0 and still correct;
    it just looks like a hang, and the operator deserves to know which it is.
    """
    from deepr.backends.local import local_model_runs_on_gpu

    on_gpu, detail = await local_model_runs_on_gpu(model)
    if not on_gpu and detail and not quiet:
        print_warning(detail)


def _render_study_summary(result: Any) -> None:
    for outcome in result.outcomes:
        marker = "[green]ok[/green]" if outcome.status == "ok" else f"[red]{outcome.status}[/red]"
        detail = f" - {outcome.detail}" if outcome.detail else ""
        console.print(
            f"  {outcome.lens:16s} {outcome.elapsed_s:7.1f}s  {marker}  {len(outcome.findings)} finding(s){detail}"
        )

    console.print("")
    print_key_value("Findings", str(len(result.findings)))
    print_key_value("Anchored in corpus", str(len(result.grounded_findings)))
    print_key_value("Cost", f"${result.cost_usd:.2f}")
    if result.limitations:
        console.print("\n[bold yellow]Limitations[/bold yellow]")
        for item in result.limitations:
            console.print(f"  - {item}")
    console.print(
        "\n[dim]Findings are proposed from sources, not verified conclusions. "
        "Nothing was written to the belief store.[/dim]"
    )


def _write_notebook(profile: Any, result: Any, store: CorpusStore, *, quiet: bool) -> None:
    from deepr.experts.paths import canonical_expert_dir

    path = canonical_expert_dir(profile.name) / "notebook.md"
    if path.exists() and NOTEBOOK_MARKER not in path.read_text(encoding="utf-8", errors="replace"):
        # A hand-edited file is not a derived view; refuse rather than clobber it.
        if not quiet:
            print_warning(f"{path} exists and is not a generated notebook; not overwriting.")
        return
    text = build_notebook(
        result,
        expert_name=profile.name,
        domain=getattr(profile, "domain", "") or "",
        purpose=getattr(profile, "description", "") or "",
        corpus_entries=store.active_entries(),
    )
    path.write_text(text, encoding="utf-8")
    if not quiet:
        print_success(f"Notebook: {path}")


@expert.command(name="notebook")
@click.argument("name")
@click.option(
    "--from-study",
    type=click.Path(exists=True, dir_okay=False, path_type=str),
    default=None,
    help="Render a saved study JSON",
)
@click.option(
    "--out", type=click.Path(dir_okay=False, path_type=str), default=None, help="Write here instead of the expert dir"
)
def expert_notebook(name: str, from_study: str | None, out: str | None) -> None:
    """Render NAME's latest study as a notebook ($0, no model).

    A derived view: the retained corpus and the study record are canonical, and
    this file is safe to delete.
    """
    profile = _load_profile(name)
    from deepr.experts.paths import canonical_expert_dir
    from deepr.experts.study_contracts import LensOutcome, StudyFinding, StudyResult

    study_path = Path(from_study) if from_study else canonical_expert_dir(profile.name) / "study.json"
    if not study_path.exists():
        click.echo(
            f'Error: no study found at {study_path}. Run: deepr expert study "{profile.name}" --local --out {study_path}',
            err=True,
        )
        sys.exit(2)

    payload = json.loads(study_path.read_text(encoding="utf-8"))
    result = StudyResult(expert_name=payload.get("expert", profile.name))
    result.limitations = list(payload.get("limitations") or [])
    for raw in payload.get("outcomes") or []:
        findings = [
            StudyFinding(
                lens=f.get("lens", ""),
                axis=f.get("axis", ""),
                kind=f.get("kind", ""),
                title=f.get("title", ""),
                payload=f.get("payload") or {},
                anchors=f.get("anchors") or [],
                grounded_anchor_count=int(f.get("grounded_anchor_count", 0) or 0),
                ungrounded_anchor_count=int(f.get("ungrounded_anchor_count", 0) or 0),
                corpus_shas=f.get("corpus_shas") or [],
            )
            for f in (raw.get("findings") or [])
        ]
        result.outcomes.append(
            LensOutcome(
                lens=raw.get("lens", ""),
                axis=raw.get("axis", ""),
                status=raw.get("status", "ok"),
                findings=findings,
                detail=raw.get("detail", ""),
            )
        )

    store = CorpusStore(profile.name)
    text = build_notebook(
        result,
        expert_name=profile.name,
        domain=getattr(profile, "domain", "") or "",
        purpose=getattr(profile, "description", "") or "",
        corpus_entries=store.active_entries(),
    )
    target = Path(out) if out else canonical_expert_dir(profile.name) / "notebook.md"
    target.write_text(text, encoding="utf-8")
    print_success(f"Notebook: {target}")
