"""Local-only expert profile creation for the expert CLI."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import click

from deepr.backends.local import default_local_model
from deepr.experts.profile import ExpertProfile, ExpertStore, get_expert_system_message
from deepr.utils.security import sanitize_name


def local_formation_options(command: Any) -> Any:
    """The shared explicit operator bounds for local creation and build."""
    command = click.option(
        "--max-minutes",
        type=click.IntRange(1, 360),
        default=45,
        show_default=True,
        help="Owned-local formation time limit; completed chunks survive retry",
    )(command)
    return click.option(
        "--max-corpus-chars",
        type=click.IntRange(1, 120_000),
        default=120_000,
        show_default=True,
        help="Explicit local formation corpus budget per lens",
    )(command)


def local_creation_options(command: Any) -> Any:
    command = local_formation_options(command)
    command = click.option("--local", is_flag=True, help="Create and research a local expert at $0 API cost")(command)
    command = click.option("--profile-only", is_flag=True, help="With --local, create only an untrained profile")(
        command
    )
    return click.option("--local-model", default=None, help="Installed local model for formation and maintenance")(
        command
    )


def make_local_expert_profile(
    *,
    name: str,
    files: tuple[str, ...],
    description: str | None,
    local_model: str | None,
    learning_options_used: bool,
    profile_only: bool = False,
    discover: bool = True,
    max_minutes: int = 45,
    max_corpus_chars: int = 120_000,
) -> ExpertProfile | None:
    """Create a local profile and form its research foundation by default."""
    if learning_options_used:
        raise click.ClickException(
            "Local formation uses bounded $0 research; metered curriculum budget/topic options do not apply."
        )
    from deepr.experts.formation import FormationLimits

    limits = FormationLimits(max_elapsed_seconds=max_minutes * 60, max_corpus_chars=max_corpus_chars)
    limits.validate()

    click.echo(f"Creating local expert: {name}...")
    try:
        profile = create_local_expert_profile(
            name=name,
            files=files,
            description=description,
            local_model=local_model,
        )
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"\nLocal profile created: {profile.name}")
    click.echo(f"Provider: {profile.provider}")
    click.echo(f"Model: {profile.model}")
    click.echo(f"Documents: {profile.total_documents}")
    if profile_only:
        click.echo(f'Untrained profile. Build its knowledge with: deepr expert build "{profile.name}"')
        return profile
    from deepr.cli.commands.semantic.expert_build import build_local_expert

    try:
        build_local_expert(
            profile, model=local_model, discover=discover, limits=limits, fresh_default=local_model is None
        )
    except (OSError, ValueError) as exc:
        raise click.ClickException(
            f'{exc}. Profile retained; resume with: deepr expert build "{profile.name}"'
        ) from exc
    return profile


def create_local_expert_profile(
    *,
    name: str,
    files: tuple[str, ...],
    description: str | None,
    local_model: str | None,
) -> ExpertProfile:
    """Create a provider-free expert profile and copy optional seed documents."""
    store = ExpertStore()
    if store.load(name) is not None:
        raise ValueError(f"expert already exists: {name}")
    model = local_model or default_local_model() or "ollama"

    profile = ExpertProfile(
        name=name,
        vector_store_id=f"local-only:{sanitize_name(name).lower()}",
        description=description,
        domain=description or name,
        source_files=[],
        total_documents=0,
        # Profile creation is not learning. Until documents or retrieved
        # sources have passed the absorb/compiler path, freshness is honestly
        # incomplete rather than "0 days old fresh".
        knowledge_cutoff_date=None,
        last_knowledge_refresh=None,
        system_message=get_expert_system_message(knowledge_cutoff_date=None, domain_velocity="medium"),
        provider="local",
        model=model,
        monthly_learning_budget=0.0,
    )
    store.save(profile)

    copied_files = _copy_seed_documents(store, name, files)
    if copied_files:
        profile.source_files = copied_files
        profile.total_documents = len(copied_files)
        store.save(profile)

    return profile


def _copy_seed_documents(store: ExpertStore, name: str, files: tuple[str, ...]) -> list[str]:
    copied_files: list[str] = []
    if not files:
        return copied_files

    docs_dir = store.get_documents_dir(name)
    docs_dir.mkdir(parents=True, exist_ok=True)
    for source in files:
        src_path = Path(source)
        dest_path = _unique_local_document_path(docs_dir, src_path)
        if src_path.resolve() != dest_path.resolve():
            shutil.copy2(src_path, dest_path)
        copied_files.append(str(dest_path))
    return copied_files


def _unique_local_document_path(docs_dir: Path, src_path: Path) -> Path:
    dest_path = docs_dir / src_path.name
    if not dest_path.exists() or src_path.resolve() == dest_path.resolve():
        return dest_path

    suffix = src_path.suffix
    stem = src_path.stem
    counter = 2
    while True:
        candidate = docs_dir / f"{stem}-{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1
