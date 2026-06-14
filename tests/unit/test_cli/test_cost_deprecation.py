"""Phase Q1.2: `cost` is a deprecated, hidden alias; `costs estimate` is canonical.

Pins the deprecation contract so a refactor cannot silently drop the warning or
the back-compat alias before the deprecation window elapses.
"""

import pytest
from click.testing import CliRunner

from deepr.cli.main import cli


@pytest.fixture
def runner():
    return CliRunner()


def test_costs_estimate_is_the_canonical_home(runner):
    result = runner.invoke(cli, ["costs", "estimate", "What are AI trends?"])
    assert result.exit_code == 0
    assert "Cost Estimate" in result.output
    # The new home does NOT emit a deprecation warning.
    assert "deprecated" not in result.output.lower()


def test_cost_estimate_still_works_but_warns(runner):
    result = runner.invoke(cli, ["cost", "estimate", "What are AI trends?"])
    assert result.exit_code == 0
    # Back-compat: still produces the estimate.
    assert "Cost Estimate" in result.output
    # ...and steers the user to the replacement.
    out = result.output.lower()
    assert "deprecated" in out
    assert "costs estimate" in out


def test_cost_group_hidden_from_top_level_help(runner):
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    # `costs` is listed; the deprecated `cost` alias is hidden.
    assert "costs" in result.output
    lines = [line for line in result.output.splitlines() if line.strip().startswith("cost ")]
    assert lines == [], f"deprecated `cost` should be hidden, found: {lines}"
