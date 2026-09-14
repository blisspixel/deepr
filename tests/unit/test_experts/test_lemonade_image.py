"""Lemonade attested local image backend."""

from __future__ import annotations

import pytest

from deepr.experts import lemonade_image as L
from deepr.experts.portraits import detect_provider, portrait_cost


def _entry(**over):
    base = {
        "id": "SDXL-Base-1.0",
        "downloaded": True,
        "recipe": "sd-cpp",
        "checkpoint": "stabilityai/sdxl:sd_xl_base_1.0.safetensors",
        "image_defaults": {"steps": 20},
    }
    base.update(over)
    return base


class TestAttestation:
    def test_accepts_a_materialized_local_image_model(self):
        assert L._is_attested(_entry()) is True

    @pytest.mark.parametrize(
        "override",
        [
            {"downloaded": False},
            {"recipe": "llamacpp"},
            {"checkpoint": ""},
            {"image_defaults": None},
        ],
        ids=["not-downloaded", "non-image-backend", "no-checkpoint", "upscaler-not-generator"],
    )
    def test_rejects_anything_that_is_not_a_local_generator(self, override):
        assert L._is_attested(_entry(**override)) is False

    def test_cloud_backed_recipe_is_never_treated_as_owned_capacity(self):
        # `lemonade cloud` can front a paid provider behind the same API.
        assert L._is_attested(_entry(recipe="openai")) is False

    def test_unreachable_server_reports_no_model_rather_than_raising(self, monkeypatch):
        monkeypatch.setattr(L, "_list_models", lambda _root: (_ for _ in ()).throw(OSError("refused")))
        assert L.attested_model() is None
        assert L.is_available() is False

    def test_explicit_model_that_is_not_materialized_is_refused(self, monkeypatch):
        monkeypatch.setattr(L, "_list_models", lambda _root: [_entry()])
        monkeypatch.setenv(L.LEMONADE_IMAGE_MODEL_ENV, "Some-Cloud-Model")
        # Falling back to a different checkpoint would silently ignore the
        # operator's explicit choice.
        assert L.attested_model() is None

    def test_preferred_model_wins_so_a_roster_renders_as_one_set(self, monkeypatch):
        monkeypatch.delenv(L.LEMONADE_IMAGE_MODEL_ENV, raising=False)
        monkeypatch.setattr(L, "_list_models", lambda _root: [_entry(id="SD-1.5"), _entry(id="SDXL-Base-1.0")])
        selected, _checkpoint = L.attested_model()
        assert selected == "SDXL-Base-1.0"


class TestRemoteUrlRejected:
    def test_non_loopback_lemonade_url_is_not_local(self, monkeypatch):
        monkeypatch.setenv(L.LEMONADE_URL_ENV, "https://lemonade.example.com")
        with pytest.raises(RuntimeError, match=r"cannot be classified as local/\$0"):
            L.base_url()


class TestPortraitIntegration:
    def test_lemonade_is_zero_dollar(self):
        assert portrait_cost("lemonade") == 0.0

    def test_auto_detection_requires_explicit_configuration(self, monkeypatch):
        # Without the env var, detection must not probe the network at all:
        # otherwise the same command picks different backends on two machines.
        monkeypatch.delenv(L.LEMONADE_URL_ENV, raising=False)
        monkeypatch.delenv("DEEPR_LOCAL_IMAGE_URL", raising=False)
        monkeypatch.delenv("DEEPR_ALLOW_METERED_IMAGE_AUTO", raising=False)
        monkeypatch.setattr(
            L, "_list_models", lambda _root: pytest.fail("detection probed the network without configuration")
        )
        assert detect_provider() is None

    def test_configured_and_attested_server_is_selected(self, monkeypatch):
        monkeypatch.delenv("DEEPR_LOCAL_IMAGE_URL", raising=False)
        monkeypatch.setenv(L.LEMONADE_URL_ENV, "http://127.0.0.1:13305")
        monkeypatch.delenv(L.LEMONADE_IMAGE_MODEL_ENV, raising=False)
        monkeypatch.setattr(L, "_list_models", lambda _root: [_entry()])
        assert detect_provider() == "lemonade"
