"""study writes where brief reads.

These two commands are only useful as a chain, and the chain was broken: study
persisted nothing unless given --out, while brief defaulted to reading a
canonical path that therefore never existed. Unit tests on each command passed
throughout, because neither one is wrong on its own.
"""

import json
from types import SimpleNamespace

import pytest

from deepr.cli.commands.semantic.expert_study import (
    _load_study_result,
    canonical_study_path,
)
from deepr.experts.study_contracts import LensOutcome, StudyFinding, StudyResult


@pytest.fixture
def profile(tmp_path, monkeypatch):
    """An expert whose canonical directory is disposable."""
    from deepr.experts import paths

    monkeypatch.setattr(paths, "canonical_expert_dir", lambda name: tmp_path)
    return SimpleNamespace(name="Round Trip Expert")


def _write(path, payload: str) -> None:
    """Write where a command would, creating the directory a command would.

    The canonical paths are nested now (`noticed/current.json`), so a test that
    writes one has to make the directory the same way the production writers
    do.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")


def _study() -> StudyResult:
    result = StudyResult(expert_name="Round Trip Expert")
    result.limitations = ["one source was skipped"]
    result.outcomes = [
        LensOutcome(
            lens="contention",
            axis="interrogation",
            status="ok",
            findings=[
                StudyFinding(
                    lens="contention",
                    axis="interrogation",
                    kind="disputes",
                    title="Sources disagree on transfer rate",
                    payload={"claim": "c", "counter": "d"},
                    grounded_anchor_count=2,
                    corpus_shas=["sha-a", "sha-b"],
                )
            ],
        )
    ]
    return result


class TestStudyRoundTrip:
    def test_a_study_written_to_the_canonical_path_is_the_one_brief_loads(self, profile):
        path = canonical_study_path(profile.name)
        _write(path, json.dumps(_study().to_dict()))

        loaded = _load_study_result(profile, None)

        assert loaded.expert_name == "Round Trip Expert"
        assert [f.title for f in loaded.findings] == ["Sources disagree on transfer rate"]

    def test_grounding_survives_the_round_trip(self, profile):
        """A finding that loses its anchors on reload would brief as unverified."""
        _write(canonical_study_path(profile.name), json.dumps(_study().to_dict()))

        finding = _load_study_result(profile, None).findings[0]

        assert finding.is_grounded
        assert finding.corpus_shas == ["sha-a", "sha-b"]

    def test_limitations_survive_the_round_trip(self, profile):
        """Limitations are what stop a partial study reading as a complete one."""
        _write(canonical_study_path(profile.name), json.dumps(_study().to_dict()))

        assert _load_study_result(profile, None).limitations == ["one source was skipped"]

    def test_missing_study_exits_with_the_command_that_makes_one(self, profile, capsys):
        with pytest.raises(SystemExit) as exit_info:
            _load_study_result(profile, None)

        assert exit_info.value.code == 2
        assert 'deepr expert study "Round Trip Expert"' in capsys.readouterr().err

    def test_explicit_path_overrides_the_canonical_one(self, profile, tmp_path):
        elsewhere = tmp_path / "other.json"
        _write(elsewhere, json.dumps(_study().to_dict()))

        assert _load_study_result(profile, str(elsewhere)).findings


class TestBriefRefusesUngroundedStudy:
    def test_brief_does_not_spend_on_an_ungrounded_study(self, tmp_path, monkeypatch):
        """Presence is not validity: a study with findings that cite nothing."""
        from click.testing import CliRunner

        from deepr.cli.commands.semantic.experts import expert
        from deepr.experts import paths

        home = tmp_path / "experts"
        monkeypatch.setattr(paths, "canonical_expert_dir", lambda name: home / name)

        class FakeProfile:
            name = "Subject"

        class FakeStore:
            def load(self, name):
                return FakeProfile() if name == "Subject" else None

        monkeypatch.setattr("deepr.experts.profile.ExpertStore", FakeStore)

        called: list[object] = []
        monkeypatch.setattr(
            "deepr.cli.commands.semantic.expert_study.build_study_backend",
            lambda **kwargs: called.append(kwargs) or (_ for _ in ()).throw(AssertionError("backend built")),
        )

        ungrounded = StudyResult(expert_name="Subject")
        ungrounded.outcomes = [
            LensOutcome(
                lens="contention",
                axis="interrogation",
                status="ok",
                findings=[
                    StudyFinding(
                        lens="contention",
                        axis="interrogation",
                        kind="disputes",
                        title="Ungrounded",
                        payload={"claim": "c"},
                        grounded_anchor_count=0,
                        corpus_shas=[],
                    )
                ],
            )
        ]
        path = home / "Subject" / "noticed" / "current.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(ungrounded.to_dict()), encoding="utf-8")

        result = CliRunner().invoke(expert, ["brief", "Subject"])
        assert result.exit_code == 2
        assert "no grounded findings" in result.output
        assert called == []


class TestBriefRefusesEmptyResult:
    def test_empty_brief_does_not_write_or_close_the_ledger(self, tmp_path, monkeypatch):
        """A timed-out synthesis must not erase a previous consultable brief."""
        from click.testing import CliRunner

        from deepr.cli.commands.semantic.experts import expert
        from deepr.experts import paths
        from deepr.experts.brief_contracts import ExpertBrief

        home = tmp_path / "experts"
        monkeypatch.setattr(paths, "canonical_expert_dir", lambda name: home / name)

        class FakeProfile:
            name = "Subject"
            domain = "d"

        class FakeStore:
            def load(self, name):
                return FakeProfile() if name == "Subject" else None

        monkeypatch.setattr("deepr.experts.profile.ExpertStore", FakeStore)

        existing = home / "Subject" / "hold" / "current.json"
        existing.parent.mkdir(parents=True)
        existing.write_text(json.dumps({"positions": [{"question": "Q", "stance": "s"}]}), encoding="utf-8")
        history = home / "Subject" / "hold" / "history.json"
        history.write_text(
            json.dumps(
                {
                    "expert": "Subject",
                    "versions": [
                        {
                            "thread_id": "t1",
                            "version_id": "v1",
                            "question": "Q",
                            "stance": "s",
                            "recorded_at": "2026-01-01T00:00:00+00:00",
                            "superseded_at": "9999-12-31T23:59:59.999999+00:00",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        _write(home / "Subject" / "noticed" / "current.json", json.dumps(_study().to_dict()))

        async def empty_brief(**_kwargs):
            return ExpertBrief(expert_name="Subject", limitations=["synthesis timed out"])

        monkeypatch.setattr("deepr.experts.brief.build_brief", empty_brief)

        class FakeBackend:
            capacity_source = "local:x"
            model = "x"
            cost_note = "$0"
            completion = staticmethod(lambda prompt: "")

        monkeypatch.setattr(
            "deepr.cli.commands.semantic.expert_study.build_study_backend",
            lambda **kwargs: FakeBackend(),
        )
        monkeypatch.setattr(
            "deepr.cli.commands.semantic.expert_study.CorpusStore",
            lambda name: type("C", (), {"active_entries": staticmethod(lambda: [])})(),
        )

        result = CliRunner().invoke(expert, ["brief", "Subject", "--json"])
        assert result.exit_code == 2
        assert "holds no positions" in result.output
        assert json.loads(existing.read_text(encoding="utf-8"))["positions"][0]["question"] == "Q"
        assert json.loads(history.read_text(encoding="utf-8"))["versions"][0]["thread_id"] == "t1"
