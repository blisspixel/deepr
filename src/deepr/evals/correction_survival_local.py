"""Answer correction-survival prompts with an attested local model (#259).

Each prompt goes through the production consult dispatch: the council system
prompt, the native Ollama runtime, the local output budget and the study
context window. The model digest is pinned before the first call and checked
on every call, so a run cannot silently mix weights. Capacity is owned local
Ollama only; no metered client can be constructed here.
"""

from __future__ import annotations

import hashlib
import time
from typing import Any


class LocalAnswerer:
    """A digest-pinned local completion that records every call it makes."""

    def __init__(self, model: str, *, digest: str = "", timeout_seconds: float = 900.0) -> None:
        from deepr.experts.consult import build_synthesis_backend

        backend = build_synthesis_backend(use_local=True, local_model=model)
        if backend.client is None or not backend.model:
            raise RuntimeError("no owned local synthesis backend could be built")
        self.client: Any = backend.client
        self.client.timeout = timeout_seconds
        self.model: str = backend.model
        self.digest = digest
        self.calls: list[dict[str, Any]] = []

    async def attest(self) -> str:
        """Bind the run to the installed digest, or refuse if it differs from the pin."""
        observed = str(await self.client.attest_model(self.model))
        if self.digest and observed != self.digest:
            raise RuntimeError(f"installed {self.model} digest {observed} differs from the pinned {self.digest}")
        self.digest = observed
        self.client.pinned_digest = observed
        return observed

    @property
    def identity(self) -> str:
        return f"local:{self.model}@{self.digest}"

    async def __call__(self, prompt: str) -> str:
        from deepr.experts.council import LOCAL_SYNTHESIS_OUTPUT_TOKENS, SYNTHESIS_SYSTEM_PROMPT
        from deepr.experts.council_synthesis_runtime import dispatch_synthesis

        if not self.digest:
            await self.attest()
        started = time.perf_counter()
        record: dict[str, Any] = {"prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest()}
        try:
            response = await dispatch_synthesis(
                provider="local",
                model=self.model,
                client=self.client,
                openai_client_factory=None,
                system_prompt=SYNTHESIS_SYSTEM_PROMPT,
                user_prompt=prompt,
                output_tokens=LOCAL_SYNTHESIS_OUTPUT_TOKENS,
                cost_bound=None,
                pre_dispatch_callback=None,
            )
        except BaseException as error:
            record.update(status="failed", error_type=type(error).__name__)
            raise
        else:
            if self.client.last_attested_digest != self.digest:
                record.update(status="failed", error_type="DigestChanged")
                raise RuntimeError("observed local model digest changed during the run")
            record.update(
                status="returned",
                observed_digest=self.client.last_attested_digest,
                stop_reason=response.stop_reason,
                tokens_input=response.usage.get("tokens_input", 0),
                tokens_output=response.usage.get("tokens_output", 0),
                cost_usd=response.usage.get("cost", 0.0),
            )
            return response.text
        finally:
            record["elapsed_s"] = round(time.perf_counter() - started, 3)
            self.calls.append(record)
