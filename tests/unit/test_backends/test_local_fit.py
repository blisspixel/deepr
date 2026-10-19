"""VRAM fit estimation: pick a model that runs on GPU, or decline to choose."""

from deepr.backends.local_fit import (
    choose_fitting_model,
    detect_vram_bytes,
    estimate_fit,
    model_task_hygiene_class,
    parse_param_billions,
    prefer_local_model,
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
        """KV cache grows with context, so a shorter one leaves room for weights.

        The previous assertion was `long_ctx != short_ctx or short_ctx is not
        None`, which the second clause makes unconditionally true. It passed
        whatever the function did.
        """
        long_ctx, long_est = choose_fitting_model(self._candidates(), context_tokens=65536, vram_bytes=_VRAM_24)
        short_ctx, short_est = choose_fitting_model(self._candidates(), context_tokens=4096, vram_bytes=_VRAM_24)

        assert short_ctx is not None
        assert sum(1 for e in short_est if e.fits) >= sum(1 for e in long_est if e.fits)
        if long_ctx is not None:
            long_params = next(e.params_b for e in long_est if e.name == long_ctx)
            short_params = next(e.params_b for e in short_est if e.name == short_ctx)
            assert short_params >= long_params


class TestDetectVram:
    def test_env_override_is_honoured(self, monkeypatch):
        monkeypatch.setenv("DEEPR_VRAM_BYTES", str(12 * _GB))
        assert detect_vram_bytes() == 12 * _GB

    def test_bad_override_reads_as_unknown(self, monkeypatch):
        monkeypatch.setenv("DEEPR_VRAM_BYTES", "not-a-number")
        assert detect_vram_bytes() == 0


class TestPreferLocalModel:
    def test_extraction_skips_coder_when_instruct_exists(self):
        assert model_task_hygiene_class("qwen3-coder-next") == "code"
        assert (
            prefer_local_model(
                ["qwen2.5-coder:32b", "qwen2.5:14b"],
                task_class="extraction",
            )
            == "qwen2.5:14b"
        )

    def test_entailment_refuses_coder_only_lists(self):
        assert prefer_local_model(["qwen2.5-coder:32b"], task_class="entailment") is None

    def test_extraction_keeps_coder_when_that_is_all_that_is_installed(self):
        assert prefer_local_model(["qwen3-coder-next"], task_class="extraction") == "qwen3-coder-next"

    def test_embedding_requires_an_embedding_tag(self):
        assert prefer_local_model(["qwen2.5:14b"], task_class="embedding") is None
        assert prefer_local_model(["nomic-embed-text"], task_class="embedding") == "nomic-embed-text"


# Ollama /api/show metadata for the installed models, retained 2026-10-18.
_QWEN38_27B_INFO = {
    "general.architecture": "qwen35",
    "qwen35.block_count": 65,
    "qwen35.attention.head_count": 24,
    "qwen35.attention.head_count_kv": 4,
    "qwen35.attention.key_length": 256,
    "qwen35.attention.value_length": 256,
    "qwen35.embedding_length": 5120,
    "qwen35.full_attention_interval": 4,
}
_QWEN36_35B_MOE_INFO = {
    "general.architecture": "qwen35moe",
    "qwen35moe.block_count": 41,
    "qwen35moe.attention.head_count": 16,
    "qwen35moe.attention.head_count_kv": 2,
    "qwen35moe.attention.key_length": 256,
    "qwen35moe.attention.value_length": 256,
    "qwen35moe.embedding_length": 2048,
    "qwen35moe.expert_count": 256,
    "qwen35moe.full_attention_interval": 4,
}


class TestKvFromMetadata:
    def test_hybrid_models_count_only_cached_layers(self):
        from deepr.backends.local_fit import kv_bytes_per_token

        assert kv_bytes_per_token(_QWEN38_27B_INFO) == 16 * 4 * 512 * 2
        assert kv_bytes_per_token(_QWEN36_35B_MOE_INFO) == 10 * 2 * 512 * 2

    def test_standard_attention_defaults(self):
        from deepr.backends.local_fit import kv_bytes_per_token

        info = {"general.architecture": "bert", "bert.block_count": 12, "bert.attention.head_count": 12}
        assert kv_bytes_per_token(info) is None  # no head size without embedding_length
        info["bert.embedding_length"] = 768
        assert kv_bytes_per_token(info) == 12 * 12 * (64 + 64) * 2

    def test_incomplete_or_malformed_metadata_is_unknown(self):
        from deepr.backends.local_fit import kv_bytes_per_token

        assert kv_bytes_per_token({}) is None
        assert kv_bytes_per_token({"general.architecture": "x", "x.block_count": True}) is None
        assert kv_bytes_per_token({"general.architecture": "x", "x.block_count": -3}) is None

    def test_metadata_corrects_moe_overestimate_but_never_raises_it(self):
        constant = estimate_fit(
            name="qwen3.6:35b", weight_bytes=22 * _GB, param_b=35.5, context_tokens=65536, vram_bytes=_VRAM_24 + 8 * _GB
        )
        derived = estimate_fit(
            name="qwen3.6:35b",
            weight_bytes=22 * _GB,
            param_b=35.5,
            context_tokens=65536,
            vram_bytes=_VRAM_24 + 8 * _GB,
            kv_per_token=20_480,
        )
        assert constant.kv_bytes > 38 * _GB
        assert derived.kv_bytes == 2 * 20_480 * 65536
        assert not constant.fits and derived.fits
        huge = estimate_fit(
            name="m", weight_bytes=8 * _GB, param_b=7, context_tokens=8192, vram_bytes=_VRAM_24, kv_per_token=10**7
        )
        assert huge.kv_bytes == 7 * 16_500 * 8192

    def test_chooser_uses_metadata_when_supplied(self):
        candidates = [("qwen3.6:35b", 22 * _GB, "35.5B"), ("qwen3.8:27b", 17_741_872_154, "27.3B")]
        vram = 32 * _GB
        without, _ = choose_fitting_model(candidates, context_tokens=65536, vram_bytes=vram)
        with_meta, _ = choose_fitting_model(
            candidates,
            context_tokens=65536,
            vram_bytes=vram,
            kv_per_token={"qwen3.6:35b": 20_480, "qwen3.8:27b": 65_536},
        )
        assert without is None
        assert with_meta == "qwen3.6:35b"
