"""Local-only expert profile creation for the expert CLI."""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

import click

from deepr.backends.local import default_local_model
from deepr.experts.profile import ExpertProfile, ExpertStore, get_expert_system_message
from deepr.utils.security import sanitize_name


def make_local_expert_profile(
    *,
    name: str,
    files: tuple[str, ...],
    description: str | None,
    local_model: str | None,
    learning_options_used: bool,
) -> ExpertProfile | None:
    """Create a local-only expert profile and print the next maintenance steps."""
    if learning_options_used:
        click.echo("Error: --local creates a $0 profile only; learning options are API-backed today.")
        click.echo(f'Do this instead: deepr expert subscribe "{name}" "{description or name}"')
        click.echo(f'Then run: deepr expert sync "{name}" --local --fresh-context -y')
        return None

    click.echo(f"Creating local expert: {name}...")
    profile = create_local_expert_profile(
        name=name,
        files=files,
        description=description,
        local_model=local_model,
    )
    click.echo(f"\nLocal expert created: {profile.name}")
    click.echo(f"Provider: {profile.provider}")
    click.echo(f"Model: {profile.model}")
    click.echo(f"Documents: {profile.total_documents}")
    click.echo("\nNext:")
    click.echo(f'  deepr expert subscribe "{profile.name}" "{description or profile.name}"')
    click.echo(f'  deepr expert sync "{profile.name}" --local --fresh-context -y')
    return profile


def create_local_expert_profile(
    *,
    name: str,
    files: tuple[str, ...],
    description: str | None,
    local_model: str | None,
) -> ExpertProfile:
    """Create a provider-free expert profile and copy optional seed documents."""
    now = datetime.now(UTC)
    store = ExpertStore()
    model = local_model or default_local_model() or "ollama"

    profile = ExpertProfile(
        name=name,
        vector_store_id=f"local-only:{sanitize_name(name).lower()}",
        description=description,
        domain=description or name,
        source_files=[],
        total_documents=0,
        knowledge_cutoff_date=now,
        last_knowledge_refresh=now,
        system_message=get_expert_system_message(knowledge_cutoff_date=now, domain_velocity="medium"),
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
