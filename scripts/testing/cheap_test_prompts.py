"""
Cheap test prompts for validating Deepr end-to-end functionality.

These prompts are designed to be:
- Fast (minimal research required)
- Cheap (low token usage, use o4-mini-deep-research)
- Sufficient to validate the full pipeline
"""

CHEAP_PROMPTS = [
    # Minimal research - should cost pennies
    "Write a 3-line haiku about software testing",

    # Small factual query - cheap and quick
    "List 3 benefits of cost optimization in cloud computing",

    # Tiny synthesis task - validates research flow
    "Summarize in 2 sentences: What is SQLite used for?",

    # Quick current info - validates API connectivity
    "What day of the week is it today?",

    # Small structured output - validates formatting
    "Create a bullet list of 3 programming languages and their primary use case",
]

# For programmatic testing
TEST_CONFIG = {
    "model": "o4-mini-deep-research",  # Cheapest model
    "max_cost_per_job": 1.00,  # Cap at $1 per test
    "timeout": 60,  # 1 minute max per job
}
