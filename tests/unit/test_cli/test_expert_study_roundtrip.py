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
    monkeypatch.setattr(
        "deepr.cli.commands.semantic.expert_study.canonical_expert_dir",
        lambda name: tmp_path,
    )
    return SimpleNamespace(name="Round Trip Expert")


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
        path.write_text(json.dumps(_study().to_dict()), encoding="utf-8")

        loaded = _load_study_result(profile, None)

        assert loaded.expert_name == "Round Trip Expert"
        assert [f.title for f in loaded.findings] == ["Sources disagree on transfer rate"]

    def test_grounding_survives_the_round_trip(self, profile):
        """A finding that loses its anchors on reload would brief as unverified."""
        canonical_study_path(profile.name).write_text(json.dumps(_study().to_dict()), encoding="utf-8")

        finding = _load_study_result(profile, None).findings[0]

        assert finding.is_grounded
        assert finding.corpus_shas == ["sha-a", "sha-b"]

    def test_limitations_survive_the_round_trip(self, profile):
        """Limitations are what stop a partial study reading as a complete one."""
        canonical_study_path(profile.name).write_text(json.dumps(_study().to_dict()), encoding="utf-8")

        assert _load_study_result(profile, None).limitations == ["one source was skipped"]

    def test_missing_study_exits_with_the_command_that_makes_one(self, profile, capsys):
        with pytest.raises(SystemExit) as exit_info:
            _load_study_result(profile, None)

        assert exit_info.value.code == 2
        assert 'deepr expert study "Round Trip Expert"' in capsys.readouterr().err

    def test_explicit_path_overrides_the_canonical_one(self, profile, tmp_path):
        elsewhere = tmp_path / "other.json"
        elsewhere.write_text(json.dumps(_study().to_dict()), encoding="utf-8")

        assert _load_study_result(profile, str(elsewhere)).findings
