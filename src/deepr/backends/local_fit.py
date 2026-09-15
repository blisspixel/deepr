"""Pick a local model that fits in VRAM at the context a workload needs.

Ollama will happily load a model that does not fit, silently placing the
overflow on CPU. The run stays correct and stays $0, and becomes many times
slower - a study pass that should take minutes takes hours, and from the
outside it is indistinguishable from a hang.

Deepr's default was "the first model Ollama lists", which on a machine with
several large models routinely picks one that cannot fit. This module chooses by
measured capacity instead: the largest model whose weights plus KV cache are
expected to sit entirely in VRAM at the requested context.

Estimation is deliberately conservative and cheap. Loading each candidate to
find out costs minutes per model; the arithmetic below costs nothing and errs
toward the smaller choice. Callers that need certainty can still observe the
real split afterwards with :func:`deepr.backends.local.local_model_runs_on_gpu`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# Headroom for the CUDA context, fragmentation, and the compute buffers Ollama
# allocates alongside weights. Measured spill on a 24 GB card began well before
# the nominal limit, so this is intentionally generous.
_VRAM_OVERHEAD_BYTES = 1_800_000_000

# Bytes of KV cache per token, per billion parameters, at fp16.
#
# Measured, not derived. Loading each model at 16K context and reading Ollama's
# own reported footprint gives, for (total - weights) / (params * tokens):
#
#     qwen3:30b              ~5,100 bytes/token/B
#     gemma4:26b             ~8,000
#     devstral-small-2:24b   ~9,700
#     qwen2.5-coder:32b     ~12,200
#     qwen3.6:27b           ~16,500
#     qwen2.5:14b           ~18,300
#
# The spread is real and it is not noise: KV cost scales with layer count and
# grouped-query sharing, not with parameter count, so a smaller model with
# proportionally more layers costs more per parameter than a larger one. A
# single per-parameter constant is an approximation at any value.
#
# Sit near the top of the measured range rather than at the maximum. The extreme
# is conservative to the point of being useless: at 21,000 this rejected a 24B
# model that measurably fits in 24 GB, which means recommending a weaker model
# for no reason. Mistakes in the optimistic direction are caught after load by
# `local_model_runs_on_gpu`, which observes the real split and warns; there is no
# equivalent recovery from silently never offering a model that would have run.
_KV_BYTES_PER_TOKEN_PER_B = 16_500

# Task-class hygiene. These are filename/tag conventions, not a quality verdict.
# They route which installed model is eligible for a task; they do not conclude
# that a coder model is wrong or that an instruct model is expert.
_CODER_MARKERS = ("-coder", "coder:", "codellama", "deepseek-coder", "qwen3-coder")
_THINKING_MARKERS = ("thinking", "reasoner", "qwq")
_EMBED_MARKERS = ("embed", "embedding")


def model_task_hygiene_class(name: str) -> str:
    """Classify an installed tag for task routing: instruct, code, thinking, or embedding."""
    lowered = name.lower()
    if any(marker in lowered for marker in _EMBED_MARKERS):
        return "embedding"
    if any(marker in lowered for marker in _CODER_MARKERS):
        return "code"
    if any(marker in lowered for marker in _THINKING_MARKERS):
        return "thinking"
    return "instruct"


def prefer_local_model(names: list[str], *, task_class: str = "extraction") -> str | None:
    """Pick an installed local model for a task class without probing Ollama.

    ``entailment`` / ``verification`` prefer general instruct and skip coder and
    thinking tags when an instruct model is present. ``extraction`` / ``synthesis``
    prefer instruct but will use a coder if that is all that is installed.
    ``embedding`` requires an embedding tag. Empty input returns None.
    """
    usable = [name.strip() for name in names if str(name).strip()]
    if not usable:
        return None
    classes = {name: model_task_hygiene_class(name) for name in usable}
    if task_class == "embedding":
        embeds = [name for name in usable if classes[name] == "embedding"]
        return embeds[0] if embeds else None
    instruct = [name for name in usable if classes[name] == "instruct"]
    if task_class in {"entailment", "verification"}:
        return instruct[0] if instruct else None
    if instruct:
        return instruct[0]
    non_embed = [name for name in usable if classes[name] != "embedding"]
    return non_embed[0] if non_embed else None


@dataclass(frozen=True)
class ModelFit:
    """Whether one model is expected to fit, and the arithmetic behind it."""

    name: str
    param_b: float
    weight_bytes: int
    kv_bytes: int
    total_bytes: int
    vram_bytes: int

    @property
    def fits(self) -> bool:
        return self.total_bytes + _VRAM_OVERHEAD_BYTES <= self.vram_bytes

    @property
    def headroom_bytes(self) -> int:
        return self.vram_bytes - _VRAM_OVERHEAD_BYTES - self.total_bytes

    def explain(self) -> str:
        verdict = "fits" if self.fits else "would spill to CPU"
        return (
            f"{self.name}: {self.weight_bytes / 1e9:.1f}G weights + "
            f"{self.kv_bytes / 1e9:.1f}G KV at this context = "
            f"{self.total_bytes / 1e9:.1f}G against {self.vram_bytes / 1e9:.1f}G VRAM -> {verdict}"
        )


def parse_param_billions(name: str, *, parameter_size: str = "") -> float:
    """Best-effort parameter count in billions, from Ollama metadata or the tag.

    Returns 0.0 when unknown, which callers treat as "cannot reason about fit"
    rather than "fits".
    """
    text = (parameter_size or "").strip().lower()
    if text.endswith("b"):
        try:
            return float(text[:-1])
        except ValueError:
            pass
    # Tag conventions: "qwen3:30b", "llama3:70b", "devstral-small-2:24b".
    tail = name.lower().rsplit(":", 1)[-1]
    digits = ""
    for char in tail:
        if char.isdigit() or char == ".":
            digits += char
        elif digits:
            break
    if digits and "b" in tail:
        try:
            return float(digits)
        except ValueError:
            return 0.0
    return 0.0


def estimate_fit(
    *,
    name: str,
    weight_bytes: int,
    param_b: float,
    context_tokens: int,
    vram_bytes: int,
) -> ModelFit:
    """Estimate whether weights plus KV cache fit at ``context_tokens``."""
    kv_bytes = int(param_b * context_tokens * _KV_BYTES_PER_TOKEN_PER_B) if param_b > 0 else 0
    return ModelFit(
        name=name,
        param_b=param_b,
        weight_bytes=weight_bytes,
        kv_bytes=kv_bytes,
        total_bytes=weight_bytes + kv_bytes,
        vram_bytes=vram_bytes,
    )


def detect_vram_bytes(*, reclaimable_bytes: int = 0) -> int:
    """VRAM actually available for a model, in bytes, or 0 if undeterminable.

    **Free, not total.** A desktop card is rarely idle: on the machine this was
    developed against, roughly 8 GB of a 24 GB card was already held by the
    display and other processes, so every model loaded to about 16 GB and then
    spilled. Sizing against total capacity predicts fits that do not happen.

    ``reclaimable_bytes`` is added back because it is not really taken. A model
    Ollama already has resident will be evicted to make room for the next one,
    so counting it as unavailable makes free VRAM look small, makes every
    candidate look too big, and falls back to the largest model - the exact
    opposite of the intent. This was observed: a prior run left a model loaded,
    the next run concluded nothing fit, and picked a 32B that ran half on CPU.

    Zero means "unknown", and callers must then decline to filter rather than
    guess. Silently preferring a small model on a large idle card would be its
    own quiet degradation.
    """
    override = os.getenv("DEEPR_VRAM_BYTES")
    if override:
        try:
            return int(override)
        except ValueError:
            return 0
    try:
        import shutil
        import subprocess

        # Resolve the absolute path rather than trusting PATH order, matching
        # how Deepr treats every other external binary it shells out to.
        nvidia_smi = shutil.which("nvidia-smi")
        if not nvidia_smi:
            return 0
        result = subprocess.run(  # noqa: S603 - resolved absolute path, fixed argv
            [nvidia_smi, "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return 0
        first = (result.stdout or "").strip().splitlines()[0].strip()
        return int(float(first) * 1024 * 1024) + max(0, reclaimable_bytes)
    except Exception:
        return 0


def choose_fitting_model(
    candidates: list[tuple[str, int, str]],
    *,
    context_tokens: int,
    vram_bytes: int | None = None,
) -> tuple[str | None, list[ModelFit]]:
    """Pick the largest candidate expected to fit. Returns (name, all estimates).

    ``candidates`` is (name, weight_bytes, parameter_size) as Ollama reports it.
    Largest-that-fits, because within a family more parameters generally read
    better, and the constraint that matters is not spilling.

    Returns ``(None, [])`` when VRAM is unknown, since nothing was measured and
    an estimate against an unknown budget would be invention. Returns
    ``(None, estimates)`` when VRAM is known and nothing fits, so the caller can
    show what was considered and why each candidate was rejected. Either way the
    caller keeps its existing behavior instead of silently downgrading.
    """
    vram = vram_bytes if vram_bytes is not None else detect_vram_bytes()
    if vram <= 0:
        return None, []

    estimates = [
        estimate_fit(
            name=name,
            weight_bytes=weight_bytes,
            param_b=parse_param_billions(name, parameter_size=parameter_size),
            context_tokens=context_tokens,
            vram_bytes=vram,
        )
        for name, weight_bytes, parameter_size in candidates
    ]
    fitting = [fit for fit in estimates if fit.fits and fit.param_b > 0]
    if not fitting:
        return None, estimates
    best = max(fitting, key=lambda fit: (fit.param_b, fit.weight_bytes))
    return best.name, estimates
