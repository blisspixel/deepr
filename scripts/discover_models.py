#!/usr/bin/env python3
"""Model discovery utility for keeping Deepr's registry up to date.

Discovers available models from AI providers and compares against the
current registry. Two discovery modes:

1. API-based: Query provider model listing APIs directly (model names only,
   not pricing — most APIs don't expose pricing).
2. LLM-based: Ask an LLM with web access (Grok recommended) for latest
   model info including pricing. Returns structured JSON.

Usage:
    # Compare registry vs live (API mode, all providers)
    python scripts/discover_models.py

    # Check one provider
    python scripts/discover_models.py --provider openai

    # Use LLM for discovery (includes pricing)
    python scripts/discover_models.py --llm

    # Use a specific LLM provider
    python scripts/discover_models.py --llm --llm-provider grok

    # JSON output for piping
    python scripts/discover_models.py --format json

    # Show full registry
    python scripts/discover_models.py --show-registry
"""

import argparse
import json
import logging
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

# Add project root to path so we can import deepr modules
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


# ─── Data types ───────────────────────────────────────────────────────────────


@dataclass
class DiscoveredModel:
    """A model discovered from a provider API or LLM lookup."""

    provider: str
    model_id: str
    display_name: str = ""
    context_window: int = 0
    input_cost_per_1m: float = 0.0
    output_cost_per_1m: float = 0.0
    source: str = ""  # "api" or "llm"
    notes: str = ""


@dataclass
class RegistryModel:
    """A model from our current registry."""

    key: str
    provider: str
    model: str
    cost_per_query: float
    input_cost_per_1m: float
    output_cost_per_1m: float
    context_window: int


# ─── Registry loader ──────────────────────────────────────────────────────────


def load_registry() -> dict[str, RegistryModel]:
    """Load current model registry."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("registry", PROJECT_ROOT / "deepr" / "providers" / "registry.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    registry = {}
    for key, cap in mod.MODEL_CAPABILITIES.items():
        registry[key] = RegistryModel(
            key=key,
            provider=cap.provider,
            model=cap.model,
            cost_per_query=cap.cost_per_query,
            input_cost_per_1m=cap.input_cost_per_1m,
            output_cost_per_1m=cap.output_cost_per_1m,
            context_window=cap.context_window,
        )
    return registry


# ─── API-based discovery ──────────────────────────────────────────────────────


def discover_openai_models() -> list[DiscoveredModel]:
    """Discover models via OpenAI API (GET /v1/models)."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        logger.info("OPENAI_API_KEY not set, skipping OpenAI API discovery")
        return []

    import requests

    try:
        resp = requests.get(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        # Filter to relevant models (skip fine-tunes, embeddings, etc.)
        relevant_prefixes = (
            "gpt-5",
            "gpt-4.1",
            "gpt-4o",
            "gpt-4-turbo",
            "o3",
            "o4",
            "o1",
        )
        models = []
        for m in data.get("data", []):
            mid = m.get("id", "")
            if any(mid.startswith(p) for p in relevant_prefixes):
                models.append(
                    DiscoveredModel(
                        provider="openai",
                        model_id=mid,
                        display_name=mid,
                        source="api",
                    )
                )
        return sorted(models, key=lambda x: x.model_id)
    except Exception as e:
        logger.warning("OpenAI API discovery failed: %s", e)
        return []


def discover_xai_models() -> list[DiscoveredModel]:
    """Discover models via xAI API (OpenAI-compatible)."""
    api_key = os.environ.get("XAI_API_KEY")
    if not api_key:
        logger.info("XAI_API_KEY not set, skipping xAI API discovery")
        return []

    import requests

    try:
        resp = requests.get(
            "https://api.x.ai/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        models = []
        for m in data.get("data", []):
            mid = m.get("id", "")
            if "grok" in mid.lower():
                models.append(
                    DiscoveredModel(
                        provider="xai",
                        model_id=mid,
                        display_name=mid,
                        source="api",
                    )
                )
        return sorted(models, key=lambda x: x.model_id)
    except Exception as e:
        logger.warning("xAI API discovery failed: %s", e)
        return []


def discover_gemini_models() -> list[DiscoveredModel]:
    """Discover models via Gemini API."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logger.info("GEMINI_API_KEY not set, skipping Gemini API discovery")
        return []

    import requests

    try:
        resp = requests.get(
            f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}",
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        models = []
        for m in data.get("models", []):
            name = m.get("name", "").replace("models/", "")
            display = m.get("displayName", name)
            ctx = m.get("inputTokenLimit", 0)
            if any(kw in name.lower() for kw in ("gemini", "deep-research")):
                models.append(
                    DiscoveredModel(
                        provider="gemini",
                        model_id=name,
                        display_name=display,
                        context_window=ctx,
                        source="api",
                    )
                )
        return sorted(models, key=lambda x: x.model_id)
    except Exception as e:
        logger.warning("Gemini API discovery failed: %s", e)
        return []


def discover_anthropic_models() -> list[DiscoveredModel]:
    """Discover models via Anthropic API (GET /v1/models)."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.info("ANTHROPIC_API_KEY not set, skipping Anthropic API discovery")
        return []

    import requests

    try:
        resp = requests.get(
            "https://api.anthropic.com/v1/models",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        models = []
        for m in data.get("data", []):
            mid = m.get("id", "")
            display = m.get("display_name", mid)
            if "claude" in mid.lower():
                models.append(
                    DiscoveredModel(
                        provider="anthropic",
                        model_id=mid,
                        display_name=display,
                        source="api",
                    )
                )
        return sorted(models, key=lambda x: x.model_id)
    except Exception as e:
        logger.warning("Anthropic API discovery failed: %s", e)
        return []


API_DISCOVERERS = {
    "openai": discover_openai_models,
    "xai": discover_xai_models,
    "gemini": discover_gemini_models,
    "anthropic": discover_anthropic_models,
}

# Provider → (env var, signup URL) for preflight check
_PROVIDER_KEYS = {
    "openai": ("OPENAI_API_KEY", "https://platform.openai.com/api-keys"),
    "xai": ("XAI_API_KEY", "https://console.x.ai/"),
    "gemini": ("GEMINI_API_KEY", "https://aistudio.google.com/app/apikey"),
    "anthropic": ("ANTHROPIC_API_KEY", "https://console.anthropic.com/settings/keys"),
    "azure-foundry": ("AZURE_PROJECT_ENDPOINT", "https://ai.azure.com/"),
}


def preflight_check(providers: list[str] | None = None) -> dict[str, bool]:
    """Check which API keys are configured and display status.

    Returns dict of provider -> bool (True = key configured).
    """
    targets = providers or list(_PROVIDER_KEYS.keys())

    print("\n  API Key Status")
    print("  " + "-" * 56)
    print(f"  {'Provider':<18} {'Env Var':<28} {'Status':<10}")
    print("  " + "-" * 56)

    results = {}
    for provider in targets:
        env_var, url = _PROVIDER_KEYS.get(provider, (None, ""))
        if not env_var:
            continue
        has_key = bool(os.environ.get(env_var))
        results[provider] = has_key
        status = "OK" if has_key else "MISSING"
        marker = "[+]" if has_key else "[-]"
        print(f"  {marker} {provider:<15} {env_var:<28} {status}")

    print("  " + "-" * 56)

    configured = sum(1 for v in results.values() if v)
    missing = sum(1 for v in results.values() if not v)
    print(f"  {configured} configured, {missing} missing")

    if missing:
        print("\n  To add missing keys, set them in .env or environment:")
        for provider, has_key in results.items():
            if not has_key:
                env_var, url = _PROVIDER_KEYS[provider]
                print(f"    {env_var}=your-key  # Get one: {url}")

    print()
    return results


def discover_via_api(providers: list[str] | None = None) -> list[DiscoveredModel]:
    """Run API-based discovery for specified providers (or all)."""
    targets = providers or list(API_DISCOVERERS.keys())
    all_models = []
    for provider in targets:
        if provider in API_DISCOVERERS:
            print(f"  Querying {provider} API...", end=" ", flush=True)
            models = API_DISCOVERERS[provider]()
            print(f"{len(models)} models found")
            all_models.extend(models)
        else:
            logger.info("No API discoverer for provider: %s", provider)
    return all_models


# ─── LLM-based discovery ─────────────────────────────────────────────────────

LLM_DISCOVERY_PROMPT = """You are a helpful assistant that researches the latest AI model offerings.
I need you to look up the CURRENT models available from these AI providers and return structured JSON.

For each provider, list their main API models that are relevant for text generation, reasoning, and research tasks.
Skip embedding models, fine-tuning models, and deprecated models.

Providers to check:
{providers}

For each model, provide:
- provider: the provider name (openai, anthropic, gemini, xai, azure-foundry)
- model_id: the API model ID (e.g. "gpt-5", "claude-opus-4-6")
- display_name: human-readable name
- context_window: max input context in tokens (0 if unknown)
- input_cost_per_1m: cost per 1M input tokens in USD (0 if unknown)
- output_cost_per_1m: cost per 1M output tokens in USD (0 if unknown)
- notes: any important notes (e.g. "registration required", "beta", "deprecated")

Return ONLY valid JSON in this exact format, no markdown fences:
{{"models": [
  {{"provider": "openai", "model_id": "gpt-5", "display_name": "GPT-5", "context_window": 400000, "input_cost_per_1m": 1.25, "output_cost_per_1m": 10.00, "notes": "registration required"}}
]}}

Focus on models that are generally available or in public preview. Include pricing if you can find it.
Today's date is {date}. Use the most current information available."""


def discover_via_llm(
    providers: list[str] | None = None,
    llm_provider: str = "auto",
) -> list[DiscoveredModel]:
    """Discover models by asking an LLM with web access.

    Prefers Grok (real-time web access) > OpenAI > Anthropic.
    """
    import requests

    target_providers = providers or ["openai", "anthropic", "gemini", "xai"]

    # Pick LLM to use for discovery
    llm_config = _pick_llm(llm_provider)
    if not llm_config:
        print("  No LLM API key available for discovery. Set XAI_API_KEY, OPENAI_API_KEY, or ANTHROPIC_API_KEY.")
        return []

    provider_descriptions = {
        "openai": "OpenAI (GPT-5 family, GPT-4.1 family, o3/o4 reasoning models)",
        "anthropic": "Anthropic (Claude Opus, Sonnet, Haiku families)",
        "gemini": "Google Gemini (Gemini Pro, Flash, Deep Research)",
        "xai": "xAI (Grok models)",
        "azure-foundry": "Azure AI Foundry (same OpenAI models but via Azure Agent Service)",
    }
    provider_list = "\n".join(f"- {provider_descriptions.get(p, p)}" for p in target_providers)

    from datetime import date

    prompt = LLM_DISCOVERY_PROMPT.format(
        providers=provider_list,
        date=date.today().isoformat(),
    )

    print(f"  Asking {llm_config['name']} to look up latest models...", flush=True)

    try:
        models_json = _call_llm(llm_config, prompt, requests)
        models = _parse_llm_response(models_json)
        print(f"  {len(models)} models discovered via {llm_config['name']}")
        return models
    except Exception as e:
        logger.warning("LLM discovery failed: %s", e)
        return []


def _pick_llm(preference: str = "auto") -> dict | None:
    """Pick the best available LLM for discovery.

    Grok is preferred because it has real-time web access for current pricing.
    """
    options = []

    xai_key = os.environ.get("XAI_API_KEY")
    if xai_key:
        options.append(
            {
                "name": "Grok (xAI)",
                "provider": "xai",
                "api_key": xai_key,
                "base_url": "https://api.x.ai/v1",
                "model": "grok-3-mini",
                "auth_header": "Authorization",
                "auth_prefix": "Bearer ",
            }
        )

    openai_key = os.environ.get("OPENAI_API_KEY")
    if openai_key:
        options.append(
            {
                "name": "GPT-4.1-mini (OpenAI)",
                "provider": "openai",
                "api_key": openai_key,
                "base_url": "https://api.openai.com/v1",
                "model": "gpt-4.1-mini",
                "auth_header": "Authorization",
                "auth_prefix": "Bearer ",
            }
        )

    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    if anthropic_key:
        options.append(
            {
                "name": "Claude Haiku 4.5 (Anthropic)",
                "provider": "anthropic",
                "api_key": anthropic_key,
                "base_url": "https://api.anthropic.com/v1",
                "model": "claude-haiku-4-5",
                "auth_header": "x-api-key",
                "auth_prefix": "",
            }
        )

    if not options:
        return None

    if preference != "auto":
        for opt in options:
            if opt["provider"] == preference:
                return opt

    return options[0]  # Best available (grok > openai > anthropic)


def _call_llm(config: dict, prompt: str, requests_mod) -> str:
    """Call the LLM API and return the response text."""
    headers = {
        config["auth_header"]: f"{config['auth_prefix']}{config['api_key']}",
        "Content-Type": "application/json",
    }

    if config["provider"] == "anthropic":
        headers["anthropic-version"] = "2023-06-01"
        payload = {
            "model": config["model"],
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}],
        }
        url = f"{config['base_url']}/messages"
    else:
        # OpenAI-compatible (OpenAI, xAI)
        payload = {
            "model": config["model"],
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 4096,
            "temperature": 0.1,
        }
        url = f"{config['base_url']}/chat/completions"

    resp = requests_mod.post(url, headers=headers, json=payload, timeout=60)
    resp.raise_for_status()
    data = resp.json()

    if config["provider"] == "anthropic":
        return data["content"][0]["text"]
    else:
        return data["choices"][0]["message"]["content"]


def _parse_llm_response(text: str) -> list[DiscoveredModel]:
    """Parse LLM JSON response into DiscoveredModel list."""
    # Strip markdown fences if present
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first and last fence lines
        lines = [line for line in lines if not line.strip().startswith("```")]
        text = "\n".join(lines)

    data = json.loads(text)
    models = []
    for m in data.get("models", []):
        models.append(
            DiscoveredModel(
                provider=m.get("provider", ""),
                model_id=m.get("model_id", ""),
                display_name=m.get("display_name", ""),
                context_window=int(m.get("context_window", 0)),
                input_cost_per_1m=float(m.get("input_cost_per_1m", 0)),
                output_cost_per_1m=float(m.get("output_cost_per_1m", 0)),
                source="llm",
                notes=m.get("notes", ""),
            )
        )
    return models


# ─── Comparison ───────────────────────────────────────────────────────────────


def compare_registry(
    registry: dict[str, RegistryModel],
    discovered: list[DiscoveredModel],
) -> dict:
    """Compare discovered models against the current registry.

    Returns a report dict with:
    - new_models: models found but not in registry
    - pricing_changes: models where pricing differs
    - in_registry: models that match
    - registry_only: models in registry but not discovered
    """
    # Build lookup from discovered models
    discovered_lookup: dict[str, DiscoveredModel] = {}
    for m in discovered:
        # Normalize key: provider/model_id
        key = f"{m.provider}/{m.model_id}"
        discovered_lookup[key] = m

    new_models = []
    pricing_changes = []
    in_registry = []

    for key, dm in discovered_lookup.items():
        if key in registry:
            rm = registry[key]
            in_registry.append({"key": key, "discovered": dm, "registry": rm})

            # Check pricing changes (only if LLM provided pricing)
            if dm.input_cost_per_1m > 0 and rm.input_cost_per_1m > 0:
                input_diff = abs(dm.input_cost_per_1m - rm.input_cost_per_1m)
                output_diff = abs(dm.output_cost_per_1m - rm.output_cost_per_1m)
                if input_diff > 0.01 or output_diff > 0.01:
                    pricing_changes.append(
                        {
                            "key": key,
                            "registry_input": rm.input_cost_per_1m,
                            "registry_output": rm.output_cost_per_1m,
                            "discovered_input": dm.input_cost_per_1m,
                            "discovered_output": dm.output_cost_per_1m,
                        }
                    )
        else:
            # Check if any registry key contains this model ID (partial match)
            partial = [k for k in registry if dm.model_id in k]
            if not partial:
                new_models.append(dm)

    # Models in registry but not discovered
    discovered_model_ids = {m.model_id for m in discovered}
    registry_only = [rm for rm in registry.values() if rm.model not in discovered_model_ids]

    return {
        "new_models": new_models,
        "pricing_changes": pricing_changes,
        "in_registry": in_registry,
        "registry_only": registry_only,
    }


# ─── Output formatting ───────────────────────────────────────────────────────


def print_registry_table(registry: dict[str, RegistryModel]):
    """Print current registry as a table."""
    header = f"  {'Model':<38} {'$/query':>8} {'In/MTok':>8} {'Out/MTok':>9} {'Context':>9}"
    sep = "  " + "-" * 76

    print("\n  Current Model Registry")
    print(sep)
    print(header)
    print(sep)

    current_provider = ""
    for key in sorted(registry.keys()):
        rm = registry[key]
        provider = rm.provider
        if provider != current_provider:
            if current_provider:
                print(sep)
            current_provider = provider

        ctx = _format_context(rm.context_window)
        print(
            f"  {key:<38} {rm.cost_per_query:>7.3f} "
            f"${rm.input_cost_per_1m:>6.2f} ${rm.output_cost_per_1m:>7.2f} {ctx:>9}"
        )

    print(sep)
    print(f"  Total: {len(registry)} models\n")


def print_comparison_report(report: dict):
    """Print a human-readable comparison report."""
    new_models = report["new_models"]
    pricing_changes = report["pricing_changes"]
    in_registry = report["in_registry"]
    registry_only = report["registry_only"]

    # New models
    if new_models:
        print(f"\n  NEW MODELS AVAILABLE ({len(new_models)}):")
        print("  " + "─" * 66)
        for m in new_models:
            pricing = ""
            if m.input_cost_per_1m > 0:
                pricing = f"  ${m.input_cost_per_1m:.2f}/${m.output_cost_per_1m:.2f} per MTok"
            ctx = f"  {_format_context(m.context_window)}" if m.context_window else ""
            notes = f"  ({m.notes})" if m.notes else ""
            print(f"    + {m.provider}/{m.model_id}{pricing}{ctx}{notes}")
        print()

    # Pricing changes
    if pricing_changes:
        print(f"\n  PRICING CHANGES ({len(pricing_changes)}):")
        print("  " + "─" * 66)
        for pc in pricing_changes:
            print(f"    ~ {pc['key']}")
            print(f"      Registry:   ${pc['registry_input']:.2f}/${pc['registry_output']:.2f} per MTok")
            print(f"      Discovered: ${pc['discovered_input']:.2f}/${pc['discovered_output']:.2f} per MTok")
        print()

    # Summary
    print("  SUMMARY:")
    print(f"    In registry:      {len(in_registry)}")
    print(f"    New available:    {len(new_models)}")
    print(f"    Pricing changes:  {len(pricing_changes)}")
    print(f"    Registry-only:    {len(registry_only)}")

    if registry_only:
        print("\n  REGISTRY-ONLY (not found in discovery — may be fine):")
        for rm in sorted(registry_only, key=lambda x: x.key):
            print(f"    ? {rm.key}")

    if not new_models and not pricing_changes:
        print("\n  Registry is up to date!")


def _format_context(tokens: int) -> str:
    """Format token count for display."""
    if tokens >= 1_000_000:
        return f"{tokens / 1_000_000:.0f}M"
    elif tokens >= 1_000:
        return f"{tokens / 1_000:.0f}K"
    return str(tokens)


def output_json(registry: dict[str, RegistryModel], report: dict):
    """Output report as JSON."""
    result = {
        "registry_count": len(registry),
        "new_models": [asdict(m) for m in report["new_models"]],
        "pricing_changes": report["pricing_changes"],
        "matched": len(report["in_registry"]),
        "registry_only": [asdict(m) for m in report["registry_only"]],
    }
    print(json.dumps(result, indent=2))


# ─── Main ─────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Discover available AI models and compare against Deepr's registry.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/discover_models.py                    # API discovery, all providers
  python scripts/discover_models.py --llm              # LLM-based discovery (Grok preferred)
  python scripts/discover_models.py --llm --llm-provider openai  # Use OpenAI for lookup
  python scripts/discover_models.py --provider openai  # Check just OpenAI
  python scripts/discover_models.py --show-registry    # Show current registry
  python scripts/discover_models.py --format json      # JSON output
        """,
    )
    parser.add_argument(
        "--provider",
        choices=["openai", "anthropic", "gemini", "xai", "azure-foundry"],
        help="Check only this provider (default: all)",
    )
    parser.add_argument(
        "--llm",
        action="store_true",
        help="Use LLM-based discovery (asks Grok/GPT to look up latest models)",
    )
    parser.add_argument(
        "--llm-provider",
        choices=["grok", "xai", "openai", "anthropic", "auto"],
        default="auto",
        help="Which LLM to use for discovery (default: auto = Grok > OpenAI > Anthropic)",
    )
    parser.add_argument(
        "--format",
        choices=["table", "json"],
        default="table",
        help="Output format (default: table)",
    )
    parser.add_argument(
        "--show-registry",
        action="store_true",
        help="Show current registry and exit",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose logging",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Load registry
    print("Loading current registry...")
    registry = load_registry()
    print(f"  {len(registry)} models registered\n")

    if args.show_registry:
        print_registry_table(registry)
        return

    # Preflight: show which API keys are configured
    providers = [args.provider] if args.provider else None
    key_status = preflight_check(providers)

    configured_count = sum(1 for v in key_status.values() if v)
    if configured_count == 0:
        print("  No API keys configured. Set at least one key in .env to run discovery.")
        print("  See .env.example for setup instructions.")
        sys.exit(1)
    # Normalize llm_provider: "grok" -> "xai"
    llm_prov = args.llm_provider
    if llm_prov == "grok":
        llm_prov = "xai"

    if args.llm:
        print("Running LLM-based discovery...")
        discovered = discover_via_llm(providers=providers, llm_provider=llm_prov)
    else:
        print("Running API-based discovery...")
        discovered = discover_via_api(providers=providers)

    if not discovered:
        print("\n  No models discovered. Check your API keys or try --llm mode.")
        return

    # Compare
    print(f"\nComparing {len(discovered)} discovered models against registry...")
    report = compare_registry(registry, discovered)

    # Output
    if args.format == "json":
        output_json(registry, report)
    else:
        print_comparison_report(report)


if __name__ == "__main__":
    main()
