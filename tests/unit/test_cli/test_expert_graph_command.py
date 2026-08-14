"""`deepr expert graph` must not persist a pile of nodes as a formed graph."""

from __future__ import annotations

import json

from click.testing import CliRunner

from deepr.cli.commands.semantic.experts import expert
from deepr.experts.study_contracts import LensOutcome, StudyFinding, StudyResult


def _study_result() -> StudyResult:
    result = StudyResult(expert_name="Subject")
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
                    title="Sources disagree",
                    payload={"claim": "c"},
                    grounded_anchor_count=2,
                    corpus_shas=["sha-a", "sha-b"],
                    finding_id="contention-1",
                )
            ],
        )
    ]
    return result


def _patch_home(tmp_path, monkeypatch):
    from deepr.experts import paths

    home = tmp_path / "experts"

    def locate(name: str):
        return home / name

    monkeypatch.setattr(paths, "canonical_expert_dir", locate)
    monkeypatch.setattr("deepr.cli.commands.semantic.expert_graph.canonical_expert_dir", locate)

    class FakeProfile:
        name = "Subject"

    class FakeStore:
        def load(self, name):
            return FakeProfile() if name == "Subject" else None

    monkeypatch.setattr("deepr.experts.profile.ExpertStore", FakeStore)
    return home / "Subject"


class TestGraphRefusesToWriteAFailedArtifact:
    def test_no_brief_does_not_write(self, tmp_path, monkeypatch):
        directory = _patch_home(tmp_path, monkeypatch)
        study_path = directory / "noticed" / "current.json"
        study_path.parent.mkdir(parents=True)
        study_path.write_text(json.dumps(_study_result().to_dict()), encoding="utf-8")

        result = CliRunner().invoke(expert, ["graph", "Subject"])
        assert result.exit_code == 2
        assert "cannot form an evidence graph" in result.output
        assert not (directory / "graph" / "evidence.json").exists()

    def test_unformed_graph_does_not_overwrite_a_formed_one(self, tmp_path, monkeypatch):
        directory = _patch_home(tmp_path, monkeypatch)
        study = _study_result()
        (directory / "noticed").mkdir(parents=True)
        (directory / "noticed" / "current.json").write_text(json.dumps(study.to_dict()), encoding="utf-8")
        (directory / "hold").mkdir(parents=True)
        (directory / "hold" / "current.json").write_text(
            json.dumps(
                {
                    "positions": [
                        {
                            "question": "Does X hold?",
                            "stance": "it holds",
                            "reasoning": "r",
                            "would_change_my_mind": "a counterexample",
                            "supported_by": [study.findings[0].finding_id or "contention-1"],
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        graph_path = directory / "graph" / "evidence.json"
        graph_path.parent.mkdir(parents=True)
        graph_path.write_text(json.dumps({"stats": {"is_formed": True}, "keep": True}), encoding="utf-8")

        monkeypatch.setattr(
            "deepr.cli.commands.semantic.expert_graph._corpus_entries",
            lambda name: [],
        )

        result = CliRunner().invoke(expert, ["graph", "Subject", "--json"])
        assert result.exit_code == 2
        assert "nothing was written" in result.output
        assert json.loads(graph_path.read_text(encoding="utf-8"))["keep"] is True
