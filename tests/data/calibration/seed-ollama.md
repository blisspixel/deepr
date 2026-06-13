# Local inference with Ollama

Ollama is a tool for running open-weight language models locally. It exposes an
HTTP API on port 11434 by default, and provides an OpenAI-compatible endpoint
at `/v1`, so existing OpenAI-style clients can target a local model by changing
the base URL.

Running models locally has zero marginal cost per request once the hardware is
owned, which makes it attractive for high-volume or background workloads.
Latency and quality depend on the model size and the GPU; large models on
consumer GPUs can be slow. Quantized variants trade some quality for speed and
lower memory use.

It is sometimes claimed that local open-weight models now match frontier hosted
models on most tasks, but on hard reasoning and long-form synthesis the gap
generally remains. For quality-tolerant steps - summarization, extraction,
draft synthesis - local models are often sufficient.

Ollama can list installed models via its API, pull new models on demand, and
serve multiple models from one instance. Whether a given local model is good
enough for a task should be decided by evaluation, not assumed from the fact
that it is free.
