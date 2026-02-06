"""Test dual provider configuration (deep research vs general)."""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_default_configuration():
    """Test that default configuration uses dual providers."""
    from deepr.config import ProviderConfig

    config = ProviderConfig()

    # Verify defaults
    assert config.default_provider == "xai", "Default provider should be xai"
    assert config.default_model == "grok-4-fast", "Default model should be grok-4-fast"
    assert config.deep_research_provider == "openai", "Deep research provider should be openai"
    assert config.deep_research_model == "o3-deep-research", (
        "Deep research model should be o3-deep-research (BEST model)"
    )

    print("[OK] Default configuration verified:")
    print(f"  General operations: {config.default_provider} / {config.default_model}")
    print(f"  Deep research: {config.deep_research_provider} / {config.deep_research_model}")


def test_environment_override():
    """Test that environment variables can override defaults."""
    import os

    from deepr.config import ProviderConfig

    # Set environment variables
    os.environ["DEEPR_DEFAULT_PROVIDER"] = "gemini"
    os.environ["DEEPR_DEFAULT_MODEL"] = "gemini-2.5-flash"
    os.environ["DEEPR_DEEP_RESEARCH_PROVIDER"] = "azure"
    os.environ["DEEPR_DEEP_RESEARCH_MODEL"] = "o3-deep-research"

    config = ProviderConfig()

    # Verify overrides
    assert config.default_provider == "gemini", "Should use env var for default provider"
    assert config.default_model == "gemini-2.5-flash", "Should use env var for default model"
    assert config.deep_research_provider == "azure", "Should use env var for deep research provider"
    assert config.deep_research_model == "o3-deep-research", "Should use env var for deep research model"

    print("[OK] Environment override verified:")
    print(f"  General operations: {config.default_provider} / {config.default_model}")
    print(f"  Deep research: {config.deep_research_provider} / {config.deep_research_model}")

    # Clean up
    del os.environ["DEEPR_DEFAULT_PROVIDER"]
    del os.environ["DEEPR_DEFAULT_MODEL"]
    del os.environ["DEEPR_DEEP_RESEARCH_PROVIDER"]
    del os.environ["DEEPR_DEEP_RESEARCH_MODEL"]


def test_cost_comparison():
    """Document cost savings of using xAI for general operations."""
    print("\n[Cost Comparison]")
    print("Scenario: 10M input tokens + 10M output tokens\n")

    # GPT-5 pricing
    gpt5_input_cost = (10_000_000 / 1_000_000) * 3.00
    gpt5_output_cost = (10_000_000 / 1_000_000) * 15.00
    gpt5_total = gpt5_input_cost + gpt5_output_cost

    # xAI 4 Fast pricing
    xai_input_cost = (10_000_000 / 1_000_000) * 0.20
    xai_output_cost = (10_000_000 / 1_000_000) * 0.50
    xai_total = xai_input_cost + xai_output_cost

    print("GPT-5 (OpenAI):")
    print(f"  Input:  10M tokens × $3.00  = ${gpt5_input_cost:.2f}")
    print(f"  Output: 10M tokens × $15.00 = ${gpt5_output_cost:.2f}")
    print(f"  Total: ${gpt5_total:.2f}\n")

    print("xAI 4 Fast (xAI):")
    print(f"  Input:  10M tokens × $0.20  = ${xai_input_cost:.2f}")
    print(f"  Output: 10M tokens × $0.50  = ${xai_output_cost:.2f}")
    print(f"  Total: ${xai_total:.2f}\n")

    savings_dollars = gpt5_total - xai_total
    savings_percent = (savings_dollars / gpt5_total) * 100

    print(f"Savings: ${savings_dollars:.2f} ({savings_percent:.1f}%)")
    print(f"Cost multiplier: {gpt5_total / xai_total:.1f}x cheaper with xAI\n")


def test_use_case_routing():
    """Document which operations use which provider."""
    print("\n[Use Case Routing]")
    print("Operation                    Provider  Model")
    print("-" * 60)
    print("Deep Research                openai    o3-deep-research (BEST)")
    print("Expert Chat                  xai       grok-4-fast")
    print("Team Research                xai       grok-4-fast")
    print("Planning/Synthesis           xai       grok-4-fast")
    print("Context Summarization        xai       grok-4-fast")
    print("Link Filtering (Scraping)    xai       grok-4-fast")
    print("Document Processing          xai       grok-4-fast")
    print("\nStrategy: Use xAI for 80% of operations, OpenAI o3 for deep research")
    print("Expected total cost reduction: ~78%\n")


def run_all_tests():
    """Run all dual provider configuration tests."""
    print("=" * 70)
    print("Dual Provider Configuration Tests")
    print("=" * 70)
    print()

    try:
        test_default_configuration()
        print()
        test_environment_override()
        print()
        test_cost_comparison()
        print()
        test_use_case_routing()

        print("=" * 70)
        print("ALL TESTS PASSED")
        print("=" * 70)
        print()
        print("Dual provider configuration working correctly:")
        print("- Deep Research -> OpenAI (o3-deep-research) - BEST model")
        print("- General Operations -> xAI (grok-4-fast)")
        print("- Expected cost savings: 78%")
        print()
        return 0

    except AssertionError as e:
        print(f"\n[FAIL] {e}")
        import traceback

        traceback.print_exc()
        return 1
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(run_all_tests())
