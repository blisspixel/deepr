"""`deepr expert practice --show` must not mutate disk."""

from __future__ import annotations

import json

from click.testing import CliRunner

from deepr.cli.commands.semantic.experts import expert


def _patch_home(tmp_path, monkeypatch):
    from deepr.experts import paths

    home = tmp_path / "experts"
    monkeypatch.setattr(paths, "canonical_expert_dir", lambda name: home / name)

    class FakeProfile:
        name = "Subject"

    class FakeStore:
        def load(self, name):
            return FakeProfile() if name == "Subject" else None

    monkeypatch.setattr("deepr.experts.profile.ExpertStore", FakeStore)
    return home / "Subject"


class TestPracticeShowIsReadOnly:
    def test_show_does_not_create_a_file(self, tmp_path, monkeypatch):
        directory = _patch_home(tmp_path, monkeypatch)
        directory.mkdir(parents=True)

        result = CliRunner().invoke(expert, ["practice", "Subject", "--show"])
        assert result.exit_code == 2
        assert "no research practice" in result.output
        assert not (directory / "attend" / "practice.json").exists()

    def test_show_does_not_rewrite_an_existing_file(self, tmp_path, monkeypatch):
        directory = _patch_home(tmp_path, monkeypatch)
        path = directory / "attend" / "practice.json"
        path.parent.mkdir(parents=True)
        original = {
            "expert": "Subject",
            "updated_at": "2026-01-01T00:00:00+00:00",
            "pursuits": [{"question": "Q", "status": "open"}],
            "watches": [],
            "interests": [],
        }
        path.write_text(json.dumps(original), encoding="utf-8")

        result = CliRunner().invoke(expert, ["practice", "Subject", "--show", "--json"])
        assert result.exit_code == 0, result.output
        assert json.loads(path.read_text(encoding="utf-8"))["updated_at"] == "2026-01-01T00:00:00+00:00"

    def test_show_refuses_an_unreadable_file(self, tmp_path, monkeypatch):
        directory = _patch_home(tmp_path, monkeypatch)
        path = directory / "attend" / "practice.json"
        path.parent.mkdir(parents=True)
        path.write_text("{not json", encoding="utf-8")

        result = CliRunner().invoke(expert, ["practice", "Subject", "--show"])
        assert result.exit_code == 2
        assert "unreadable" in result.output
        assert path.read_text(encoding="utf-8") == "{not json"


class TestPracticeRequiresACitedBrief:
    def test_update_refuses_without_a_brief(self, tmp_path, monkeypatch):
        directory = _patch_home(tmp_path, monkeypatch)
        directory.mkdir(parents=True)

        called: list[object] = []
        monkeypatch.setattr(
            "deepr.cli.commands.semantic.expert_practice.build_study_backend",
            lambda **kwargs: called.append(kwargs) or (_ for _ in ()).throw(AssertionError("backend")),
        )

        result = CliRunner().invoke(expert, ["practice", "Subject", "--local"])
        assert result.exit_code == 2
        assert "cannot keep a practice" in result.output
        assert called == []
        assert not (directory / "attend" / "practice.json").exists()
