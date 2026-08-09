"""`deepr expert perspective`: lending a frame to a subject it knows nothing about.

The property that matters: this mode must never look like coverage. It claims
an analogy, says so in the first line of every rendering, and states where the
analogy breaks. A reading that cannot do those things is worse than no reading.
"""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from deepr.cli.commands.semantic.experts import expert


@pytest.fixture
def expert_home(tmp_path, monkeypatch):
    home = tmp_path / "experts"
    monkeypatch.setattr("deepr.cli.commands.semantic.expert_perspective.canonical_expert_dir", lambda n: home / n)
    return home


def _write_brief(home, name, *, orientation="I read this as a dependency problem.", settled=("A is settled",)):
    directory = home / name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "brief.json").write_text(
        json.dumps(
            {
                "expert_name": name,
                "orientation": orientation,
                "positions": [],
                "state": {"settled": list(settled), "live": ["B is contested"], "unknown": []},
            }
        ),
        encoding="utf-8",
    )
    return directory


@pytest.fixture
def profile(monkeypatch):
    class FakeProfile:
        name = "Lender"

    class FakeStore:
        def load(self, name):
            return FakeProfile() if name == "Lender" else None

    monkeypatch.setattr("deepr.experts.profile.ExpertStore", FakeStore)
    return FakeProfile


def _stub_backend(monkeypatch, reply):
    async def completion(prompt: str) -> str:
        completion.prompt = prompt
        return reply

    class FakeBackend:
        cost_note = "$0 local"
        capacity_source = "local:test"

    fake = FakeBackend()
    fake.completion = completion
    monkeypatch.setattr(
        "deepr.cli.commands.semantic.expert_perspective.build_study_backend", lambda **kwargs: fake
    )
    return completion


_GOOD_READING = json.dumps(
    {
        "observations": [
            "In my subject meaning lives in the order of construction, so I would ask whether "
            "your assembly order carries information nobody is reading."
        ],
        "where_it_breaks": ["My material is reversible and yours is not; a wrong step cannot be undone."],
    }
)


class TestItNeverClaimsCoverage:
    def test_every_rendering_says_analogy_in_its_opening(self, profile, expert_home, monkeypatch):
        _write_brief(expert_home, "Lender")
        _stub_backend(monkeypatch, _GOOD_READING)

        r = CliRunner().invoke(expert, ["perspective", "Lender", "how should I design a chair"])

        assert r.exit_code == 0, r.output
        assert "analogy, not evidence" in r.output

    def test_where_it_breaks_is_carried_into_the_output(self, profile, expert_home, monkeypatch):
        """An analogy with no stated limit is being offered as a fact."""
        _write_brief(expert_home, "Lender")
        _stub_backend(monkeypatch, _GOOD_READING)

        r = CliRunner().invoke(expert, ["perspective", "Lender", "chairs"])

        assert "cannot be undone" in r.output

    def test_a_frame_that_does_not_reach_says_so_and_exits_zero(self, profile, expert_home, monkeypatch):
        """A forced analogy is worse than none, so refusing is a real answer."""
        _write_brief(expert_home, "Lender")
        _stub_backend(monkeypatch, '{"observations": [], "where_it_breaks": []}')

        r = CliRunner().invoke(expert, ["perspective", "Lender", "chairs"])

        assert r.exit_code == 0
        assert "does not reach this" in r.output


class TestWhatItLends:
    def test_the_prompt_carries_patterns_rather_than_question_matched_evidence(
        self, profile, expert_home, monkeypatch
    ):
        """Ranking against a foreign question surfaces shared vocabulary, which
        is the least interesting thing a frame has to offer."""
        _write_brief(expert_home, "Lender")
        completion = _stub_backend(monkeypatch, _GOOD_READING)

        CliRunner().invoke(expert, ["perspective", "Lender", "how should I design a chair"])

        assert "I read this as a dependency problem." in completion.prompt
        assert "B is contested" in completion.prompt

    def test_a_preferred_lens_reaches_the_prompt(self, profile, expert_home, monkeypatch):
        _write_brief(expert_home, "Lender")
        completion = _stub_backend(monkeypatch, _GOOD_READING)

        CliRunner().invoke(expert, ["perspective", "Lender", "chairs", "--lens", "read it as negative space"])

        assert "read it as negative space" in completion.prompt


class TestRefusalsBeforeSpending:
    def test_unknown_expert_exits_two(self, profile, expert_home):
        r = CliRunner().invoke(expert, ["perspective", "Nobody", "chairs"])
        assert r.exit_code == 2
        assert "Expert not found" in r.output

    def test_an_unbriefed_expert_has_no_frame_to_lend(self, profile, expert_home, monkeypatch):
        _stub_backend(monkeypatch, _GOOD_READING)
        r = CliRunner().invoke(expert, ["perspective", "Lender", "chairs"])
        assert r.exit_code == 2
        assert "no frame to lend" in r.output

    def test_a_capacity_refusal_is_named_rather_than_swallowed(self, profile, expert_home, monkeypatch):
        _write_brief(expert_home, "Lender")

        async def refusing(prompt: str) -> str:
            raise RuntimeError("plan did not prove that paid extra usage is disabled")

        class FakeBackend:
            cost_note = "$0"
            capacity_source = "plan:claude"
            completion = staticmethod(refusing)

        monkeypatch.setattr(
            "deepr.cli.commands.semantic.expert_perspective.build_study_backend", lambda **kwargs: FakeBackend()
        )

        r = CliRunner().invoke(expert, ["perspective", "Lender", "chairs"])

        assert r.exit_code == 2
        assert "paid extra usage is disabled" in r.output


class TestOutput:
    def test_json_mode_emits_the_reading(self, profile, expert_home, monkeypatch):
        _write_brief(expert_home, "Lender")
        _stub_backend(monkeypatch, _GOOD_READING)

        r = CliRunner().invoke(expert, ["perspective", "Lender", "chairs", "--json"])

        assert r.exit_code == 0, r.output
        payload = json.loads(r.output)
        assert payload["where_it_breaks"]

    def test_out_writes_the_rendered_reading(self, profile, expert_home, monkeypatch, tmp_path):
        _write_brief(expert_home, "Lender")
        _stub_backend(monkeypatch, _GOOD_READING)
        target = tmp_path / "reading.md"

        r = CliRunner().invoke(expert, ["perspective", "Lender", "chairs", "--out", str(target)])

        assert r.exit_code == 0, r.output
        assert "analogy, not evidence" in target.read_text(encoding="utf-8")
