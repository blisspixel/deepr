"""The documented local path reaches a cited, consultable expert at $0."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from click.testing import CliRunner

from deepr.cli.main import cli
from deepr.experts.brief_contracts import ExpertBrief, Position, SettledState
from deepr.experts.consult_context import build_consult_context, load_brief, load_study, render_consult_packet
from deepr.experts.corpus_store import CorpusStore, content_hash
from deepr.experts.study_contracts import LensOutcome, StudyFinding, StudyResult


def _invoke(runner: CliRunner, args: list[str]) -> str:
    result = runner.invoke(cli, args)
    assert result.exit_code == 0, f"{result.output}\n{result.exception!r}"
    return result.output


@pytest.mark.parametrize("setup", ["automatic", "chosen_sources"])
def test_documented_local_onboarding_builds_cited_consult_context(tmp_path, monkeypatch, setup):
    """Both documented creation paths produce inspectable, cited consult context."""
    from deepr.cli.commands.semantic import expert_build, expert_consult, expert_study
    from deepr.experts import formation

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
        source_sha = content_hash(source_text)

        study = StudyResult(
            expert_name=expert_name,
            capacity_source="local:fixture-model",
            model="fixture-model",
            corpus_sources=1,
            corpus_origins=1,
            corpus_chars=len(source_text),
            outcomes=[
                LensOutcome(lens="synopsis", axis="interrogation", status="ok"),
                LensOutcome(lens="mechanism", axis="interrogation", status="ok"),
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
                ),
            ],
        )

        class FakeBackend:
            capacity_source = "local:fixture-model"
            model = "fixture-model"
            cost_note = "$0 local fixture"
            chunk_chars = 8_000

            @staticmethod
            async def completion(_prompt: str) -> str:
                return ""

        async def fake_run_study(**kwargs):
            assert kwargs["corpus"].read(source_sha) == source_text
            return study

        monkeypatch.setattr(expert_build, "build_study_backend", lambda **_kwargs: FakeBackend())
        monkeypatch.setattr(formation, "run_study", fake_run_study)
        discovery = AsyncMock(side_effect=AssertionError("Discovery was explicitly disabled"))
        monkeypatch.setattr(formation, "run_search_plan", discovery)
        monkeypatch.setattr("deepr.backends.local.release_local_model", AsyncMock(return_value=True))

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

        monkeypatch.setattr(formation, "build_brief", fake_build_brief)
        make_args = ["expert", "make", expert_name, "--local", "-d", "Safe retry boundary decisions"]
        if setup == "automatic":
            build_output = _invoke(runner, [*make_args, "--files", str(source), "--no-discovery"])
        else:
            make_output = _invoke(runner, [*make_args, "--profile-only"])
            assert "Untrained profile" in make_output
            assert formation.read_formation_state(expert_name) is None
            _invoke(runner, ["expert", "retain", expert_name, str(source), "--title", "Trusted starting source"])
            build_output = _invoke(runner, ["expert", "build", expert_name, "--no-discovery"])
        assert "Formation: research_complete" in build_output
        state = formation.read_formation_state(expert_name)
        assert state["qualification"] == "not_reviewed"
        assert state["api_cost_usd"] == 0
        assert len(CorpusStore(expert_name).active_entries()) == 1
        directory = formation.canonical_expert_dir(expert_name)
        assert (directory / state["knowledge_index"]).is_file()
        assert (directory / "graph/evidence.json").is_file()
        assert (directory / "formation/runs" / state["operation_id"] / "review.md").is_file()
        _invoke(runner, ["expert", "knowledge", expert_name])
        discovery.assert_not_awaited()

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
            "deepr expert knowledge",
            "deepr expert consult",
        ]
        offsets = [text.index(command) for command in commands]
        assert offsets == sorted(offsets), f"{relative_path} does not teach the complete loop in order"
        assert "--profile-only" in text
    quick_start = (repo / "docs/QUICK_START.md").read_text(encoding="utf-8")
    chosen_sources = quick_start[quick_start.index("### Optional: Start From Chosen Sources") :]
    offsets = [
        chosen_sources.index(command) for command in ("deepr expert make", "deepr expert retain", "deepr expert build")
    ]
    assert offsets == sorted(offsets)
    assert "--no-discovery" in chosen_sources
