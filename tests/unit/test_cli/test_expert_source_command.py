"""`deepr expert source` must honor acquire exit codes."""

from __future__ import annotations

from types import SimpleNamespace

from click.testing import CliRunner

from deepr.cli.commands.semantic.experts import expert
from deepr.experts.corpus_acquire import AcquiredSource, AcquireResult


def _patch_source(tmp_path, monkeypatch, report: AcquireResult):
    from deepr.experts import paths

    home = tmp_path / "experts"
    monkeypatch.setattr(paths, "canonical_expert_dir", lambda name: home / name)

    class FakeProfile:
        name = "Subject"

    class FakeStore:
        def load(self, name):
            return FakeProfile() if name == "Subject" else None

    class FakeCorpus:
        def __init__(self, *_args, **_kwargs):
            pass

        def active_entries(self):
            return []

    monkeypatch.setattr("deepr.experts.profile.ExpertStore", FakeStore)
    monkeypatch.setattr("deepr.experts.corpus_store.CorpusStore", FakeCorpus)
    monkeypatch.setattr(
        "deepr.cli.commands.semantic.expert_source.build_study_backend",
        lambda **kwargs: SimpleNamespace(cost_note="$0"),
    )

    async def fake_build_plan(*_args, **_kwargs):
        plan = SimpleNamespace(queries=[SimpleNamespace(arm="descriptive", text="q")])
        return plan, "test"

    async def fake_search(*_args, **_kwargs):
        return SimpleNamespace(
            hits=[SimpleNamespace(url="https://example.org/a")],
            distinct_hosts={"example.org"},
            stopped_early="",
        )

    async def fake_acquire(**_kwargs):
        return report

    monkeypatch.setattr("deepr.cli.commands.semantic.expert_source._build_plan", fake_build_plan)
    monkeypatch.setattr("deepr.experts.corpus_search.run_search_plan", fake_search)
    monkeypatch.setattr("deepr.experts.corpus_acquire.acquire_sources", fake_acquire)
    monkeypatch.setattr("deepr.experts.corpus_acquire.default_fetch_page", lambda: None)
    return home


class TestSourceHonorsAcquireExitCode:
    def test_nothing_usable_exits_2(self, tmp_path, monkeypatch):
        report = AcquireResult(expert_name="Subject")
        report.sources = [AcquiredSource(url="https://example.org/a", status="fetch_failed", detail="timeout")]
        _patch_source(tmp_path, monkeypatch, report)

        result = CliRunner().invoke(expert, ["source", "Subject", "topic", "--local"])
        assert result.exit_code == 2
        assert "nothing usable" in result.output
        assert "failed" in result.output

    def test_partial_acquire_exits_1(self, tmp_path, monkeypatch):
        report = AcquireResult(expert_name="Subject")
        report.sources = [
            AcquiredSource(url="https://example.org/a", status="retained", sha256="aa", origin_key="url:example.org"),
            AcquiredSource(url="https://example.org/b", status="fetch_failed", detail="404"),
        ]
        _patch_source(tmp_path, monkeypatch, report)

        result = CliRunner().invoke(expert, ["source", "Subject", "topic", "--local"])
        assert result.exit_code == 1
        assert "Partial acquire" in result.output
