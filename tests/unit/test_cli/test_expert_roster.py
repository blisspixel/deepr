"""Explicit expert-roster curation is local, reversible, and all-or-none."""

from __future__ import annotations

from click.testing import CliRunner

from deepr.cli.main import cli
from deepr.experts.profile import ExpertProfile
from deepr.experts.profile_store import ExpertStore


def _store_profiles(*names: str) -> ExpertStore:
    store = ExpertStore()
    for name in names:
        store.save(ExpertProfile(name=name, vector_store_id=f"local-{name}"))
    return store


def test_feature_and_unfeature_are_explicit_reversible_metadata_changes() -> None:
    store = _store_profiles("Evidence", "Systems")
    runner = CliRunner()

    featured = runner.invoke(cli, ["expert", "roster", "feature", "Evidence", "Systems"])
    assert featured.exit_code == 0
    assert store.load("Evidence").roster_tier == "flagship"
    assert store.load("Systems").roster_tier == "flagship"

    unfeatured = runner.invoke(cli, ["expert", "roster", "unfeature", "Systems"])
    assert unfeatured.exit_code == 0
    assert store.load("Evidence").roster_tier == "flagship"
    assert store.load("Systems").roster_tier == "standard"


def test_missing_name_prevents_every_requested_change() -> None:
    store = _store_profiles("Evidence")

    result = CliRunner().invoke(cli, ["expert", "roster", "feature", "Evidence", "Missing"])

    assert result.exit_code == 1
    assert "Expert not found: Missing" in result.output
    assert store.load("Evidence").roster_tier == "standard"


def test_roster_list_reports_explicit_tiers() -> None:
    store = _store_profiles("Evidence", "Systems")
    evidence = store.load("Evidence")
    evidence.roster_tier = "flagship"
    store.save(evidence)

    result = CliRunner().invoke(cli, ["expert", "roster", "list"])

    assert result.exit_code == 0
    assert "Flagship experts: 1" in result.output
    assert "Evidence" in result.output
    assert "Standard experts: 1" in result.output
