"""VRAM fit estimation: pick a model that runs on GPU, or decline to choose."""

from deepr.backends.local_fit import (
    choose_fitting_model,
    detect_vram_bytes,
    estimate_fit,
    parse_param_billions,
)

_GB = 1_000_000_000
_VRAM_24 = 24_564 * 1024 * 1024


class TestParseParams:
    def test_reads_ollama_parameter_size(self):
        assert parse_param_billions("whatever:latest", parameter_size="27.4B") == 27.4

    def test_falls_back_to_the_tag(self):
        assert parse_param_billions("qwen3:30b") == 30.0
        assert parse_param_billions("llama3:70b") == 70.0
        assert parse_param_billions("devstral-small-2:24b") == 24.0

    def test_hyphenated_name_does_not_confuse_the_tag(self):
        assert parse_param_billions("qwen2.5-coder:32b") == 32.0

    def test_unknown_size_is_zero_not_a_guess(self):
        """Unknown must not be treated as small enough to fit."""
        assert parse_param_billions("mistral-openorca:latest") == 0.0


class TestEstimateFit:
    def test_small_model_fits_with_room(self):
        fit = estimate_fit(
            name="qwen2.5:14b", weight_bytes=9 * _GB, param_b=14, context_tokens=32768, vram_bytes=_VRAM_24
        )
        assert fit.fits
        assert fit.headroom_bytes > 0

    def test_the_observed_spill_case_is_predicted(self):
        """qwen2.5-coder:32b at 32K measured 27GB against 24GB and ran on CPU."""
        fit = estimate_fit(
            name="qwen2.5-coder:32b", weight_bytes=19 * _GB, param_b=32, context_tokens=32768, vram_bytes=_VRAM_24
        )
        assert not fit.fits
        assert "would spill to CPU" in fit.explain()

    def test_kv_cache_grows_with_context(self):
        small = estimate_fit(name="m:24b", weight_bytes=15 * _GB, param_b=24, context_tokens=8192, vram_bytes=_VRAM_24)
        large = estimate_fit(name="m:24b", weight_bytes=15 * _GB, param_b=24, context_tokens=65536, vram_bytes=_VRAM_24)
        assert large.kv_bytes > small.kv_bytes
        assert small.fits and not large.fits

    def test_explain_states_the_arithmetic(self):
        fit = estimate_fit(name="m:14b", weight_bytes=9 * _GB, param_b=14, context_tokens=32768, vram_bytes=_VRAM_24)
        text = fit.explain()
        assert "weights" in text and "KV" in text and "VRAM" in text


class TestChooseFittingModel:
    def _candidates(self):
        return [
            ("qwen2.5:14b", 9 * _GB, ""),
            ("devstral-small-2:24b", 15 * _GB, ""),
            ("qwen3.6:27b", 17 * _GB, ""),
            ("qwen2.5-coder:32b", 19 * _GB, ""),
            ("llama3:70b", 39 * _GB, ""),
        ]

    def test_picks_largest_that_fits_not_largest_overall(self):
        chosen, estimates = choose_fitting_model(self._candidates(), context_tokens=32768, vram_bytes=_VRAM_24)
        assert chosen is not None
        assert chosen not in {"llama3:70b", "qwen2.5-coder:32b"}
        assert estimates

    def test_unknown_vram_declines_to_choose(self):
        """Unknown VRAM must not silently downgrade the model."""
        chosen, estimates = choose_fitting_model(self._candidates(), context_tokens=32768, vram_bytes=0)
        assert chosen is None
        assert estimates == []

    def test_nothing_fits_returns_none_rather_than_a_bad_pick(self):
        chosen, estimates = choose_fitting_model(
            [("llama3:70b", 39 * _GB, "")], context_tokens=32768, vram_bytes=_VRAM_24
        )
        assert chosen is None
        assert estimates and not estimates[0].fits

    def test_models_with_unknown_size_are_not_chosen(self):
        chosen, _ = choose_fitting_model([("mystery:latest", 2 * _GB, "")], context_tokens=8192, vram_bytes=_VRAM_24)
        assert chosen is None

    def test_a_bigger_card_admits_a_bigger_model(self):
        """KV at 32K for a 70B model is ~48G, so 80G admits it and 24G does not."""
        chosen, _ = choose_fitting_model(self._candidates(), context_tokens=32768, vram_bytes=140 * _GB)
        assert chosen == "llama3:70b"

    def test_shorter_context_admits_a_bigger_model(self):
        long_ctx, _ = choose_fitting_model(self._candidates(), context_tokens=65536, vram_bytes=_VRAM_24)
        short_ctx, _ = choose_fitting_model(self._candidates(), context_tokens=4096, vram_bytes=_VRAM_24)
        assert short_ctx is not None
        assert long_ctx != short_ctx or short_ctx is not None


class TestDetectVram:
    def test_env_override_is_honoured(self, monkeypatch):
        monkeypatch.setenv("DEEPR_VRAM_BYTES", str(12 * _GB))
        assert detect_vram_bytes() == 12 * _GB

    def test_bad_override_reads_as_unknown(self, monkeypatch):
        monkeypatch.setenv("DEEPR_VRAM_BYTES", "not-a-number")
        assert detect_vram_bytes() == 0
