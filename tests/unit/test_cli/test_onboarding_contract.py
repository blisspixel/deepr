"""The documented local path reaches a cited, consultable expert at $0."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from deepr.cli.main import cli
from deepr.experts.brief_contracts import ExpertBrief, Position, SettledState
from deepr.experts.consult_context import build_consult_context, load_brief, load_study, render_consult_packet
from deepr.experts.corpus_store import CorpusStore
from deepr.experts.study_contracts import LensOutcome, StudyFinding, StudyResult


def _invoke(runner: CliRunner, args: list[str]) -> str:
    result = runner.invoke(cli, args)
    assert result.exit_code == 0, f"{result.output}\n{result.exception!r}"
    return result.output


def test_documented_local_onboarding_builds_cited_consult_context(tmp_path, monkeypatch):
    """Every public onboarding verb composes into the stored consult packet."""
    from deepr.cli.commands.semantic import expert_consult, expert_study

    expert_name = "Onboarding Contract Expert"
    question = "When are retry writes safe?"
    source_text = (
        "Retries without idempotency keys can duplicate writes. "
        "Use an idempotency key before retrying a state-changing request."
    )
    source = tmp_path / "source.md"
    source.write_text(source_text, encoding="utf-8")
    monkeypatch.setenv("DEEPR_LOCAL_MODEL", "fixture-model")

    runner = CliRunner()
    with patch("deepr.providers.create_provider", side_effect=AssertionError("provider constructed")) as provider:
        make_output = _invoke(
            runner,
            [
                "expert",
                "make",
                expert_name,
                "--local",
                "-d",
                "Safe retry boundary decisions",
            ],
        )
        for next_verb in ("retain", "study", "brief", "consult"):
            assert f"expert {next_verb}" in make_output

        _invoke(
            runner,
            ["expert", "retain", expert_name, str(source), "--title", "Trusted starting source"],
        )
        corpus = CorpusStore(expert_name)
        entries = corpus.active_entries()
        assert len(entries) == 1
        source_sha = entries[0].sha256

        study = StudyResult(
            expert_name=expert_name,
            capacity_source="local:fixture-model",
            model="fixture-model",
            corpus_sources=1,
            corpus_origins=1,
            corpus_chars=len(source_text),
            outcomes=[
                LensOutcome(
                    lens="failure",
                    axis="interrogation",
                    status="ok",
                    findings=[
                        StudyFinding(
                            lens="failure",
                            axis="interrogation",
                            kind="fail_patterns",
                            title="Retries can duplicate writes without idempotency keys",
                            finding_id="failure-1",
                            payload={"claim": "State-changing retries need idempotency keys."},
                            anchors=["Retries without idempotency keys can duplicate writes."],
                            grounded_anchor_count=1,
                            corpus_shas=[source_sha],
                        )
                    ],
                )
            ],
        )

        class FakeBackend:
            capacity_source = "fixture"
            model = "fixture-model"
            cost_note = "$0 local fixture"
            chunk_chars = 8_000

            @staticmethod
            async def completion(_prompt: str) -> str:
                return ""

        async def fake_run_study(**kwargs):
            assert kwargs["corpus"].read(source_sha) == source_text
            return study

        monkeypatch.setattr(expert_study, "build_study_backend", lambda **_kwargs: FakeBackend())
        monkeypatch.setattr(expert_study, "run_study", fake_run_study)
        _invoke(runner, ["expert", "study", expert_name, "--local", "--lens", "failure", "--json"])

        brief = ExpertBrief(
            expert_name=expert_name,
            orientation="Retry safety depends on whether repeated writes are idempotent.",
            positions=[
                Position(
                    question=question,
                    stance="Retry state-changing writes only with an idempotency key.",
                    reasoning="The retained source identifies duplicate writes as the failure mode.",
                    would_change_my_mind="A transactional protocol proves duplicate requests cannot commit twice.",
                    supported_by=["failure-1"],
                    likelihood="likely",
                    confidence="moderate",
                    supporting_documents=1,
                    distinct_roots=1,
                )
            ],
            state=SettledState(
                settled=["Unprotected retries can duplicate writes."],
                live=["Which operations already provide idempotency?"],
                unknown=["Whether the target service deduplicates requests."],
            ),
            finding_titles={"failure-1": "Retries can duplicate writes without idempotency keys"},
            generated_from_findings=1,
        )

        async def fake_build_brief(**_kwargs):
            return brief

        monkeypatch.setattr("deepr.experts.brief.build_brief", fake_build_brief)
        _invoke(runner, ["expert", "brief", expert_name, "--local", "--json"])

        saved_brief = load_brief(expert_study.canonical_brief_path(expert_name))
        saved_study = load_study(expert_study.canonical_study_path(expert_name))
        context = build_consult_context(
            expert_name=expert_name,
            question=question,
            brief=saved_brief,
            result=saved_study,
            corpus=CorpusStore(expert_name),
        )
        packet = render_consult_packet(context)
        assert context.coverage == "grounded"
        assert "failure-1" in packet
        assert source_text in packet

        monkeypatch.setattr(
            expert_consult,
            "_execute_cli_consult",
            lambda **_kwargs: {
                "schema_version": "deepr-consult-v1",
                "experts_consulted": [expert_name],
                "synthesis_status": "completed",
            },
        )
        _invoke(
            runner,
            ["expert", "consult", question, "--expert", expert_name, "--local", "--json"],
        )
        provider.assert_not_called()


def test_public_docs_teach_the_complete_expert_loop_in_order():
    repo = Path(__file__).resolve().parents[3]
    for relative_path in ("README.md", "docs/QUICK_START.md"):
        text = (repo / relative_path).read_text(encoding="utf-8")
        commands = [
            "deepr expert make",
            "deepr expert retain",
            "deepr expert study",
            "deepr expert brief",
            "deepr expert consult",
        ]
        offsets = [text.index(command) for command in commands]
        assert offsets == sorted(offsets), f"{relative_path} does not teach the complete loop in order"
