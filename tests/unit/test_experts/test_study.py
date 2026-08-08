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
from deepr.experts.study_contracts import LensOutcome
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


class TestFindingTitles:
    """Titles are how the brief cites findings, so a useless title is a broken citation."""

    def test_a_lens_naming_its_subject_gets_that_name(self, corpus):
        material = corpus.load_study_material()
        parsed = {"fail_patterns": [{"name": "slot mismatch", "anchors": ["The reconciler applies desired state"]}]}
        assert build_findings(LENSES["failure"], parsed, material)[0].title == "slot mismatch"

    def test_a_tension_is_titled_from_its_description(self, corpus):
        """The contention lens returns description/source/type, and none of them is 'name'."""
        material = corpus.load_study_material()
        parsed = {
            "tensions": [
                {
                    "description": "Sources disagree on whether the export is a backup",
                    "type": "disputed",
                    "anchors": ["Operators frequently assume the export is a complete backup"],
                }
            ]
        }
        title = build_findings(LENSES["contention"], parsed, material)[0].title
        assert title == "Sources disagree on whether the export is a backup"

    def test_a_source_hash_is_never_used_as_a_title(self, corpus):
        """Observed live: 40 findings all titled with the same corpus hash.

        Every citation then matched every finding, so citation checking in the
        brief silently stopped meaning anything.
        """
        material = corpus.load_study_material()
        sha = material[0][0].sha256
        parsed = {
            "tensions": [
                {
                    "source": sha,
                    "description": "Sources disagree on backup semantics",
                    "anchors": ["Operators frequently assume the export is a complete backup"],
                }
            ]
        }
        title = build_findings(LENSES["contention"], parsed, material)[0].title
        assert title == "Sources disagree on backup semantics"

    def test_a_truncated_source_hash_is_also_rejected(self, corpus):
        material = corpus.load_study_material()
        parsed = {
            "tensions": [
                {
                    "name": material[0][0].sha256[:12],
                    "anchors": ["Operators frequently assume the export is a complete backup"],
                }
            ]
        }
        assert build_findings(LENSES["contention"], parsed, material)[0].title == "contention finding"

    def test_a_finding_that_names_nothing_falls_back_to_the_lens(self, corpus):
        material = corpus.load_study_material()
        parsed = {"tensions": [{"anchors": ["The reconciler applies desired state"]}]}
        assert build_findings(LENSES["contention"], parsed, material)[0].title == "contention finding"


class TestProvenanceHonesty:
    """The numbers that make a brief look corroborated must not be fiction."""

    def test_a_finding_is_credited_only_to_the_source_the_lens_read(self, tmp_path):
        """Grounding used to run against the whole corpus, not the chunk shown.

        Shared boilerplate is ubiquitous in web-acquired text, so an anchor
        would resolve to whichever source sorted first among those containing
        it. Findings were credited to documents the lens never saw, and the
        coverage report then called the real source untouched.
        """
        shared = "This material is provided without warranty of any kind whatsoever."
        store = CorpusStore("Provenance Expert", storage_dir=tmp_path / "corpus")
        store.add(f"Alpha document. {shared}", origin_key="url:aaa.example")
        store.add(f"Zulu document. {shared}", origin_key="url:zzz.example")

        material = store.load_study_material()
        zulu = [(entry, text) for entry, text in material if "Zulu" in text]
        assert zulu, "fixture must contain the Zulu source"

        parsed = {"fail_patterns": [{"name": "shared boilerplate", "anchors": [shared]}]}
        findings = build_findings(LENSES["failure"], parsed, zulu)

        assert findings[0].corpus_shas == [zulu[0][0].sha256]

    def test_findings_get_unique_ids_across_chunks(self, corpus):
        parsed = {"fail_patterns": [{"name": "a", "anchors": ["x"]}, {"name": "b", "anchors": ["y"]}]}
        material = corpus.load_study_material()
        first = build_findings(LENSES["failure"], parsed, material, start_index=1)
        second = build_findings(LENSES["failure"], parsed, material, start_index=len(first) + 1)

        ids = [f.finding_id for f in first + second]
        assert ids == ["failure-1", "failure-2", "failure-3", "failure-4"]
        assert len(set(ids)) == len(ids)


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
        assert result.independence.effective_source_count == 1.0
        assert any("agreeing with itself" in limit for limit in result.limitations)

    @pytest.mark.asyncio
    async def test_many_pages_from_one_publisher_still_count_as_one(self, tmp_path):
        """The shape of the run this check was written for: 3 pages, 1 publisher."""
        store = CorpusStore("One Publisher", storage_dir=tmp_path / "corpus")
        for n in range(3):
            store.add(f"Page {n} body text retained for study.", origin_key="url:en.wikipedia.org")

        result = await run_study(
            expert_name="E",
            corpus=store,
            completion=_completion_returning({"fail_patterns": []}),
            lens_keys=["failure"],
        )

        assert result.independence.source_count == 3
        assert result.independence.effective_source_count == 1.0
        assert result.independence.is_thin

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


class TestReentrancy:
    """Recovery is structural, not conversational.

    A study is tens of model calls over many minutes. Holding it all in memory
    until the end means one interruption discards work that already succeeded
    and was already paid for.
    """

    @pytest.mark.asyncio
    async def test_the_pass_is_checkpointed_after_every_lens(self, corpus):
        seen: list[int] = []
        result = await run_study(
            expert_name="E",
            corpus=corpus,
            completion=_completion_returning({"fail_patterns": [{"name": "x", "anchors": [CORPUS_TEXT[:60]]}]}),
            lens_keys=["failure", "mechanism"],
            checkpoint=lambda r: seen.append(len(r.outcomes)),
        )
        assert seen == [1, 2]
        assert len(result.outcomes) == 2

    @pytest.mark.asyncio
    async def test_a_completed_lens_is_reused_rather_than_re_read(self, corpus):
        calls: list[str] = []

        async def _completion(prompt):
            calls.append(prompt)
            return json.dumps({"fail_patterns": [{"name": "x", "anchors": [CORPUS_TEXT[:60]]}]})

        first = await run_study(expert_name="E", corpus=corpus, completion=_completion, lens_keys=["failure"])
        after_first = len(calls)

        second = await run_study(
            expert_name="E",
            corpus=corpus,
            completion=_completion,
            lens_keys=["failure", "mechanism"],
            resume_from=first.outcomes,
        )

        assert len(calls) > after_first, "the new lens must still run"
        assert len(second.outcomes) == 2
        assert any("Resumed" in limit for limit in second.limitations)

    @pytest.mark.asyncio
    async def test_a_failed_lens_is_retried_rather_than_reused(self, corpus):
        """Reusing a parse failure would make the interruption permanent."""
        failed = LensOutcome(lens="failure", axis="interrogation", status="parse_failed")
        calls: list[str] = []

        async def _completion(prompt):
            calls.append(prompt)
            return json.dumps({"fail_patterns": [{"name": "x", "anchors": [CORPUS_TEXT[:60]]}]})

        result = await run_study(
            expert_name="E",
            corpus=corpus,
            completion=_completion,
            lens_keys=["failure"],
            resume_from=[failed],
        )

        assert calls, "a failed lens must be re-read"
        assert result.outcomes[0].status == "ok"
