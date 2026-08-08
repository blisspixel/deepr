"""Grading a fleet, where certainty counts against you.

The rule that shapes everything here: an expert holding no unresolved dissent,
naming no open questions and admitting no weakness is not finished, it is
closed. A full cup has no room. So openness is graded, and S requires all four
of deep, current, holding a perspective, and still looking.
"""

import json

import pytest

from deepr.experts.expert_health import ExpertHealth, assess_expert, fleet_summary


def _strong(**overrides) -> ExpertHealth:
    """An expert with nothing structurally wrong with it."""
    defaults = dict(
        name="E",
        sources=20,
        effective_origins=12.0,
        findings=90,
        grounded_findings=88,
        cross_source_findings=20,
        positions=6,
        falsifiable_positions=6,
        positions_with_dissent=3,
        standpoint="I read this as a systems problem.",
        open_questions=4,
        known_weaknesses=2,
        age_days=2,
    )
    return ExpertHealth(**{**defaults, **overrides})


class TestTheLadder:
    def test_all_four_reaches_s(self):
        assert _strong().grade == "S"

    def test_a_closed_expert_cannot_reach_s(self):
        """The full cup. Certainty is where learning stops, not where it ends."""
        closed = _strong(positions_with_dissent=0, open_questions=0, known_weaknesses=0)
        assert not closed.is_open
        assert closed.grade == "B"

    def test_no_perspective_caps_below_s(self):
        """Positions without a reading is a well-organized index."""
        assert _strong(standpoint="").grade == "A"

    def test_open_but_not_hungry_caps_below_s(self):
        """Leaving a gap unstated is not the same as going after it."""
        assert _strong(known_weaknesses=0).grade == "A"

    def test_stale_drops_further(self):
        assert _strong(age_days=400).grade == "B"

    def test_deep_but_not_current_is_a_not_s(self):
        assert _strong(age_days=60).grade == "A"


class TestCapsThatIgnoreDepth:
    def test_no_brief_caps_at_c_however_large_the_corpus(self):
        """An expert that has not landed anywhere is a search index."""
        assert _strong(positions=0, falsifiable_positions=0).grade == "C"

    def test_never_studied_is_c(self):
        assert _strong(findings=0, grounded_findings=0, positions=0).grade == "C"

    def test_claims_without_a_corpus_is_d(self):
        """Nothing can be re-read or checked, whatever the claim count says."""
        health = ExpertHealth(name="E", beliefs=150)
        assert health.grade == "D"
        assert "no retained corpus" in health.next_action

    def test_nothing_at_all_is_f(self):
        assert ExpertHealth(name="E").grade == "F"


class TestDepthIsOrigins:
    def test_many_documents_from_one_publisher_do_not_count_as_depth(self):
        thin = _strong(sources=30, effective_origins=1.0)
        assert thin.grade == "B"
        assert "one publisher agreeing with itself" in thin.next_action

    def test_unverifiable_findings_block_the_climb(self):
        shaky = _strong(grounded_findings=10)
        assert shaky.grade == "B"
        assert "verifiable" in shaky.next_action


class TestNextAction:
    @pytest.mark.parametrize(
        ("health", "expected"),
        [
            (ExpertHealth(name="E"), "Empty"),
            (_strong(findings=0, grounded_findings=0, positions=0), "never read"),
            (_strong(positions=0, falsifiable_positions=0), "never briefed"),
            (_strong(falsifiable_positions=4), "would overturn them"),
            (_strong(standpoint=""), "no reading of its own"),
            (_strong(open_questions=0), "no open questions"),
            (_strong(known_weaknesses=0), "nothing it is weak on"),
            (_strong(age_days=90), "Re-acquire to reach S"),
            (_strong(), "S tier"),
        ],
    )
    def test_every_grade_comes_with_something_to_do(self, health, expected):
        """A letter nobody can act on is not triage."""
        assert expected in health.next_action

    def test_only_one_action_is_offered(self):
        """Five things to do is the same as none."""
        assert "\n" not in _strong(sources=0, beliefs=5).next_action


class TestAssessFromDisk:
    def test_a_bare_directory_grades_f_rather_than_raising(self, tmp_path):
        assert assess_expert("E", tmp_path).grade == "F"

    def test_study_and_brief_are_read_together(self, tmp_path):
        (tmp_path / "study.json").write_text(
            json.dumps(
                {
                    "totals": {"findings": 40, "grounded_findings": 39, "cross_source_findings": 8},
                    "independence": {"source_count": 12, "effective_source_count": 9.0},
                    "started_at": "2026-08-07T00:00:00+00:00",
                }
            ),
            encoding="utf-8",
        )
        (tmp_path / "brief.json").write_text(
            json.dumps(
                {
                    "positions": [{"is_falsifiable": True, "unresolved_dissent": "one source disputes it"}],
                    "state": {"live": ["a"], "unknown": ["b"]},
                }
            ),
            encoding="utf-8",
        )

        health = assess_expert("E", tmp_path)

        assert health.sources == 12
        assert health.effective_origins == 9.0
        assert health.positions_with_dissent == 1
        assert health.is_open

    def test_a_corrupt_artifact_does_not_take_the_fleet_down(self, tmp_path):
        (tmp_path / "study.json").write_text("{not json", encoding="utf-8")
        assert assess_expert("E", tmp_path).grade == "F"


class TestFleetSummary:
    def test_closed_experts_are_counted_separately(self):
        fleet = [_strong(), _strong(positions_with_dissent=0, open_questions=0, known_weaknesses=0)]
        summary = fleet_summary(fleet)
        assert summary["closed"] == 1
        assert summary["s_tier"] == 1
        assert summary["consultable"] == 2
