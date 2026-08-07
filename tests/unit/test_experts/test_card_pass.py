"""One card per source: bounded, incremental, and honest when a read fails.

The property that matters is that adding a source costs one call. An expert
you can grow a document at a time is a different thing from one that must be
rebuilt, and the difference is what lets a corpus get large.
"""

import json

import pytest

from deepr.experts.card_pass import (
    build_one_card,
    card_path,
    load_card,
    run_card_pass,
    save_card,
)
from deepr.experts.corpus_store import CorpusStore
from deepr.experts.source_card import SourceCard, build_card_prompt

SOURCE_TEXT = (
    "The reconciler applies desired state on a fixed thirty second interval. "
    "Operators frequently assume the export is a complete backup, which it is not. "
    "The authors note that behaviour above five hundred clusters was not measured."
)

_GOOD = {
    "what_it_is": "A vendor operations guide, undated.",
    "summary": "Describes the reconciliation loop and its backup semantics.",
    "establishes": ["The reconciler runs on a fixed interval"],
    "notable": ["The export is not a backup, contrary to common assumption"],
    "stops_at": "Does not cover behaviour above five hundred clusters.",
    "claims": [
        {
            "statement": "Reconciliation runs on a thirty second interval",
            "anchor": "applies desired state on a fixed thirty second interval",
            "hedged": False,
        }
    ],
    "leans_on": ["the upstream controller spec"],
}


@pytest.fixture
def corpus(tmp_path):
    store = CorpusStore("Card Expert", storage_dir=tmp_path / "corpus")
    store.add(SOURCE_TEXT, origin_key="url:a.org", title="Ops Guide")
    return store


def _completion_returning(payload, calls=None):
    async def _completion(prompt):
        if calls is not None:
            calls.append(prompt)
        return json.dumps(payload)

    return _completion


class TestCardPrompt:
    def test_the_prompt_asks_for_a_card_not_a_summary(self):
        prompt = build_card_prompt(sha="abc123def456", origin="url:a.org", title="T", text="body")
        assert "Not a summary" in prompt
        assert "establishes" in prompt
        assert "stops_at" in prompt

    def test_the_prompt_demands_verbatim_anchors(self):
        prompt = build_card_prompt(sha="abc", origin="url:a.org", title="", text="body")
        assert "copied verbatim" in prompt
        assert "cannot anchor should not be reported" in prompt

    def test_the_prompt_carries_only_one_source(self):
        """Bounded by the document, which is what makes the corpus able to grow."""
        prompt = build_card_prompt(sha="abc", origin="url:a.org", title="", text="body text")
        assert prompt.count("| origin=") == 1


class TestBuildOneCard:
    @pytest.mark.asyncio
    async def test_a_read_card_carries_what_the_source_establishes(self, corpus):
        entry, text = corpus.load_study_material()[0]
        card = await build_one_card(entry, text, _completion_returning(_GOOD))

        assert card.is_read
        assert card.establishes == ["The reconciler runs on a fixed interval"]
        assert card.stops_at.startswith("Does not cover")
        assert card.sha256 == entry.sha256

    @pytest.mark.asyncio
    async def test_a_verbatim_anchor_grounds(self, corpus):
        entry, text = corpus.load_study_material()[0]
        card = await build_one_card(entry, text, _completion_returning(_GOOD))
        assert card.grounded_claims

    @pytest.mark.asyncio
    async def test_an_invented_anchor_is_labeled_not_dropped(self, corpus):
        """Deciding a claim is wrong is meaning; this layer only checks form."""
        payload = json.loads(json.dumps(_GOOD))
        payload["claims"][0]["anchor"] = "this phrase appears nowhere in the source at all"
        entry, text = corpus.load_study_material()[0]

        card = await build_one_card(entry, text, _completion_returning(payload))

        assert len(card.claims) == 1
        assert not card.grounded_claims
        assert any("nothing here is checkable" in c for c in card.concerns())

    @pytest.mark.asyncio
    async def test_a_failed_call_becomes_an_error_card_not_an_exception(self, corpus):
        async def _boom(_prompt):
            raise RuntimeError("backend down")

        entry, text = corpus.load_study_material()[0]
        card = await build_one_card(entry, text, _boom)

        assert not card.is_read
        assert "backend down" in card.error
        assert any("was not read" in c for c in card.concerns())

    @pytest.mark.asyncio
    async def test_unparseable_output_reports_what_came_back(self, corpus):
        async def _prose(_prompt):
            return "I think the main themes are..."

        entry, text = corpus.load_study_material()[0]
        card = await build_one_card(entry, text, _prose)

        assert "main themes" in card.error

    @pytest.mark.asyncio
    async def test_a_source_over_budget_says_how_much_was_not_read(self, corpus):
        entry, text = corpus.load_study_material()[0]
        card = await build_one_card(entry, text, _completion_returning(_GOOD), source_budget=40)

        assert card.truncated_chars == len(text) - 40
        assert any("were not read" in c for c in card.concerns())


class TestIncremental:
    @pytest.mark.asyncio
    async def test_adding_a_source_costs_one_call(self, corpus, tmp_path):
        """The whole point: an expert grows a document at a time."""
        calls: list[str] = []
        completion = _completion_returning(_GOOD, calls)

        await run_card_pass(expert_name="E", corpus=corpus, expert_dir=tmp_path, completion=completion)
        assert len(calls) == 1

        corpus.add("A second and entirely different retained document body.", origin_key="url:b.org")
        result = await run_card_pass(expert_name="E", corpus=corpus, expert_dir=tmp_path, completion=completion)

        assert len(calls) == 2
        assert result.built == 1
        assert result.reused == 1

    @pytest.mark.asyncio
    async def test_an_unchanged_corpus_costs_nothing(self, corpus, tmp_path):
        calls: list[str] = []
        completion = _completion_returning(_GOOD, calls)

        await run_card_pass(expert_name="E", corpus=corpus, expert_dir=tmp_path, completion=completion)
        result = await run_card_pass(expert_name="E", corpus=corpus, expert_dir=tmp_path, completion=completion)

        assert len(calls) == 1
        assert result.reused == 1
        assert result.built == 0

    @pytest.mark.asyncio
    async def test_rebuild_forces_a_re_read(self, corpus, tmp_path):
        calls: list[str] = []
        completion = _completion_returning(_GOOD, calls)

        await run_card_pass(expert_name="E", corpus=corpus, expert_dir=tmp_path, completion=completion)
        await run_card_pass(expert_name="E", corpus=corpus, expert_dir=tmp_path, completion=completion, rebuild=True)

        assert len(calls) == 2

    @pytest.mark.asyncio
    async def test_one_failed_source_does_not_lose_the_others(self, corpus, tmp_path):
        corpus.add("A second and entirely different retained document body.", origin_key="url:b.org")
        seen: list[str] = []

        async def _flaky(prompt):
            seen.append(prompt)
            if len(seen) == 1:
                raise RuntimeError("transient")
            return json.dumps(_GOOD)

        result = await run_card_pass(expert_name="E", corpus=corpus, expert_dir=tmp_path, completion=_flaky)

        assert len(result.cards) == 2
        assert result.failed == 1
        assert result.built == 1
        assert result.exit_code == 1


class TestPersistence:
    def test_a_card_round_trips(self, tmp_path):
        card = SourceCard(
            sha256="abc123",
            origin_key="url:a.org",
            title="T",
            summary="what it says",
            establishes=["a thing"],
        )
        save_card(tmp_path, card)

        loaded = load_card(tmp_path, "abc123")

        assert loaded is not None
        assert loaded.summary == "what it says"
        assert loaded.establishes == ["a thing"]

    def test_a_card_is_keyed_by_content_hash(self, tmp_path):
        """So a revised source gets a new card and the old one is still there."""
        assert card_path(tmp_path, "abc123").name == "abc123.json"

    def test_a_corrupt_card_is_absence_not_a_crash(self, tmp_path):
        path = card_path(tmp_path, "abc123")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{not json", encoding="utf-8")
        assert load_card(tmp_path, "abc123") is None
