"""Study lenses must stay domain-agnostic and resolve predictably."""

import pytest

from deepr.experts.study_lenses import (
    DEFAULT_LENS_KEYS,
    LENSES,
    axis_coverage,
    domain_hint_leaks,
    resolve_lenses,
)


class TestDomainAgnostic:
    def test_no_lens_prompt_names_a_subject_matter(self):
        """The invariant the whole design rests on.

        A lens that mentions networks, medicine, or markets is tuned to one
        topic. An expert substrate whose lenses only work on one kind of
        material is not a general expert substrate.
        """
        assert domain_hint_leaks() == []

    def test_guard_actually_catches_a_leak(self, monkeypatch):
        """A guard that cannot fail is not a guard."""
        from deepr.experts import study_lenses

        leaky = dict(study_lenses.LENSES)
        original = leaky["failure"]
        leaky["failure"] = type(original)(
            key=original.key,
            axis=original.axis,
            summary=original.summary,
            prompt=original.prompt + "\nFocus on network protocol behavior.",
            output_field=original.output_field,
        )
        monkeypatch.setattr(study_lenses, "LENSES", leaky)
        leaks = study_lenses.domain_hint_leaks()
        assert any("failure" in leak for leak in leaks)

    def test_every_lens_has_a_prompt_and_output_field(self):
        for key, lens in LENSES.items():
            assert lens.prompt.strip(), f"{key} has an empty prompt"
            assert lens.output_field.strip(), f"{key} has no output field"
            assert lens.axis in {"interrogation", "perspective"}


class TestResolve:
    def test_default_spans_both_axes(self):
        """A study pass on one axis is thin by construction."""
        coverage = axis_coverage(resolve_lenses(None))
        assert coverage["interrogation"] >= 2
        assert coverage["perspective"] >= 2

    def test_explicit_keys_preserve_order(self):
        resolved = resolve_lenses(["adversarial", "mechanism"])
        assert [lens.key for lens in resolved] == ["adversarial", "mechanism"]

    def test_duplicates_collapse(self):
        resolved = resolve_lenses(["failure", "failure", "Failure"])
        assert [lens.key for lens in resolved] == ["failure"]

    def test_hyphen_and_case_normalize(self):
        assert [lens.key for lens in resolve_lenses(["Human-Cultural"])] == ["human_cultural"]

    def test_unknown_lens_raises_and_lists_available(self):
        """A silent skip would let a typo quietly shrink a study pass."""
        with pytest.raises(ValueError) as excinfo:
            resolve_lenses(["mechanism", "nonsense"])
        message = str(excinfo.value)
        assert "nonsense" in message
        assert "adversarial" in message

    def test_default_keys_are_all_real(self):
        for key in DEFAULT_LENS_KEYS:
            assert key in LENSES
