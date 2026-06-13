"""Characterization + behavior tests for the expert maintenance commands.

These guard the decomposition of experts.py: the sync/absorb commands moved to
deepr/cli/commands/semantic/expert_maintenance.py must stay registered on the
`expert` group with the same options, and gain --local for $0 local execution.
"""

from __future__ import annotations

from click.testing import CliRunner

from deepr.cli.commands.semantic.experts import expert


class TestRegistration:
    def test_sync_registered_with_options(self):
        assert "sync" in expert.commands
        opts = {p.name for p in expert.commands["sync"].params}
        assert {"name", "budget", "dry_run"} <= opts

    def test_absorb_registered_with_options(self):
        assert "absorb" in expert.commands
        opts = {p.name for p in expert.commands["absorb"].params}
        assert {"name", "report_id", "min_confidence", "dry_run"} <= opts

    def test_sync_has_local_and_api_flags(self):
        opts = {p.name for p in expert.commands["sync"].params}
        assert {"local", "api"} <= opts

    def test_absorb_has_local_and_api_flags(self):
        opts = {p.name for p in expert.commands["absorb"].params}
        assert {"local", "api"} <= opts


class TestBackendFlagGuard:
    """--local and --api are mutually exclusive and checked before any store work."""

    def test_sync_rejects_local_and_api_together(self):
        r = CliRunner().invoke(expert, ["sync", "Whoever", "--local", "--api"])
        assert r.exit_code == 2
        assert "not both" in r.output

    def test_absorb_rejects_local_and_api_together(self):
        r = CliRunner().invoke(expert, ["absorb", "Whoever", "job123", "--local", "--api"])
        assert r.exit_code == 2
        assert "not both" in r.output
