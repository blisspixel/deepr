"""Explicit editorial curation for the expert hub roster."""

from __future__ import annotations

import click

from deepr.cli.colors import print_header, print_success
from deepr.cli.commands.semantic.experts import expert
from deepr.experts.profile_store import ExpertStore


@expert.group(name="roster")
def roster() -> None:
    """Curate which experts lead the flagship roster."""


def _set_roster_tier(names: tuple[str, ...], tier: str) -> None:
    store = ExpertStore()
    profiles = []
    for name in names:
        profile = store.load(name)
        if profile is None:
            raise click.ClickException(f"Expert not found: {name}")
        profiles.append(profile)
    for profile in profiles:
        profile.roster_tier = tier
        store.save(profile)
    label = "flagship" if tier == "flagship" else "standard"
    print_success(f"Set {len(profiles)} expert(s) to the {label} roster tier.")


@roster.command("feature")
@click.argument("names", nargs=-1, required=True)
def feature(names: tuple[str, ...]) -> None:
    """Place one or more experts in the flagship roster."""
    _set_roster_tier(names, "flagship")


@roster.command("unfeature")
@click.argument("names", nargs=-1, required=True)
def unfeature(names: tuple[str, ...]) -> None:
    """Return one or more experts to the standard roster."""
    _set_roster_tier(names, "standard")


@roster.command("list")
def list_roster() -> None:
    """List explicit roster tiers without making a model call."""
    print_header("Expert Roster")
    profiles = ExpertStore(create=False).list_all()
    featured = sorted(profile.name for profile in profiles if profile.roster_tier == "flagship")
    click.echo(f"\nFlagship experts: {len(featured)}")
    for name in featured:
        click.echo(f"  {name}")
    click.echo(f"Standard experts: {len(profiles) - len(featured)}")
