"""Tests for the plan-quota adapter registry (declarative specs + argv builders)."""

from __future__ import annotations

from datetime import UTC, date, datetime

from deepr.backends.capacity import CostModel
from deepr.backends.plan_quota.adapters import (
    REGISTRY,
    all_adapters,
    auto_routable_adapters,
    get_adapter,
    parse_reset_after_seconds,
    parse_reset_at_utc,
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

    def test_absolute_local_clock_becomes_future_utc(self):
        today = date(2026, 7, 11)
        now_epoch = datetime(2026, 7, 11, 15, 0, tzinfo=UTC).timestamp()

        def pacific_summer(day, hour, minute):
            return (datetime(day.year, day.month, day.day, hour + 7, minute, tzinfo=UTC).timestamp(),)

        reset = parse_reset_at_utc(
            "You've hit your usage limit. Try again at 9:20 AM.",
            now_epoch=now_epoch,
            local_date=today,
            wall_time_resolver=pacific_summer,
        )

        assert reset == datetime(2026, 7, 11, 16, 20, tzinfo=UTC)

    def test_absolute_clock_rolls_to_next_day_with_new_dst_offset(self):
        today = date(2026, 10, 31)
        now_epoch = datetime(2026, 10, 31, 17, 0, tzinfo=UTC).timestamp()

        def pacific_transition(day, hour, minute):
            offset = 7 if day == today else 8
            return (datetime(day.year, day.month, day.day, hour + offset, minute, tzinfo=UTC).timestamp(),)

        reset = parse_reset_at_utc(
            "try again at 9:20 a.m.",
            now_epoch=now_epoch,
            local_date=today,
            wall_time_resolver=pacific_transition,
        )

        assert reset == datetime(2026, 11, 1, 17, 20, tzinfo=UTC)

    def test_ambiguous_dst_clock_returns_none(self):
        today = date(2026, 11, 1)
        now_epoch = datetime(2026, 11, 1, 7, 0, tzinfo=UTC).timestamp()

        def ambiguous(_day, _hour, _minute):
            return (
                datetime(2026, 11, 1, 8, 30, tzinfo=UTC).timestamp(),
                datetime(2026, 11, 1, 9, 30, tzinfo=UTC).timestamp(),
            )

        assert (
            parse_reset_at_utc(
                "try again at 1:30 AM",
                now_epoch=now_epoch,
                local_date=today,
                wall_time_resolver=ambiguous,
            )
            is None
        )

    def test_nonexistent_or_unavailable_local_clock_returns_none(self):
        assert (
            parse_reset_at_utc(
                "try again at 2:30 AM",
                now_epoch=datetime(2026, 3, 8, 8, 0, tzinfo=UTC).timestamp(),
                local_date=date(2026, 3, 8),
                wall_time_resolver=lambda _day, _hour, _minute: (),
            )
            is None
        )

    def test_relative_reset_uses_same_utc_contract(self):
        now = datetime(2026, 7, 11, 15, 0, tzinfo=UTC)
        assert parse_reset_at_utc("try again in 45m", now_epoch=now.timestamp()) == datetime(
            2026, 7, 11, 15, 45, tzinfo=UTC
        )


class TestRegistry:
    def test_all_seven_registered(self):
        assert set(REGISTRY) == {"codex", "claude", "opencode", "kiro", "grok", "antigravity", "copilot"}

    def test_auto_routable_are_only_free_at_margin_tos_clean(self):
        ids = {a.backend_id for a in auto_routable_adapters()}
        assert ids == {"codex", "claude"}

    def test_copilot_is_metered_and_off_by_default(self):
        cp = get_adapter("copilot")
        assert cp.metered_at_margin
        assert not cp.enabled_by_default

    def test_opencode_is_explicit_only_because_provider_cost_is_ambiguous(self):
        adapter = get_adapter("opencode")
        assert not adapter.enabled_by_default
        assert "OPENAI_API_KEY" in adapter.metered_env_vars
        assert "ANTHROPIC_API_KEY" in adapter.metered_env_vars
        assert "explicit-only" in adapter.tos_note

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
        assert "-c" in argv and 'approval_policy="never"' in argv
        assert argv[-1] == "what changed?"

    def test_codex_inserts_model(self):
        argv = get_adapter("codex").build_argv("q", "gpt-5.4")
        assert "--model" in argv
        assert argv[argv.index("--model") + 1] == "gpt-5.4"
        assert argv[-1] == "q"

    def test_claude_print_mode(self):
        argv = get_adapter("claude").build_argv("q")
        assert argv == ["claude", "-p", "q"]

    def test_claude_uses_stdin_delivery(self):
        # A multi-line synthesis prompt passed as a claude.cmd command-line arg is
        # mangled by cmd.exe on Windows, so claude silently sees an empty task.
        # The prompt must go over stdin instead (`claude -p -`).
        adapter = get_adapter("claude")
        assert adapter.stdin_prompt is True
        assert adapter.build_argv("-") == ["claude", "-p", "-"]

    def test_opencode_passes_model_as_provider_slash_model(self):
        argv = get_adapter("opencode").build_argv("q", "anthropic/claude-sonnet-4-6")
        assert argv[:2] == ["opencode", "run"]
        assert "-m" in argv
        assert argv[argv.index("-m") + 1] == "anthropic/claude-sonnet-4-6"

    def test_grok_reads_prompt_from_file(self):
        # A long research/synthesis prompt as a -p arg hits the Windows command
        # line limit (WinError 206), so grok must read it from a file.
        adapter = get_adapter("grok")
        assert adapter.prompt_is_file is True
        argv = adapter.build_argv("/tmp/deepr-plan-xyz.txt")
        assert "-p" not in argv
        assert argv[-2:] == ["--prompt-file", "/tmp/deepr-plan-xyz.txt"]

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

    def test_codex_current_usage_limit_is_error_channel_only(self):
        adapter = get_adapter("codex")
        message = "You've hit your usage limit. Try again at 9:20 AM."
        assert not adapter.looks_exhausted(message)
        assert adapter.looks_error_channel_exhausted(message)
        assert adapter.looks_error_channel_exhausted(message.replace("You've", "You\u2019ve"))

    def test_kiro_credits_exhausted(self):
        assert get_adapter("kiro").looks_exhausted("[429]: ... Internal status: credits_exhausted")

    def test_clean_output_not_exhausted(self):
        assert not get_adapter("codex").looks_exhausted("here is your answer")


class TestCostModels:
    def test_window_kinds_present(self):
        for adapter in all_adapters():
            assert adapter.cost_model in CostModel
            assert adapter.unit_name
