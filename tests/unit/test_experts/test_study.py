"""The study pass: anchoring, failure isolation, and honest limitations."""

import json

import pytest

from deepr.experts.corpus_store import CorpusStore
from deepr.experts.study import (
    build_findings,
    build_study_prompt,
    extract_json_object,
    run_study,
)
from deepr.experts.study_lenses import LENSES

CORPUS_TEXT = (
    "The reconciler applies desired state on a fixed interval. "
    "A hash of the primary name selects the operating slot, which is why two "
    "otherwise identical configurations can fail to meet. "
    "Operators frequently assume the export is a complete backup."
)


@pytest.fixture
def corpus(tmp_path):
    store = CorpusStore("Study Test Expert", storage_dir=tmp_path / "corpus")
    store.add(CORPUS_TEXT, origin_key="url:one.example", publisher="one.example")
    store.add("An unrelated second source about scheduling windows.", origin_key="url:two.example")
    return store


def _completion_returning(payload):
    async def _completion(_prompt: str) -> str:
        return json.dumps(payload) if isinstance(payload, dict) else payload

    return _completion


class TestExtractJsonObject:
    def test_plain_object(self):
        parsed, err = extract_json_object('{"a": 1}')
        assert parsed == {"a": 1} and err == ""

    def test_code_fence_stripped(self):
        parsed, _ = extract_json_object('```json\n{"a": 1}\n```')
        assert parsed == {"a": 1}

    def test_think_block_stripped(self):
        parsed, _ = extract_json_object('<think>pondering</think>{"a": 1}')
        assert parsed == {"a": 1}

    def test_prose_around_object(self):
        parsed, _ = extract_json_object('Here you go:\n{"a": 1}\nHope that helps.')
        assert parsed == {"a": 1}

    def test_empty_reports_error(self):
        parsed, err = extract_json_object("   ")
        assert parsed is None and "empty" in err

    def test_invalid_json_reports_error(self):
        parsed, err = extract_json_object('{"a": }')
        assert parsed is None and "invalid JSON" in err

    def test_array_top_level_rejected(self):
        parsed, err = extract_json_object("[1, 2, 3]")
        assert parsed is None and err


class TestAnchoring:
    def test_verbatim_anchor_is_grounded(self, corpus):
        material = corpus.load_study_material()
        parsed = {
            "fail_patterns": [
                {"name": "slot mismatch", "anchors": ["A hash of the primary name selects the operating slot"]}
            ]
        }
        findings = build_findings(LENSES["failure"], parsed, material)
        assert len(findings) == 1
        assert findings[0].is_grounded is True
        assert findings[0].corpus_shas

    def test_invented_anchor_is_labeled_not_dropped(self, corpus):
        """Deciding a finding is wrong is meaning; this layer only checks form."""
        material = corpus.load_study_material()
        parsed = {
            "fail_patterns": [{"name": "fabricated", "anchors": ["this sentence never appeared anywhere at all"]}]
        }
        findings = build_findings(LENSES["failure"], parsed, material)
        assert len(findings) == 1
        assert findings[0].is_grounded is False
        assert findings[0].ungrounded_anchor_count == 1

    def test_anchor_matching_survives_reflowed_whitespace(self, corpus):
        material = corpus.load_study_material()
        parsed = {"fail_patterns": [{"name": "reflowed", "anchors": ["A hash   of the primary\n name selects"]}]}
        findings = build_findings(LENSES["failure"], parsed, material)
        assert findings[0].is_grounded is True

    def test_trivially_short_anchor_never_grounds(self, corpus):
        """Short strings match by coincidence and would make grounding meaningless."""
        material = corpus.load_study_material()
        parsed = {"fail_patterns": [{"name": "short", "anchors": ["the"]}]}
        findings = build_findings(LENSES["failure"], parsed, material)
        assert findings[0].is_grounded is False

    def test_findings_recovered_from_wrong_top_level_key(self, corpus):
        material = corpus.load_study_material()
        parsed = {"results": [{"name": "x", "anchors": ["The reconciler applies desired state"]}]}
        findings = build_findings(LENSES["failure"], parsed, material)
        assert len(findings) == 1


class TestPrompt:
    def test_prompt_carries_lens_and_corpus_and_demands_anchors(self, corpus):
        material = corpus.load_study_material()
        prompt = build_study_prompt(LENSES["adversarial"], material)
        assert "anchors" in prompt
        assert "CORPUS BEGINS" in prompt
        assert "reconciler applies desired state" in prompt
        assert LENSES["adversarial"].output_field in prompt


class TestRunStudy:
    @pytest.mark.asyncio
    async def test_empty_corpus_reports_limitation_and_makes_no_calls(self, tmp_path):
        empty = CorpusStore("Empty Expert", storage_dir=tmp_path / "corpus")
        calls = []

        async def _completion(prompt):
            calls.append(prompt)
            return "{}"

        result = await run_study(
            expert_name="Empty Expert", corpus=empty, completion=_completion, lens_keys=["failure"]
        )
        assert calls == []
        assert result.exit_code == 2
        assert any("Corpus is empty" in limit for limit in result.limitations)

    @pytest.mark.asyncio
    async def test_one_failing_lens_does_not_kill_the_pass(self, corpus):
        async def _completion(prompt):
            if "adversarial" in prompt.lower() or "turned against" in prompt:
                raise RuntimeError("backend refused")
            return json.dumps({"fail_patterns": [{"name": "ok", "anchors": [CORPUS_TEXT[:60]]}]})

        result = await run_study(
            expert_name="E",
            corpus=corpus,
            completion=_completion,
            lens_keys=["failure", "adversarial"],
        )
        assert result.exit_code == 1
        assert "adversarial" in result.failed_lenses
        # One finding per chunk: the corpus has two sources, so the working
        # lens runs twice and its findings merge.
        assert len(result.findings) == len(corpus.iter_study_chunks(chunk_chars=14000))

    @pytest.mark.asyncio
    async def test_all_lenses_failing_is_exit_two(self, corpus):
        async def _completion(_prompt):
            raise RuntimeError("backend down")

        result = await run_study(
            expert_name="E", corpus=corpus, completion=_completion, lens_keys=["failure", "mechanism"]
        )
        assert result.exit_code == 2

    @pytest.mark.asyncio
    async def test_parse_failure_is_recorded_not_raised(self, corpus):
        result = await run_study(
            expert_name="E",
            corpus=corpus,
            completion=_completion_returning("not json at all"),
            lens_keys=["failure"],
        )
        assert result.outcomes[0].status == "parse_failed"
        assert result.exit_code == 2

    @pytest.mark.asyncio
    async def test_single_origin_corpus_is_flagged(self, tmp_path):
        """Agreement within one publisher is not corroboration."""
        store = CorpusStore("Single Origin", storage_dir=tmp_path / "corpus")
        store.add("Only source body text here for study.", origin_key="url:only.example")
        result = await run_study(
            expert_name="E",
            corpus=store,
            completion=_completion_returning({"fail_patterns": []}),
            lens_keys=["failure"],
        )
        assert any("single origin" in limit for limit in result.limitations)

    @pytest.mark.asyncio
    async def test_ungrounded_anchors_surface_as_a_limitation(self, corpus):
        result = await run_study(
            expert_name="E",
            corpus=corpus,
            completion=_completion_returning(
                {"fail_patterns": [{"name": "x", "anchors": ["a phrase that is simply not present"]}]}
            ),
            lens_keys=["failure"],
        )
        assert any("not found in the retained corpus" in limit for limit in result.limitations)

    @pytest.mark.asyncio
    async def test_study_never_reads_the_belief_store(self, corpus):
        """The echo-chamber guard: findings come from sources, not prior conclusions."""
        seen = {}

        async def _completion(prompt):
            seen["prompt"] = prompt
            return json.dumps({"fail_patterns": []})

        await run_study(expert_name="E", corpus=corpus, completion=_completion, lens_keys=["failure"])
        assert "SOURCE " in seen["prompt"]
        assert "belief" not in seen["prompt"].lower()

    @pytest.mark.asyncio
    async def test_result_serializes_with_counts(self, corpus):
        result = await run_study(
            expert_name="E",
            corpus=corpus,
            completion=_completion_returning({"fail_patterns": [{"name": "y", "anchors": [CORPUS_TEXT[:60]]}]}),
            lens_keys=["failure", "operational"],
        )
        payload = result.to_dict()
        assert payload["schema_version"] == "deepr-expert-study-v1"
        assert payload["totals"]["lenses_run"] == 2
        assert payload["corpus"]["distinct_origins"] == 2
        assert payload["cost_usd"] == 0.0

    @pytest.mark.asyncio
    async def test_default_lenses_span_both_axes(self, corpus):
        result = await run_study(
            expert_name="E",
            corpus=corpus,
            completion=_completion_returning({"fail_patterns": []}),
        )
        coverage = result.axis_coverage()
        assert coverage["interrogation"] >= 2
        assert coverage["perspective"] >= 2
