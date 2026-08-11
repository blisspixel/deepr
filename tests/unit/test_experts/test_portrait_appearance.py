"""An expert that chose how to look gets that, not a picture of its field.

The fallback prompt describes the *subject* an expert studies, so two experts
on one domain with opposite standpoints render nearly identically - the one
thing a portrait exists to prevent. These tests hold that a self-authored
appearance wins outright, and that a missing or broken self-account degrades to
the old behaviour rather than failing a portrait run.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from deepr.experts import expert_layout
from deepr.experts.portraits import _build_prompt, self_chosen_appearance


class TestTheExpertChoosesItsOwnFace:
    def test_a_written_appearance_is_the_scene(self) -> None:
        prompt = _build_prompt("tkg", "temporal knowledge graphs", None, appearance="A surveyor at dusk.")
        assert "A surveyor at dusk." in prompt
        assert "temporal knowledge graphs" not in prompt

    def test_who_is_in_the_scene_is_stated_rather_than_left_to_the_model(self) -> None:
        """An appearance describes a situation and rarely says who is in it.

        Left unstated, the model supplies its own default, and eight experts
        whose scenes were a loading dock, a card index and a survey field all
        came back as the same man in a blazer.
        """
        assert _build_prompt("tkg", None, None, appearance="A surveyor at dusk.").startswith("Portrait of a ")

    def test_the_same_expert_looks_like_itself_every_time(self) -> None:
        first = _build_prompt("tkg", None, None, appearance="A surveyor at dusk.")
        assert first == _build_prompt("tkg", None, None, appearance="A surveyor at dusk.")

    def test_different_experts_are_different_people(self) -> None:
        subjects = {
            _build_prompt(n, None, None, appearance="At a desk.").split(".")[0]
            for n in ("tkg", "anti-slop", "evaluation", "provenance", "retrieval", "mycorrhizal")
        }
        assert len(subjects) > 1, "the roster would be one person repeated"

    def test_the_style_does_not_force_a_boardroom(self) -> None:
        """The style used to say "high-end SaaS avatar" and "ultra-professional",
        which overwhelmed every scene an expert described."""
        prompt = _build_prompt("tkg", None, None, appearance="A surveyor at dusk.")
        assert "no suit or blazer" in prompt
        assert "Not a studio headshot" in prompt

    def test_the_field_is_used_only_when_nothing_was_chosen(self) -> None:
        assert "temporal knowledge graphs" in _build_prompt("tkg", "temporal knowledge graphs", None)

    def test_blank_and_whitespace_are_not_a_choice(self) -> None:
        for empty in (None, "", "   ", "\n\t "):
            assert "expert in" in _build_prompt("tkg", "graphs", None, appearance=empty)

    def test_the_house_style_still_applies(self) -> None:
        """A self-chosen portrait has to sit beside the rest of the library."""
        prompt = _build_prompt("tkg", "graphs", None, appearance="A surveyor at dusk", style="flat vector")
        assert "flat vector" in prompt
        assert prompt.endswith("No text or watermarks.")

    def test_the_expert_sentence_is_not_double_punctuated(self) -> None:
        assert ".. " not in _build_prompt("tkg", "graphs", None, appearance="A surveyor at dusk.")

    def test_a_long_appearance_is_bounded(self) -> None:
        prompt = _build_prompt("tkg", "graphs", None, appearance="word " * 500)
        assert len(prompt) < 1400


class TestReadingTheChoiceFromDisk:
    @pytest.fixture(autouse=True)
    def _fleet(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(expert_layout._paths, "canonical_expert_dir", lambda name: tmp_path / name)
        self.root = tmp_path

    def _write_self(self, name: str, body: str) -> None:
        directory = self.root / name
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "self.json").write_text(body, encoding="utf-8")

    def test_it_reads_what_the_expert_wrote(self) -> None:
        self._write_self("cairn", '{"appearance": "A surveyor at dusk."}')
        assert self_chosen_appearance("cairn") == "A surveyor at dusk."

    def test_an_expert_with_no_self_account_has_not_chosen(self) -> None:
        assert self_chosen_appearance("nobody") == ""

    def test_unreadable_json_falls_back_rather_than_failing_the_run(self) -> None:
        self._write_self("cairn", "{ not json")
        assert self_chosen_appearance("cairn") == ""

    def test_a_self_account_predating_the_field_is_fine(self) -> None:
        self._write_self("cairn", '{"standpoint": "I read this as a systems problem."}')
        assert self_chosen_appearance("cairn") == ""

    def test_it_finds_the_choice_before_migration_too(self) -> None:
        """Reads fall back, so an unmigrated expert still gets its own face."""
        directory = self.root / "cairn"
        directory.mkdir(parents=True)
        (directory / "profile_card.json").write_text('{"appearance": "A surveyor at dusk."}', encoding="utf-8")
        assert self_chosen_appearance("cairn") == "A surveyor at dusk."
