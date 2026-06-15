"""CLI tests for `deepr eval continuity` error paths.

Regression for a live-hunt finding (2026-06-14): on an expert that exists but
has no beliefs yet, continuity wrongly said "Create or learn an expert first"
(implying it didn't exist), and probing a missing name created an empty belief
directory as a side effect.
"""

import pytest
from click.testing import CliRunner

from deepr.cli.main import cli


@pytest.fixture
def runner():
    return CliRunner()


def test_continuity_missing_expert_says_not_found_and_creates_no_dir(runner):
    from deepr.config import experts_root

    result = runner.invoke(cli, ["eval", "continuity", "Ghost Expert XYZ"])
    assert result.exit_code != 0
    assert "not found" in result.output.lower()
    # The existence check must run before BeliefStore, so no dir is created.
    assert not (experts_root() / "Ghost Expert XYZ").exists()
    assert not (experts_root() / "ghost_expert_xyz").exists()


def test_continuity_expert_without_beliefs_points_to_synthesis(runner):
    from deepr.experts.profile import ExpertProfile, ExpertStore

    ExpertStore().save(ExpertProfile(name="Empty Probe", vector_store_id="vs-x", description="x", domain="ai"))

    result = runner.invoke(cli, ["eval", "continuity", "Empty Probe"])
    assert result.exit_code != 0
    out = result.output.lower()
    assert "no beliefs yet" in out
    assert "synthesize" in out  # actionable next step, not "create an expert"
