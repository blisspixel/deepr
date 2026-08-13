"""Metered keys removed from Deepr's own process, not merely checked.

The gap this closes was found by auditing a real machine. Every key in `.env`
was renamed, and three were still live in the process - OPENAI, XAI and
ANTHROPIC - because they were set at the Windows user level and `.env` was
never their only source. Editing `.env` looks like disarming something and is
not.
"""

import pytest

from deepr.security.key_quarantine import (
    OPT_OUT_VAR,
    QUARANTINE_PREFIX,
    live_metered_names,
    quarantine_metered_keys,
    quarantined_names,
    temporarily_released_metered_keys,
)


class TestKeysAreMovedNotJustChecked:
    def test_a_metered_key_is_removed_from_the_environment(self):
        """A guard has to be reached. An absent variable cannot be read."""
        env = {"OPENAI_API_KEY": "sk-proj-live", "PATH": "/usr/bin"}

        moved = quarantine_metered_keys(env)

        assert moved == ["OPENAI_API_KEY"]
        assert "OPENAI_API_KEY" not in env
        assert env["PATH"] == "/usr/bin"

    def test_the_value_is_preserved_rather_than_destroyed(self):
        """Silently destroying a credential someone set on purpose is its own
        kind of surprise."""
        env = {"ANTHROPIC_API_KEY": "sk-ant-live"}
        quarantine_metered_keys(env)

        assert env[QUARANTINE_PREFIX + "ANTHROPIC_API_KEY"] == "sk-ant-live"

    def test_every_key_the_windows_audit_found_is_covered(self):
        """The three that survived a full .env rename on the real machine."""
        env = {"OPENAI_API_KEY": "a", "XAI_API_KEY": "b", "ANTHROPIC_API_KEY": "c"}

        quarantine_metered_keys(env)

        assert live_metered_names(env) == []

    def test_it_reaches_wider_than_the_plan_quota_adapters(self):
        """This runs in Deepr's process, where any importable SDK could read one."""
        env = {"OPENROUTER_API_KEY": "x", "MISTRAL_API_KEY": "y", "GROQ_API_KEY": "z"}
        assert len(quarantine_metered_keys(env)) == 3

    def test_a_blank_key_is_not_treated_as_present(self):
        """Blanked-out entries are the disarmed state, not something to move."""
        env = {"OPENAI_API_KEY": "", "XAI_API_KEY": "   "}
        assert quarantine_metered_keys(env) == []

    def test_non_key_variables_are_untouched(self):
        env = {"DEEPR_MAX_COST_PER_DAY": "5.0", "HOME": "/home/x"}
        quarantine_metered_keys(env)
        assert env == {"DEEPR_MAX_COST_PER_DAY": "5.0", "HOME": "/home/x"}


class TestTheEscapeHatch:
    def test_an_operator_can_opt_out_deliberately(self):
        """A safety measure with no escape hatch gets disabled wholesale."""
        env = {OPT_OUT_VAR: "1", "OPENAI_API_KEY": "sk-live"}

        assert quarantine_metered_keys(env) == []
        assert env["OPENAI_API_KEY"] == "sk-live"

    def test_the_opt_out_requires_a_truthy_value(self):
        env = {OPT_OUT_VAR: "no", "OPENAI_API_KEY": "sk-live"}
        assert quarantine_metered_keys(env) == ["OPENAI_API_KEY"]


class TestReporting:
    def test_what_was_moved_can_be_listed_back(self):
        env = {"OPENAI_API_KEY": "a", "GEMINI_API_KEY": "b"}
        quarantine_metered_keys(env)

        assert quarantined_names(env) == ["GEMINI_API_KEY", "OPENAI_API_KEY"]

    def test_live_names_is_the_honest_answer_to_can_this_bill_me(self):
        env = {"OPENAI_API_KEY": "a"}
        assert live_metered_names(env) == ["OPENAI_API_KEY"]

        quarantine_metered_keys(env)
        assert live_metered_names(env) == []

    def test_running_twice_is_a_no_op(self):
        env = {"OPENAI_API_KEY": "a"}
        quarantine_metered_keys(env)
        assert quarantine_metered_keys(env) == []
        assert env[QUARANTINE_PREFIX + "OPENAI_API_KEY"] == "a"


class TestScopedRelease:
    def test_key_is_live_only_inside_client_construction_scope(self):
        env = {"OPENAI_API_KEY": "a"}
        quarantine_metered_keys(env)

        with temporarily_released_metered_keys(env) as restored:
            assert restored == ["OPENAI_API_KEY"]
            assert env["OPENAI_API_KEY"] == "a"
            assert QUARANTINE_PREFIX + "OPENAI_API_KEY" not in env

        assert "OPENAI_API_KEY" not in env
        assert env[QUARANTINE_PREFIX + "OPENAI_API_KEY"] == "a"

    def test_only_requested_provider_key_is_released(self):
        env = {"OPENAI_API_KEY": "a", "XAI_API_KEY": "x"}
        quarantine_metered_keys(env)

        with temporarily_released_metered_keys(env, key_names=("OPENAI_API_KEY",)):
            assert env["OPENAI_API_KEY"] == "a"
            assert "XAI_API_KEY" not in env
            assert env[QUARANTINE_PREFIX + "XAI_API_KEY"] == "x"

        assert live_metered_names(env) == []

    def test_unknown_key_name_cannot_be_released(self):
        with pytest.raises(ValueError, match="known metered key"):
            with temporarily_released_metered_keys({}, key_names=("UNRELATED_SECRET",)):
                pass

    def test_exception_still_restores_quarantine(self):
        env = {"XAI_API_KEY": "x"}
        quarantine_metered_keys(env)

        try:
            with temporarily_released_metered_keys(env):
                raise RuntimeError("construction failed")
        except RuntimeError:
            pass

        assert live_metered_names(env) == []
        assert env[QUARANTINE_PREFIX + "XAI_API_KEY"] == "x"
