"""`deepr expert viva`: examining an expert from the command line.

What matters here is that the command refuses cleanly before spending anything
when there is nothing to examine, and that a run producing no questions exits
non-zero rather than writing a clean-looking empty transcript.
"""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from deepr.cli.commands.semantic.experts import expert


@pytest.fixture
def expert_home(tmp_path, monkeypatch):
    """Point the canonical expert directory at a temp dir."""
    from deepr.experts import paths

    home = tmp_path / "experts"
    # Patched on `paths` alone: every path helper resolves through
    # `expert_layout`, which looks the root up on the module at call time
    # rather than binding it at import.
    monkeypatch.setattr(paths, "canonical_expert_dir", lambda name: home / name)
    return home


def _write_brief(home, name, *, orientation="I read this as a systems problem.", positions=1):
    directory = home / name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "brief.json").write_text(
        json.dumps(
            {
                "expert_name": name,
                "orientation": orientation,
                "positions": [
                    {
                        "claim": f"Position {i}",
                        "confidence": "moderate",
                        "would_change_my_mind": "A counterexample from a primary source.",
                    }
                    for i in range(positions)
                ],
            }
        ),
        encoding="utf-8",
    )
    return directory


@pytest.fixture
def profile(monkeypatch):
    """A loadable expert profile, so the command gets past name resolution."""

    class FakeProfile:
        name = "Candidate"

    class FakeStore:
        def load(self, name):
            return FakeProfile() if name in {"Candidate", "Examiner One"} else None

    monkeypatch.setattr("deepr.experts.profile.ExpertStore", FakeStore)
    return FakeProfile


def _stub_backend(monkeypatch, replies):
    """A $0 backend whose completion replays a script."""
    from deepr.cli.commands.semantic import study_backend as backend_module

    state = {"replies": list(replies), "prompts": []}

    async def completion(prompt: str) -> str:
        state["prompts"].append(prompt)
        return state["replies"].pop(0) if state["replies"] else ""

    class FakeBackend:
        capacity_source = "local:qwen2.5:14b"
        model = "qwen2.5:14b"
        cost_note = "$0 local"

    fake = FakeBackend()
    fake.completion = completion
    monkeypatch.setattr(
        "deepr.cli.commands.semantic.expert_viva.build_study_backend",
        lambda **kwargs: fake,
    )
    assert backend_module is not None
    return state


class TestRefusalsBeforeSpending:
    def test_unknown_expert_exits_two(self, profile, expert_home):
        r = CliRunner().invoke(expert, ["viva", "Nobody"])
        assert r.exit_code == 2
        assert "Expert not found" in r.output

    def test_an_unbriefed_expert_is_refused_with_the_command_to_run(self, profile, expert_home, monkeypatch):
        """Nothing to probe, so three model calls would produce a document saying so."""
        called = _stub_backend(monkeypatch, [])
        r = CliRunner().invoke(expert, ["viva", "Candidate"])
        assert r.exit_code == 2
        assert "has no brief" in r.output
        assert "expert brief" in r.output
        assert called["prompts"] == []

    def test_an_examiner_without_an_orientation_is_skipped(self, profile, expert_home, monkeypatch):
        _write_brief(expert_home, "Candidate")
        _write_brief(expert_home, "Examiner One", orientation="")
        _stub_backend(monkeypatch, [])

        r = CliRunner().invoke(expert, ["viva", "Candidate", "--examiner", "Examiner One"])

        assert r.exit_code == 2
        assert "holds no orientation of its own" in r.output
        assert "no usable examiners" in r.output


class TestAnExaminationThatRuns:
    def test_it_writes_the_transcript_and_the_reading_queue(self, profile, expert_home, monkeypatch):
        _write_brief(expert_home, "Candidate")
        _stub_backend(
            monkeypatch,
            [
                '{"questions": [{"question": "Why this?", "probes": "reasoning"}]}',
                "{}",
                "{}",
                '{"answers": [{"question": "Why this?", "answer": "Because X."}]}',
                '{"judgements": [{"question": "Why this?", "verdict": "cannot_answer",'
                ' "would_resolve_it": "The 2024 errata."}]}',
                "{}",
                "{}",
            ],
        )

        r = CliRunner().invoke(expert, ["viva", "Candidate"])

        assert r.exit_code == 0, r.output
        written = json.loads((expert_home / "Candidate" / "met" / "examination.json").read_text(encoding="utf-8"))
        assert written["reading_queue"] == ["The 2024 errata."]
        assert "The 2024 errata." in r.output

    def test_markdown_is_written_beside_the_json(self, profile, expert_home, monkeypatch):
        _write_brief(expert_home, "Candidate")
        _stub_backend(
            monkeypatch,
            ['{"questions": [{"question": "Q"}]}', "{}", "{}", '{"answers": []}', "{}", "{}", "{}"],
        )

        r = CliRunner().invoke(expert, ["viva", "Candidate", "--markdown"])

        assert r.exit_code == 0, r.output
        assert (expert_home / "Candidate" / "met" / "examination.md").exists()

    def test_a_panel_that_asked_nothing_exits_two(self, profile, expert_home, monkeypatch):
        """A broken backend must not read as a clean examination."""
        _write_brief(expert_home, "Candidate")
        _stub_backend(monkeypatch, ["not json", "not json", "not json"])

        r = CliRunner().invoke(expert, ["viva", "Candidate"])

        assert r.exit_code == 2
        assert "no examiner produced a question" in r.output

    def test_a_capacity_refusal_is_named_rather_than_swallowed(self, profile, expert_home, monkeypatch):
        """Measured live: the paid-overage guard refused and the run looked empty.

        A quota refusal affects every call, so it is the whole story rather
        than one flaky examiner. Reporting an empty panel without it sends
        someone looking for a prompt bug that is not there.
        """
        _write_brief(expert_home, "Candidate")

        async def refusing(prompt: str) -> str:
            raise RuntimeError("plan did not prove that paid extra usage is disabled")

        class FakeBackend:
            capacity_source = "plan:claude"
            model = ""
            cost_note = "$0 at the margin"
            completion = staticmethod(refusing)

        monkeypatch.setattr(
            "deepr.cli.commands.semantic.expert_viva.build_study_backend", lambda **kwargs: FakeBackend()
        )

        r = CliRunner().invoke(expert, ["viva", "Candidate"])

        assert r.exit_code == 2
        assert "paid extra usage is disabled" in r.output

    def test_a_failed_run_does_not_destroy_the_previous_transcript(self, profile, expert_home, monkeypatch):
        """Measured live: a backend hiccup overwrote a good viva with an empty one.

        An examination costs quota and several minutes. Losing one to a
        transient failure on the next run is the worst possible trade, so the
        refusal happens before anything is written.
        """
        _write_brief(expert_home, "Candidate")
        existing = expert_home / "Candidate" / "met" / "examination.json"
        existing.parent.mkdir(parents=True, exist_ok=True)
        existing.write_text('{"summary": "an earlier examination"}', encoding="utf-8")
        _stub_backend(monkeypatch, ["not json", "not json", "not json"])

        r = CliRunner().invoke(expert, ["viva", "Candidate"])

        assert r.exit_code == 2
        assert "left alone" in r.output
        assert json.loads(existing.read_text(encoding="utf-8"))["summary"] == "an earlier examination"

    def test_no_grade_appears_anywhere_in_the_output(self, profile, expert_home, monkeypatch):
        """expert health is the letter-shaped question; this one is not."""
        _write_brief(expert_home, "Candidate")
        _stub_backend(
            monkeypatch,
            [
                '{"questions": [{"question": "Q"}]}',
                "{}",
                "{}",
                '{"answers": [{"question": "Q", "answer": "A"}]}',
                '{"judgements": [{"question": "Q", "verdict": "answered"}]}',
                "{}",
                "{}",
            ],
        )

        r = CliRunner().invoke(expert, ["viva", "Candidate", "--json"])

        assert r.exit_code == 0, r.output
        payload = json.loads(r.output)
        assert "grade" not in payload
        assert "score" not in payload
