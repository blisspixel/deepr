"""`deepr expert profile`: the expert's own account of how it reads its subject.

The behaviour worth guarding is the shift history. Every study recomputes the
brief from the corpus, so a profile's record of changing its mind is the only
thing in an expert's directory that cannot be regenerated. Losing it to a bad
model reply, or dropping it on the operation that produces revisions, would be
the worst failure available here.
"""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from deepr.cli.commands.semantic.experts import expert


@pytest.fixture
def expert_home(tmp_path, monkeypatch):
    home = tmp_path / "experts"
    monkeypatch.setattr(
        "deepr.cli.commands.semantic.expert_profile_card_cmd.canonical_expert_dir", lambda n: home / n
    )
    return home


def _write_brief(home, name):
    directory = home / name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "brief.json").write_text(
        json.dumps(
            {
                "expert_name": name,
                "orientation": "I read this as a dependency problem.",
                "positions": [{"claim": "A", "would_change_my_mind": "B"}],
                "state": {"settled": ["s"], "live": ["l"], "unknown": []},
            }
        ),
        encoding="utf-8",
    )
    return directory


@pytest.fixture
def profile(monkeypatch):
    class FakeProfile:
        name = "Subject"

    class FakeStore:
        def load(self, name):
            return FakeProfile() if name == "Subject" else None

    monkeypatch.setattr("deepr.experts.profile.ExpertStore", FakeStore)
    return FakeProfile


def _stub_backend(monkeypatch, reply):
    async def completion(prompt: str) -> str:
        completion.prompt = prompt
        return reply

    class FakeBackend:
        cost_note = "$0 local"
        capacity_source = "local:qwen2.5:14b"
        model = "qwen2.5:14b"

    fake = FakeBackend()
    fake.completion = completion
    monkeypatch.setattr(
        "deepr.cli.commands.semantic.expert_profile_card_cmd.build_study_backend", lambda **kwargs: fake
    )
    return completion


def _reply(standpoint="I read this as a dependency problem.", **extra):
    return json.dumps(
        {
            "chosen_name": "Ledger",
            "standpoint": standpoint,
            "what_the_subject_is_about": "what depends on what",
            "preferred_lens": "mechanism",
            "open_questions": ["whether retraction scales"],
            "where_it_is_weak": ["no primary sources"],
            "voice": "plain",
            "glad_to_be_asked_about": ["dependency chains"],
            **extra,
        }
    )


class TestItUnlocksThePerspectiveRung:
    def test_it_writes_the_file_expert_health_reads(self, profile, expert_home, monkeypatch):
        """Nothing wrote profile_card.json, so the top of the ladder was unreachable."""
        _write_brief(expert_home, "Subject")
        _stub_backend(monkeypatch, _reply())

        r = CliRunner().invoke(expert, ["profile", "Subject"])

        assert r.exit_code == 0, r.output
        written = json.loads((expert_home / "Subject" / "profile_card.json").read_text(encoding="utf-8"))
        assert written["standpoint"]
        assert written["has_standpoint"] is True

    def test_the_chosen_name_and_invitation_are_surfaced(self, profile, expert_home, monkeypatch):
        _write_brief(expert_home, "Subject")
        _stub_backend(monkeypatch, _reply())

        r = CliRunner().invoke(expert, ["profile", "Subject"])

        assert "Ledger" in r.output
        assert "dependency chains" in r.output


class TestTheShiftHistory:
    def test_a_changed_standpoint_is_recorded_with_what_moved_it(self, profile, expert_home, monkeypatch):
        _write_brief(expert_home, "Subject")
        directory = expert_home / "Subject"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "profile_card.json").write_text(
            json.dumps({"expert_name": "Subject", "standpoint": "I used to read it as a naming problem."}),
            encoding="utf-8",
        )
        _stub_backend(
            monkeypatch,
            _reply(
                shift_from_prior="I used to read it as a naming problem.",
                shift_because="The failure lens found retraction, not naming, at the centre.",
            ),
        )

        r = CliRunner().invoke(expert, ["profile", "Subject"])

        assert r.exit_code == 0, r.output
        written = json.loads((directory / "profile_card.json").read_text(encoding="utf-8"))
        assert len(written["shifts"]) == 1
        assert written["shifts"][0]["because"].startswith("The failure lens")
        assert "changed its mind 1 time(s)" in r.output

    def test_earlier_shifts_survive_a_re_profile(self, profile, expert_home, monkeypatch):
        """Append-only. Overwriting leaves the state a new expert is already in."""
        _write_brief(expert_home, "Subject")
        directory = expert_home / "Subject"
        (directory / "profile_card.json").write_text(
            json.dumps(
                {
                    "expert_name": "Subject",
                    "standpoint": "Second reading.",
                    "shifts": [{"at": "2026-01-01", "was": "First reading.", "now": "Second reading.", "because": "x"}],
                }
            ),
            encoding="utf-8",
        )
        _stub_backend(
            monkeypatch,
            _reply(
                standpoint="Third reading.",
                shift_from_prior="Second reading.",
                shift_because="New sources.",
            ),
        )

        CliRunner().invoke(expert, ["profile", "Subject"])

        written = json.loads((directory / "profile_card.json").read_text(encoding="utf-8"))
        assert [s["was"] for s in written["shifts"]] == ["First reading.", "Second reading."]

    def test_an_unchanged_standpoint_records_no_shift(self, profile, expert_home, monkeypatch):
        """Inventing a change is worse than reporting none."""
        _write_brief(expert_home, "Subject")
        directory = expert_home / "Subject"
        (directory / "profile_card.json").write_text(
            json.dumps({"expert_name": "Subject", "standpoint": "Same reading."}), encoding="utf-8"
        )
        _stub_backend(monkeypatch, _reply(standpoint="Same reading.", shift_from_prior="", shift_because=""))

        CliRunner().invoke(expert, ["profile", "Subject"])

        assert json.loads((directory / "profile_card.json").read_text(encoding="utf-8"))["shifts"] == []

    def test_the_prior_standpoint_is_shown_to_the_model(self, profile, expert_home, monkeypatch):
        """It cannot report a change it was never shown."""
        _write_brief(expert_home, "Subject")
        (expert_home / "Subject" / "profile_card.json").write_text(
            json.dumps({"expert_name": "Subject", "standpoint": "An earlier reading."}), encoding="utf-8"
        )
        completion = _stub_backend(monkeypatch, _reply())

        CliRunner().invoke(expert, ["profile", "Subject"])

        assert "An earlier reading." in completion.prompt


class TestRefusalsBeforeWriting:
    def test_an_unusable_reply_does_not_destroy_the_shift_history(self, profile, expert_home, monkeypatch):
        """The history is the only unrecomputable thing in the directory."""
        _write_brief(expert_home, "Subject")
        card = expert_home / "Subject" / "profile_card.json"
        card.write_text(
            json.dumps(
                {
                    "expert_name": "Subject",
                    "standpoint": "A real reading.",
                    "shifts": [{"at": "2026-01-01", "was": "older", "now": "A real reading.", "because": "y"}],
                }
            ),
            encoding="utf-8",
        )
        _stub_backend(monkeypatch, "the model wrote prose instead")

        r = CliRunner().invoke(expert, ["profile", "Subject"])

        assert r.exit_code == 2
        assert "left alone" in r.output
        assert json.loads(card.read_text(encoding="utf-8"))["shifts"]

    def test_an_unbriefed_expert_is_refused(self, profile, expert_home, monkeypatch):
        _stub_backend(monkeypatch, _reply())
        r = CliRunner().invoke(expert, ["profile", "Subject"])
        assert r.exit_code == 2
        assert "has not landed anywhere" in r.output

    def test_a_brief_holding_no_positions_is_refused(self, profile, expert_home, monkeypatch):
        """Measured: a timed-out synthesis wrote an empty brief, and profiling
        against it produced a standpoint about the pipeline failing rather than
        about the subject. The "did it return a standpoint" check cannot catch
        that, because a description of the failure is a non-empty standpoint.
        """
        directory = expert_home / "Subject"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "brief.json").write_text(
            json.dumps({"expert_name": "Subject", "positions": [], "limitations": ["synthesis timed out"]}),
            encoding="utf-8",
        )
        _stub_backend(monkeypatch, _reply())

        r = CliRunner().invoke(expert, ["profile", "Subject"])

        assert r.exit_code == 2
        assert "no positions" in r.output

    def test_a_capacity_refusal_is_named(self, profile, expert_home, monkeypatch):
        _write_brief(expert_home, "Subject")

        async def refusing(prompt: str) -> str:
            raise RuntimeError("plan did not prove that paid extra usage is disabled")

        class FakeBackend:
            cost_note = "$0"
            capacity_source = "plan:claude"
            model = ""
            completion = staticmethod(refusing)

        monkeypatch.setattr(
            "deepr.cli.commands.semantic.expert_profile_card_cmd.build_study_backend",
            lambda **kwargs: FakeBackend(),
        )

        r = CliRunner().invoke(expert, ["profile", "Subject"])

        assert r.exit_code == 2
        assert "paid extra usage is disabled" in r.output
