"""Grading a fleet as a progression, one thing per rung.

Five gates hold an expert at B: a thin or captured corpus, findings that reach
no passage, a small or unrecorded model doing the reading, no standpoint of its
own, and - separating A from S - staleness or disuse.

What is deliberately *not* a gate matters as much. Cross-source counts,
contention carried forward, declared open questions and named weaknesses were
all inferences about quality from a structural proxy, and every one of them is
satisfied by a shallow reading as easily as a deep one. Which model did the
reading predicts more than all of them together and is a fact rather than an
inference.
"""

import json

import pytest

from deepr.experts.expert_health import ExpertHealth, assess_expert, fleet_summary


def _strong(**overrides) -> ExpertHealth:
    """An expert with nothing structurally wrong with it."""
    defaults = dict(
        name="E",
        sources=20,
        origin_count=12,
        dominant_share=0.2,
        effective_origins=10.5,
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
        consulted_days_ago=3,
        graph_is_formed=True,
        model_tier="frontier",
    )
    return ExpertHealth(**{**defaults, **overrides})


class TestTheLadder:
    def test_well_researched_current_and_in_use_is_s(self):
        assert _strong().grade == "S"

    def test_never_consulted_is_the_difference_between_a_and_s(self):
        """A good expert nothing has ever asked is not being kept honest."""
        unused = _strong(consulted_days_ago=-1)
        assert not unused.is_in_use
        assert unused.grade == "A"

    def test_consulted_long_ago_is_also_only_a(self):
        assert _strong(consulted_days_ago=200).grade == "A"

    def test_not_current_is_a_however_much_it_is_used(self):
        assert _strong(age_days=60).grade == "A"
        assert _strong(age_days=400).grade == "A"

    def test_no_perspective_is_b_not_a(self):
        """Positions without a reading is a well-organized index, not an expert."""
        assert _strong(standpoint="").grade == "B"

    def test_dropped_dissent_is_now_a_warning_rather_than_a_gate(self):
        """Kept as a signal, demoted from the ladder.

        It is an inference about quality from a structural proxy, and a
        shallow reading satisfies it as easily as a deep one. The next action
        still says so; the letter no longer does.
        """
        closed = _strong(contention_findings=12, positions_with_dissent=0)
        assert closed.dropped_the_dissent
        assert closed.grade == "S"

    def test_naming_no_weakness_no_longer_blocks_the_top(self):
        """Self-reported hunger was the weakest signal here and gated the most."""
        assert _strong(known_weaknesses=0, open_questions=0).grade == "S"


class TestTheModelThatDidTheReading:
    """Weighted heavily, because it is a fact rather than an inference.

    A small model and a frontier model reading the same corpus through the
    same lenses produce different experts, and nothing downstream recovers the
    difference: a shallow finding is grounded, traceable and cross-source
    exactly as easily as a deep one.
    """

    def test_a_small_model_holds_an_otherwise_perfect_expert_at_b(self):
        assert _strong(model_tier="small").grade == "B"

    def test_an_unrecorded_model_does_not_pass_either(self):
        """Absence of evidence must not read as evidence of quality."""
        assert _strong(model_tier="unknown").grade == "B"

    def test_mid_tier_is_enough(self):
        assert _strong(model_tier="mid").grade == "S"

    def test_the_next_action_names_the_tier_and_says_what_to_do(self):
        action = _strong(model_tier="small").next_action
        assert "small model" in action
        assert "plan backend" in action

    def test_a_study_predating_the_stamp_is_classified_from_capacity_source(self, tmp_path):
        """The whole existing fleet is rankable without re-studying anything.

        capacity_source has always recorded which backend ran, and the tier is
        derived from exactly that. Requiring the newer stamp would have burned
        hours of quota to recover information already on disk.
        """
        (tmp_path / "study.json").write_text(
            json.dumps({"capacity_source": "plan:grok", "totals": {"findings": 1}}), encoding="utf-8"
        )
        assert assess_expert("E", tmp_path).model_tier == "frontier"

    def test_the_newer_stamp_wins_where_both_are_present(self, tmp_path):
        (tmp_path / "study.json").write_text(
            json.dumps(
                {
                    "capacity_source": "plan:grok",
                    "model_provenance": {"capacity_source": "local:qwen2.5:7b", "tier": "small"},
                }
            ),
            encoding="utf-8",
        )
        assert assess_expert("E", tmp_path).model_tier == "small"


class TestTheGraphGate:
    """Structural, and stronger than the ratio beside it.

    grounded_ratio averages - half the findings anchoring nowhere still scores
    0.5 and reads as middling. This asks whether any claim connects to a
    passage at all.
    """

    def test_an_expert_whose_claims_reach_no_passage_is_held_at_b(self):
        assert _strong(graph_is_formed=False).grade == "B"

    def test_the_next_action_points_at_the_command_that_shows_the_break(self):
        assert "expert graph" in _strong(graph_is_formed=False).next_action

    def test_it_is_read_from_the_evidence_graph_on_disk(self, tmp_path):
        (tmp_path / "graph").mkdir()
        (tmp_path / "graph" / "evidence.json").write_text(json.dumps({"stats": {"is_formed": True}}), encoding="utf-8")
        assert assess_expert("E", tmp_path).graph_is_formed

    def test_a_missing_graph_reads_as_not_formed_rather_than_raising(self, tmp_path):
        assert not assess_expert("E", tmp_path).graph_is_formed


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
    def test_one_publisher_is_not_depth_however_many_documents(self):
        thin = _strong(sources=30, origin_count=1, dominant_share=1.0, effective_origins=1.0)
        assert thin.grade == "B"
        assert "one publisher agreeing with itself" in thin.next_action

    def test_reading_more_of_the_best_source_does_not_lower_the_grade(self):
        """exp(H) fell when an expert read more of its most authoritative source.

        Five publishers with one document each scored 5.0; the same five with
        twenty from the best scored 1.98 and were told to acquire elsewhere.
        The grade-optimal move was deleting evidence.
        """
        spread = _strong(sources=5, origin_count=5, dominant_share=0.2, effective_origins=5.0)
        deeper = _strong(sources=24, origin_count=5, dominant_share=0.4, effective_origins=1.98)
        assert deeper.grade == spread.grade == "S"

    def test_too_few_publishers_is_b_however_current_and_used(self):
        assert _strong(origin_count=2).grade == "B"

    def test_capture_is_caught_by_share_not_entropy(self):
        captured = _strong(sources=24, origin_count=5, dominant_share=0.83, effective_origins=1.98)
        assert captured.is_captured
        assert captured.grade == "B"

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
            (_strong(consulted_days_ago=-1), "nobody has consulted it ever"),
            (_strong(consulted_days_ago=120), "in 120 days"),
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

    def test_a_header_only_corpus_is_not_a_source(self, tmp_path):
        corpus = tmp_path / "corpus"
        corpus.mkdir()
        (corpus / "index.jsonl").write_text(
            '{"schema_version": "deepr-expert-corpus-v1", "expert": "E"}\n',
            encoding="utf-8",
        )
        assert assess_expert("E", tmp_path).sources == 0


class TestConsultRecencyComesFromRealTraces:
    """The shape was guessed wrong once and silently graded everything A.

    A consult trace nests under `input` and `output`. Reading a flat
    `experts_consulted` found nothing, so every expert looked never-consulted
    and the top of the ladder was unreachable for a second reason.
    """

    def _write(self, path, records):
        path.write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")

    def test_both_requested_and_consulted_names_are_read(self, tmp_path, monkeypatch):
        from datetime import UTC, datetime

        from deepr.experts import expert_health

        traces = [
            {
                "recorded_at": "2026-08-01T00:00:00+00:00",
                "input": {"requested_experts": ["Asked For"]},
                "output": {"experts_consulted": ["Actually Spoke"]},
            }
        ]
        monkeypatch.setattr(expert_health, "_load_traces_for_recency", lambda limit: traces, raising=False)
        monkeypatch.setattr("deepr.experts.consult_traces.load_consult_traces", lambda limit=500: traces, raising=False)

        seen = expert_health.last_consulted_days(now=datetime(2026, 8, 6, tzinfo=UTC))

        assert seen["Asked For"] == 5
        assert seen["Actually Spoke"] == 5

    def test_a_failed_consult_still_counts_as_being_used(self, tmp_path, monkeypatch):
        """The question is whether anyone wants this expert, not whether it worked."""
        from datetime import UTC, datetime

        from deepr.experts import expert_health

        traces = [
            {
                "recorded_at": "2026-08-05T00:00:00+00:00",
                "input": {"requested_experts": ["Wanted"]},
                "output": {},
                "status": "failed",
            }
        ]
        monkeypatch.setattr("deepr.experts.consult_traces.load_consult_traces", lambda limit=500: traces, raising=False)

        assert expert_health.last_consulted_days(now=datetime(2026, 8, 6, tzinfo=UTC))["Wanted"] == 1

    def test_an_unreadable_trace_store_grades_everyone_never_consulted(self, monkeypatch):
        """Being wrong toward 'no evidence of use' is the safe direction."""
        from deepr.experts import expert_health

        def boom(limit=500):
            raise OSError("trace store is gone")

        monkeypatch.setattr("deepr.experts.consult_traces.load_consult_traces", boom, raising=False)

        assert expert_health.last_consulted_days() == {}


class TestFleetSummary:
    def test_closed_experts_are_counted_separately(self):
        fleet = [_strong(), _strong(positions_with_dissent=0, open_questions=0, known_weaknesses=0)]
        summary = fleet_summary(fleet)
        assert summary["closed"] == 1
        assert summary["s_tier"] == 2
        assert summary["consultable"] == 2

    def test_good_experts_nobody_uses_are_counted(self):
        """The triage question this answers: what did we build and abandon."""
        summary = fleet_summary([_strong(), _strong(consulted_days_ago=-1)])
        assert summary["unused"] == 1
        assert summary["s_tier"] == 1


class TestOpennessIsJudgedAgainstTheSubject:
    """Certainty is correct in some subjects, and the rule was domain-blind.

    Expert intuition is valid where the environment is regular and feedback
    exists; on a frozen specification there is no live dissent and an expert
    manufacturing some is worse than one reporting none. Measured expert
    organizations also err toward under-confidence, worst on the hardest
    questions, so a uniform penalty on certainty pushes the wrong way.
    """

    def test_a_settled_subject_is_not_penalized_for_having_no_dissent(self):
        settled = _strong(contention_findings=0, positions_with_dissent=0)
        assert not settled.subject_is_contested
        assert settled.is_open
        assert settled.grade == "S"

    def test_a_settled_subject_that_declares_nothing_is_still_fine(self):
        """Manufactured doubt on a frozen spec would be worse than none."""
        quiet = _strong(contention_findings=0, positions_with_dissent=0, open_questions=0, known_weaknesses=0)
        assert quiet.grade == "S"

    def test_a_brief_that_dropped_real_contention_is_still_reported(self):
        """The lens found it and the brief carried none of it. That is averaging.

        Still detected and still the next action; no longer a gate on the
        letter, because it is a proxy rather than a fact.
        """
        dropped = _strong(contention_findings=15, positions_with_dissent=0)
        assert dropped.dropped_the_dissent
        assert not dropped.is_open
        assert "carried none of them" in dropped.next_action

    def test_carrying_the_dissent_forward_clears_it(self):
        kept = _strong(contention_findings=15, positions_with_dissent=4)
        assert not kept.dropped_the_dissent
        assert kept.grade == "S"

    def test_declared_openness_alone_cannot_rescue_a_dropped_dissent(self):
        """Self-report is the weakest channel; it must not override the check."""
        loud = _strong(contention_findings=15, positions_with_dissent=0, open_questions=9, known_weaknesses=9)
        assert not loud.is_open

    def test_contention_findings_are_read_from_the_study(self, tmp_path):
        import json as _json

        (tmp_path / "study.json").write_text(
            _json.dumps(
                {
                    "totals": {"findings": 40, "grounded_findings": 39, "cross_source_findings": 8},
                    "independence": {"source_count": 12, "origin_count": 9, "dominant_share": 0.2},
                    "outcomes": [
                        {"lens": "contention", "finding_count": 6},
                        {"lens": "failure", "finding_count": 34},
                    ],
                    "started_at": "2026-08-07T00:00:00+00:00",
                }
            ),
            encoding="utf-8",
        )
        assert assess_expert("E", tmp_path).contention_findings == 6
