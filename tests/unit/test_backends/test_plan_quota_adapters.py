"""Tests for the plan-quota adapter registry (declarative specs + argv builders)."""

from __future__ import annotations

from deepr.backends.capacity import CostModel
from deepr.backends.plan_quota.adapters import (
    REGISTRY,
    all_adapters,
    auto_routable_adapters,
    get_adapter,
    parse_reset_after_seconds,
)


class TestResetParser:
    def test_codex_hours_minutes(self):
        assert parse_reset_after_seconds("reached your 5-hour limit. Try again in 3h 42m.") == 3 * 3600 + 42 * 60

    def test_antigravity_compact(self):
        assert parse_reset_after_seconds("Individual quota reached. Resets in 2h15m30s.") == 2 * 3600 + 15 * 60 + 30

    def test_minutes_only(self):
        assert parse_reset_after_seconds("try again in 45m") == 45 * 60

    def test_monthly_no_countdown_is_none(self):
        assert parse_reset_after_seconds("[429] credits_exhausted") is None

    def test_unrelated_text_is_none(self):
        assert parse_reset_after_seconds("here is your answer in detail") is None


class TestRegistry:
    def test_all_seven_registered(self):
        assert set(REGISTRY) == {"codex", "claude", "opencode", "kiro", "grok", "antigravity", "copilot"}

    def test_auto_routable_are_only_free_at_margin_tos_clean(self):
        ids = {a.backend_id for a in auto_routable_adapters()}
        assert ids == {"codex", "claude", "opencode"}

    def test_copilot_is_metered_and_off_by_default(self):
        cp = get_adapter("copilot")
        assert cp.metered_at_margin
        assert not cp.enabled_by_default

    def test_gray_zone_backends_off_by_default(self):
        for bid in ("kiro", "grok", "antigravity"):
            assert not get_adapter(bid).enabled_by_default, bid
            assert get_adapter(bid).tos_note, bid

    def test_antigravity_flagged_experimental_and_pty(self):
        agy = get_adapter("antigravity")
        assert agy.experimental
        assert agy.needs_pty

    def test_unknown_adapter_is_none(self):
        assert get_adapter("nope") is None


class TestArgvBuilders:
    def test_codex_is_readonly_sandbox_no_approval(self):
        argv = get_adapter("codex").build_argv("what changed?")
        assert argv[:2] == ["codex", "exec"]
        assert "--sandbox" in argv and "read-only" in argv
        assert "--ask-for-approval" in argv and "never" in argv
        assert argv[-1] == "what changed?"

    def test_codex_inserts_model(self):
        argv = get_adapter("codex").build_argv("q", "gpt-5.4")
        assert "--model" in argv
        assert argv[argv.index("--model") + 1] == "gpt-5.4"
        assert argv[-1] == "q"

    def test_claude_print_mode(self):
        argv = get_adapter("claude").build_argv("q")
        assert argv == ["claude", "-p", "q"]

    def test_opencode_passes_model_as_provider_slash_model(self):
        argv = get_adapter("opencode").build_argv("q", "anthropic/claude-sonnet-4-6")
        assert argv[:2] == ["opencode", "run"]
        assert "-m" in argv
        assert argv[argv.index("-m") + 1] == "anthropic/claude-sonnet-4-6"

    def test_copilot_denies_shell_and_write(self):
        argv = get_adapter("copilot").build_argv("q")
        assert "-s" in argv
        assert "--no-ask-user" in argv
        assert "--deny-tool" in argv
        assert argv[argv.index("--deny-tool") + 1] == "shell,write"

    def test_kiro_non_interactive_readonly_tools(self):
        argv = get_adapter("kiro").build_argv("q")
        assert argv[:3] == ["kiro-cli", "chat", "--no-interactive"]
        assert "--trust-tools=read,grep" in argv


class TestParseAnswer:
    def test_strips_ansi(self):
        adapter = get_adapter("codex")
        assert adapter.parse_answer("\x1b[32mhello\x1b[0m") == "hello"

    def test_strips_code_fence(self):
        adapter = get_adapter("grok")
        assert adapter.parse_answer('```json\n{"a": 1}\n```') == '{"a": 1}'

    def test_plain_text_trimmed(self):
        assert get_adapter("claude").parse_answer("  answer  \n") == "answer"


class TestExhaustion:
    def test_codex_usage_limit(self):
        assert get_adapter("codex").looks_exhausted("Error: usage_limit_reached, try again")

    def test_kiro_credits_exhausted(self):
        assert get_adapter("kiro").looks_exhausted("[429]: ... Internal status: credits_exhausted")

    def test_clean_output_not_exhausted(self):
        assert not get_adapter("codex").looks_exhausted("here is your answer")


class TestCostModels:
    def test_window_kinds_present(self):
        for adapter in all_adapters():
            assert adapter.cost_model in CostModel
            assert adapter.unit_name
