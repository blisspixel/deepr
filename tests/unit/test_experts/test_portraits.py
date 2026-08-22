"""Tests for expert portrait prompt building and the consistent style preference.

Pure prompt/style logic only - no image provider is called (those paths need a
key and cost money, so they stay out of the unit suite).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from deepr.experts import portraits as P
from deepr.experts.portraits import (
    DEFAULT_PORTRAIT_STYLE,
    PORTRAIT_COST_ESTIMATE_USD,
    PORTRAIT_STYLE_ENV,
    XAI_PORTRAIT_COST_ESTIMATE_USD,
    _build_prompt,
    detect_provider,
    portrait_cost,
    portrait_style,
)


class TestLocalImageProvider:
    def test_detect_blocks_unattested_loopback_image_endpoint(self, monkeypatch):
        monkeypatch.setenv("DEEPR_LOCAL_IMAGE_URL", "http://localhost:8188")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

        with pytest.raises(RuntimeError, match="exact local-only capacity"):
            detect_provider()

    def test_detect_rejects_remote_local_url_without_metered_fallback(self, monkeypatch):
        monkeypatch.setenv("DEEPR_LOCAL_IMAGE_URL", "https://images.example.com/v1")
        monkeypatch.setenv("DEEPR_ALLOW_METERED_IMAGE_AUTO", "1")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

        with pytest.raises(RuntimeError, match=r"cannot be classified as local/\$0"):
            detect_provider()

    def test_detect_does_not_fall_back_to_metered_without_opt_in(self, monkeypatch):
        monkeypatch.delenv("DEEPR_LOCAL_IMAGE_URL", raising=False)
        monkeypatch.delenv("DEEPR_ALLOW_METERED_IMAGE_AUTO", raising=False)
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        assert detect_provider() is None

    def test_detect_falls_back_to_metered_with_explicit_auto_opt_in(self, monkeypatch):
        monkeypatch.delenv("DEEPR_LOCAL_IMAGE_URL", raising=False)
        monkeypatch.setenv("DEEPR_ALLOW_METERED_IMAGE_AUTO", "1")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        assert detect_provider() == "openai"

    def test_xai_uses_only_general_metered_auto_opt_in(self, monkeypatch):
        monkeypatch.delenv("DEEPR_LOCAL_IMAGE_URL", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        monkeypatch.delenv("DEEPR_ALLOW_METERED_IMAGE_AUTO", raising=False)
        monkeypatch.setenv("XAI_API_KEY", "xai-test")

        assert detect_provider() is None

        monkeypatch.setenv("DEEPR_ALLOW_XAI_IMAGE_AUTO", "1")

        assert detect_provider() is None

        monkeypatch.setenv("DEEPR_ALLOW_METERED_IMAGE_AUTO", "1")

        assert detect_provider() == "xai"

    def test_local_label_is_not_zero_cost_authority(self):
        with pytest.raises(RuntimeError, match="exact local-only capacity"):
            portrait_cost("local")
        assert portrait_cost("openai") == PORTRAIT_COST_ESTIMATE_USD
        assert portrait_cost("xai") == XAI_PORTRAIT_COST_ESTIMATE_USD
        assert portrait_cost(None) == PORTRAIT_COST_ESTIMATE_USD

    @pytest.mark.asyncio
    async def test_generate_local_blocks_before_client_construction(self, monkeypatch):
        monkeypatch.setenv("DEEPR_LOCAL_IMAGE_URL", "http://localhost:8188")
        monkeypatch.setenv("DEEPR_LOCAL_IMAGE_MODEL", "remote-forwarding-alias")
        constructed = False

        def fake_ctor(*_args, **_kwargs):
            nonlocal constructed
            constructed = True

        with patch("openai.AsyncOpenAI", fake_ctor):
            with pytest.raises(RuntimeError, match="exact local-only capacity"):
                await P._generate_local("a prompt")

        assert constructed is False

    @pytest.mark.asyncio
    async def test_generate_local_rejects_remote_before_client_construction(self, monkeypatch):
        monkeypatch.setenv("DEEPR_LOCAL_IMAGE_URL", "http://192.168.1.25:8188/v1")
        constructed = False

        def fake_ctor(*_args, **_kwargs):
            nonlocal constructed
            constructed = True

        with patch("openai.AsyncOpenAI", fake_ctor):
            with pytest.raises(RuntimeError, match="remote endpoints need explicit cost attestation"):
                await P._generate_local("must not run")

        assert constructed is False

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("localhost:8188", "http://127.0.0.1:8188/v1"),
            ("http://[::1]:8188/v1/", "http://[::1]:8188/v1"),
        ],
    )
    def test_local_image_url_is_canonical_loopback(self, monkeypatch, value, expected):
        monkeypatch.setenv("DEEPR_LOCAL_IMAGE_URL", value)
        assert P._local_image_base_url() == expected

    @pytest.mark.asyncio
    async def test_generate_local_requires_url(self, monkeypatch):
        monkeypatch.delenv("DEEPR_LOCAL_IMAGE_URL", raising=False)
        with pytest.raises(RuntimeError, match="DEEPR_LOCAL_IMAGE_URL"):
            await P._generate_local("a prompt")

    @pytest.mark.asyncio
    async def test_generate_portrait_defaults_to_runtime_data_root(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DEEPR_DATA_DIR", str(tmp_path / "portable-data"))
        monkeypatch.setenv("DEEPR_LOCAL_IMAGE_URL", "http://localhost:8188")
        monkeypatch.setattr(P, "_require_attested_local_image_capacity", lambda: None)

        async def fake_generate_local(_prompt):
            return b"NEWPORTRAIT"

        monkeypatch.setattr(P, "_generate_local", fake_generate_local)

        url = await P.generate_portrait("Portable Expert", provider="local")

        assert url == "/portraits/portable-expert.png"
        assert (tmp_path / "portable-data" / "portraits" / "portable-expert.png").read_bytes() == b"NEWPORTRAIT"

    @pytest.mark.asyncio
    async def test_generate_portrait_prefixes_windows_device_names(self, monkeypatch, tmp_path):
        output_dir = tmp_path / "portraits"
        monkeypatch.setenv("DEEPR_LOCAL_IMAGE_URL", "http://localhost:8188")
        monkeypatch.setattr(P, "_require_attested_local_image_capacity", lambda: None)

        async def fake_generate_local(_prompt):
            return b"DEVICEPORTRAIT"

        monkeypatch.setattr(P, "_generate_local", fake_generate_local)

        url = await P.generate_portrait("CON", provider="local", output_dir=output_dir)

        assert url == "/portraits/expert-con.png"
        assert (output_dir / "expert-con.png").read_bytes() == b"DEVICEPORTRAIT"

    @pytest.mark.asyncio
    async def test_generate_portrait_archives_existing_file_before_replacement(self, monkeypatch, tmp_path):
        output_dir = tmp_path / "portraits"
        output_dir.mkdir()
        current = output_dir / "backup-expert.png"
        current.write_bytes(b"OLDPORTRAIT")
        monkeypatch.setenv("DEEPR_LOCAL_IMAGE_URL", "http://localhost:8188")
        monkeypatch.setattr(P, "_require_attested_local_image_capacity", lambda: None)

        async def fake_generate_local(_prompt):
            return b"NEWPORTRAIT"

        monkeypatch.setattr(P, "_generate_local", fake_generate_local)

        url = await P.generate_portrait("Backup Expert", provider="local", output_dir=output_dir)

        assert url == "/portraits/backup-expert.png"
        assert current.read_bytes() == b"NEWPORTRAIT"
        archived = list((output_dir / "archive").glob("backup-expert-*.png"))
        assert len(archived) == 1
        assert archived[0].read_bytes() == b"OLDPORTRAIT"


class TestPortraitCostGate:
    @pytest.fixture(autouse=True)
    def _enable_legacy_metered_path_for_characterization(self, monkeypatch):
        from deepr.experts import metered_mutation_gate

        monkeypatch.setattr(metered_mutation_gate, "METERED_EXPERT_MUTATIONS_ENABLED", True)

    @pytest.mark.asyncio
    async def test_paid_gate_precedes_cost_reservation_and_provider(self, monkeypatch):
        from deepr.experts import cost_safety, metered_mutation_gate

        monkeypatch.setattr(metered_mutation_gate, "METERED_EXPERT_MUTATIONS_ENABLED", False)
        monkeypatch.setattr(cost_safety, "get_cost_safety_manager", lambda: pytest.fail("must not reserve"))
        monkeypatch.setattr(P, "generate_portrait", pytest.fail)

        with pytest.raises(metered_mutation_gate.MeteredExpertMutationDisabledError):
            await P.generate_and_save_portrait(SimpleNamespace(name="Paid Expert"), MagicMock(), provider="openai")

    @pytest.mark.asyncio
    async def test_generate_and_save_blocks_before_provider_spend(self, monkeypatch):
        profile = SimpleNamespace(name="Budget Expert", domain="cost", description="test")
        store = MagicMock()

        class FakeCostSafety:
            def check_and_reserve(self, **kwargs):
                assert kwargs["estimated_cost"] == PORTRAIT_COST_ESTIMATE_USD
                return False, "daily limit reached", False, ""

            def record_cost(self, **_kwargs):
                raise AssertionError("blocked portrait must not record cost")

            def refund_reservation(self, _reservation_id):
                raise AssertionError("blocked portrait must not reserve")

        async def fail_generate_portrait(**_kwargs):
            raise AssertionError("provider call should be blocked")

        import deepr.experts.cost_safety as cost_safety

        monkeypatch.setattr(cost_safety, "get_cost_safety_manager", lambda: FakeCostSafety())
        monkeypatch.setattr(P, "generate_portrait", fail_generate_portrait)

        with pytest.raises(ValueError, match="daily limit reached"):
            await P.generate_and_save_portrait(profile, store, provider="openai")

        store.save.assert_not_called()

    @pytest.mark.asyncio
    async def test_generate_and_save_settles_reserved_cost(self, monkeypatch):
        profile = SimpleNamespace(name="Budget Expert", domain="cost", description="test")
        store = MagicMock()
        records = []

        class FakeCostSafety:
            def check_and_reserve(self, **_kwargs):
                return True, "OK", False, "reservation-1"

            def record_cost(self, **kwargs):
                records.append(kwargs)
                return True

            def refund_reservation(self, _reservation_id):
                raise AssertionError("successful portrait must not refund")

        async def fake_generate_portrait(**kwargs):
            assert kwargs["provider"] == "xai"
            return "/portraits/budget-expert.png"

        import deepr.experts.cost_safety as cost_safety

        monkeypatch.setattr(cost_safety, "get_cost_safety_manager", lambda: FakeCostSafety())
        monkeypatch.setattr(P, "generate_portrait", fake_generate_portrait)

        url = await P.generate_and_save_portrait(profile, store, provider="xai")

        assert url == "/portraits/budget-expert.png"
        assert profile.portrait_url == "/portraits/budget-expert.png"
        store.save.assert_called_once_with(profile)
        assert records[0]["reservation_id"] == "reservation-1"
        assert records[0]["actual_cost"] == XAI_PORTRAIT_COST_ESTIMATE_USD
        assert records[0]["provider"] == "xai"

    @pytest.mark.asyncio
    async def test_generate_and_save_conservatively_settles_provider_failure(self, monkeypatch):
        profile = SimpleNamespace(name="Budget Expert", domain="cost", description="test")
        store = MagicMock()
        refunds = []
        records = []

        class FakeCostSafety:
            def check_and_reserve(self, **_kwargs):
                return True, "OK", False, "reservation-1"

            def record_cost(self, **kwargs):
                records.append(kwargs)
                return True

            def refund_reservation(self, reservation_id):
                refunds.append(reservation_id)

        async def fail_generate_portrait(**_kwargs):
            raise RuntimeError("provider failed")

        import deepr.experts.cost_safety as cost_safety

        monkeypatch.setattr(cost_safety, "get_cost_safety_manager", lambda: FakeCostSafety())
        monkeypatch.setattr(P, "generate_portrait", fail_generate_portrait)

        with pytest.raises(RuntimeError, match="provider failed"):
            await P.generate_and_save_portrait(profile, store, provider="openai")

        assert refunds == []
        assert records[0]["reservation_id"] == "reservation-1"
        assert records[0]["actual_cost"] == PORTRAIT_COST_ESTIMATE_USD
        assert records[0]["metadata"]["outcome"] == "failed"
        assert records[0]["metadata"]["settlement_reason"] == "provider_dispatch_or_completion_uncertain"
        store.save.assert_not_called()


class TestGoogleImageProvider:
    @pytest.mark.asyncio
    async def test_generate_google_blocks_before_http_client_construction(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "gemini-secret")
        constructed = False

        def fake_client(*_args, **_kwargs):
            nonlocal constructed
            constructed = True

        with patch("httpx.AsyncClient", fake_client):
            with pytest.raises(RuntimeError, match="durable accounting"):
                await P._generate_google("portrait prompt")

        assert constructed is False

    @pytest.mark.asyncio
    @pytest.mark.parametrize("generator", [P._generate_openai, P._generate_google, P._generate_xai])
    async def test_all_direct_metered_portrait_helpers_fail_closed(self, generator):
        with pytest.raises(RuntimeError, match="every image call"):
            await generator("portrait prompt")


def test_portrait_command_registered_on_expert_group():
    # Guards the extraction into expert_portrait.py: importing the expert group
    # must pull in and register the portrait subcommand.
    from deepr.cli.commands.semantic.experts import expert

    assert "portrait" in expert.commands


class TestPortraitCliTargetResolution:
    def test_existing_portrait_is_skipped_without_force(self):
        from deepr.cli.commands.semantic.expert_portrait import _resolve_targets

        profiles = {
            "A": SimpleNamespace(name="A", portrait_url="/portraits/a.png"),
            "B": SimpleNamespace(name="B", portrait_url=None),
        }
        store = MagicMock()
        store.list_all.return_value = list(profiles.values())
        store.load.side_effect = lambda name: profiles.get(name)

        assert _resolve_targets(store, name=None, all_experts=True, missing_only=False, force=False) == ["B"]

    def test_existing_portrait_can_be_forced(self):
        from deepr.cli.commands.semantic.expert_portrait import _resolve_targets

        profile = SimpleNamespace(name="A", portrait_url="/portraits/a.png")
        store = MagicMock()
        store.load.return_value = profile

        assert _resolve_targets(store, name="A", all_experts=False, missing_only=False, force=True) == ["A"]


class TestPortraitCliCostConfirmation:
    def test_yes_does_not_bypass_metered_cost_confirmation(self, monkeypatch):
        from deepr.cli.commands.semantic import expert_portrait as portrait_command_module
        from deepr.cli.commands.semantic.expert_portrait import expert_portrait

        profile = SimpleNamespace(name="Paid Portrait Expert", portrait_url=None)
        store = MagicMock()
        store.load.return_value = profile

        import deepr.experts.profile as profile_module

        monkeypatch.setattr(profile_module, "ExpertStore", lambda: store)
        monkeypatch.setattr(P, "detect_provider", lambda: "xai")
        monkeypatch.setattr(P, "portrait_cost", lambda _provider: XAI_PORTRAIT_COST_ESTIMATE_USD)
        monkeypatch.setattr(
            portrait_command_module,
            "_run_portrait_batch",
            lambda *_args, **_kwargs: pytest.fail("provider dispatch must be blocked"),
        )

        result = CliRunner().invoke(expert_portrait, ["Paid Portrait Expert", "--provider", "xai", "-y"])

        assert result.exit_code == 2
        assert "--confirm-metered-cost" in result.output

    def test_confirmed_paid_and_unattested_local_both_fail_closed(self, monkeypatch):
        from deepr.cli.commands.semantic import expert_portrait as portrait_command_module
        from deepr.cli.commands.semantic.expert_portrait import expert_portrait

        profile = SimpleNamespace(name="Portrait Expert", portrait_url=None)
        store = MagicMock()
        store.load.return_value = profile

        import deepr.experts.profile as profile_module

        calls = []

        async def fake_batch(*_args, **kwargs):
            calls.append(kwargs["provider"])
            return 1

        monkeypatch.setattr(profile_module, "ExpertStore", lambda: store)
        monkeypatch.setattr(portrait_command_module, "_run_portrait_batch", fake_batch)

        paid = CliRunner().invoke(
            expert_portrait,
            ["Portrait Expert", "--provider", "openai", "-y", "--confirm-metered-cost"],
        )
        local = CliRunner().invoke(expert_portrait, ["Portrait Expert", "--provider", "local", "-y"])

        assert paid.exit_code == 1
        assert "temporarily disabled" in paid.output.lower()
        assert local.exit_code != 0
        assert "exact local-only capacity" in str(local.exception)
        assert calls == []


class TestPortraitStyle:
    def test_default_when_unset(self, monkeypatch):
        monkeypatch.delenv(PORTRAIT_STYLE_ENV, raising=False)
        assert portrait_style() == DEFAULT_PORTRAIT_STYLE

    def test_env_preference_overrides_default(self, monkeypatch):
        monkeypatch.setenv(PORTRAIT_STYLE_ENV, "flat vector, muted palette")
        assert portrait_style() == "flat vector, muted palette"

    def test_explicit_override_beats_env(self, monkeypatch):
        monkeypatch.setenv(PORTRAIT_STYLE_ENV, "from env")
        assert portrait_style("explicit style") == "explicit style"

    def test_blank_override_falls_back_to_env(self, monkeypatch):
        monkeypatch.setenv(PORTRAIT_STYLE_ENV, "from env")
        assert portrait_style("   ") == "from env"


class TestBuildPrompt:
    def test_includes_style_and_domain(self, monkeypatch):
        monkeypatch.delenv(PORTRAIT_STYLE_ENV, raising=False)
        prompt = _build_prompt("Coffee Expert", domain="coffee brewing", description=None)
        assert DEFAULT_PORTRAIT_STYLE in prompt
        assert "coffee brewing" in prompt
        assert "No text or watermarks" in prompt

    def test_custom_style_is_used(self):
        prompt = _build_prompt("X", domain="y", description=None, style="woodcut print")
        assert "woodcut print" in prompt
        assert DEFAULT_PORTRAIT_STYLE not in prompt

    def test_style_is_consistent_across_experts(self, monkeypatch):
        # Same style clause for different experts -> a coherent library look.
        monkeypatch.setenv(PORTRAIT_STYLE_ENV, "isometric, pastel")
        a = _build_prompt("Expert A", domain="alpha", description=None)
        b = _build_prompt("Expert B", domain="beta", description=None)
        assert "isometric, pastel" in a
        assert "isometric, pastel" in b

    def test_subject_is_deterministic_per_name(self, monkeypatch):
        monkeypatch.delenv(PORTRAIT_STYLE_ENV, raising=False)
        assert _build_prompt("Stable Name", domain="d", description=None) == _build_prompt(
            "Stable Name", domain="d", description=None
        )
