"""Tests for expert portrait prompt building and the consistent style preference.

Pure prompt/style logic only - no image provider is called (those paths need a
key and cost money, so they stay out of the unit suite).
"""

from __future__ import annotations

import base64
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
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
    def test_detect_prefers_local_when_url_set(self, monkeypatch):
        monkeypatch.setenv("DEEPR_LOCAL_IMAGE_URL", "http://localhost:8188")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")  # local still wins (cheapest-first)
        assert detect_provider() == "local"

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

    def test_xai_is_not_auto_selected_without_explicit_opt_in(self, monkeypatch):
        monkeypatch.delenv("DEEPR_LOCAL_IMAGE_URL", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        monkeypatch.delenv("DEEPR_ALLOW_METERED_IMAGE_AUTO", raising=False)
        monkeypatch.delenv("DEEPR_ALLOW_XAI_IMAGE_AUTO", raising=False)
        monkeypatch.setenv("XAI_API_KEY", "xai-test")

        assert detect_provider() is None

        monkeypatch.setenv("DEEPR_ALLOW_XAI_IMAGE_AUTO", "1")

        assert detect_provider() == "xai"

    def test_local_is_free_metered_is_not(self):
        assert portrait_cost("local") == 0.0
        assert portrait_cost("openai") == PORTRAIT_COST_ESTIMATE_USD
        assert portrait_cost("xai") == XAI_PORTRAIT_COST_ESTIMATE_USD
        assert portrait_cost(None) == PORTRAIT_COST_ESTIMATE_USD

    @pytest.mark.asyncio
    async def test_generate_local_hits_configured_endpoint(self, monkeypatch):
        monkeypatch.setenv("DEEPR_LOCAL_IMAGE_URL", "http://localhost:8188")
        captured: dict = {}
        fake_result = MagicMock()
        fake_result.data = [MagicMock(b64_json=base64.b64encode(b"IMGBYTES").decode())]
        fake_client = MagicMock()
        fake_client.images.generate = AsyncMock(return_value=fake_result)

        def fake_ctor(*_a, **kwargs):
            captured.update(kwargs)
            return fake_client

        with patch("openai.AsyncOpenAI", fake_ctor):
            out = await P._generate_local("a prompt")

        assert out == b"IMGBYTES"
        assert captured["base_url"].endswith("/v1")  # /v1 appended if missing
        assert captured["api_key"] == "local"  # nothing billed

    @pytest.mark.asyncio
    async def test_generate_local_requires_url(self, monkeypatch):
        monkeypatch.delenv("DEEPR_LOCAL_IMAGE_URL", raising=False)
        with pytest.raises(RuntimeError, match="DEEPR_LOCAL_IMAGE_URL"):
            await P._generate_local("a prompt")


class TestPortraitCostGate:
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
    async def test_generate_and_save_refunds_on_provider_failure(self, monkeypatch):
        profile = SimpleNamespace(name="Budget Expert", domain="cost", description="test")
        store = MagicMock()
        refunds = []

        class FakeCostSafety:
            def check_and_reserve(self, **_kwargs):
                return True, "OK", False, "reservation-1"

            def record_cost(self, **_kwargs):
                raise AssertionError("failed portrait must not record cost")

            def refund_reservation(self, reservation_id):
                refunds.append(reservation_id)

        async def fail_generate_portrait(**_kwargs):
            raise RuntimeError("provider failed")

        import deepr.experts.cost_safety as cost_safety

        monkeypatch.setattr(cost_safety, "get_cost_safety_manager", lambda: FakeCostSafety())
        monkeypatch.setattr(P, "generate_portrait", fail_generate_portrait)

        with pytest.raises(RuntimeError, match="provider failed"):
            await P.generate_and_save_portrait(profile, store, provider="openai")

        assert refunds == ["reservation-1"]
        store.save.assert_not_called()


class TestGoogleImageProvider:
    @pytest.mark.asyncio
    async def test_generate_google_uses_header_not_query_key(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "gemini-secret")
        captured: dict = {}

        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {"predictions": [{"bytesBase64Encoded": base64.b64encode(b"IMG").decode()}]}

        class FakeClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

            async def post(self, url, **kwargs):
                captured["url"] = url
                captured.update(kwargs)
                return FakeResponse()

        monkeypatch.setattr(httpx, "AsyncClient", FakeClient)

        assert await P._generate_google("portrait prompt") == b"IMG"
        assert "key=" not in captured["url"]
        assert captured["headers"] == {"x-goog-api-key": "gemini-secret"}

    @pytest.mark.asyncio
    async def test_generate_google_sanitizes_http_error(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "gemini-secret")
        request = httpx.Request("POST", "https://example.invalid/?key=gemini-secret")
        response = httpx.Response(403, request=request)

        class FakeResponse:
            def raise_for_status(self):
                raise httpx.HTTPStatusError("leaky url", request=request, response=response)

        class FakeClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

            async def post(self, *_args, **_kwargs):
                return FakeResponse()

        monkeypatch.setattr(httpx, "AsyncClient", FakeClient)

        with pytest.raises(RuntimeError) as excinfo:
            await P._generate_google("portrait prompt")

        assert str(excinfo.value) == "Google Imagen request failed with HTTP 403"
        assert "gemini-secret" not in str(excinfo.value)


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
