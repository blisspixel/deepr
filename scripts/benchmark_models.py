#!/usr/bin/env python3
"""Tiered model quality benchmark for validating Deepr's auto-mode routing table.

FOUR TIERS:
  Chat     -- Training data knowledge, reasoning, docs (16 models, chat completions)
  News     -- Web search, freshness, citations (8 models: OpenAI + Grok + Gemini)
  Research -- Multi-source reports (3 deep research + 8 web-search-augmented models)
  Docs     -- Technical documentation extraction (8 models, web search + structure)

Four phases per tier:
  1. Preflight -- Load registry, check API keys, select models, estimate cost
  2. Evaluate  -- Send each prompt to each model, capture response + latency + citations
  3. Judge     -- Use cheap LLM to score each response (tier-specific dimensions)
  4. Report    -- Per-tier rankings, cross-tier routing recommendations

ACTUAL COSTS (2026-02-13 baseline):
  Chat:      ~$0.81   (17 models x 18 prompts, chat completions)
  News:      ~$0.17   (8 models x 6 prompts, web search + grounding)
  Research:  ~$0.50   (3 deep + 8 web-search models x 4 prompts)
  Docs:      ~$0.30   (8 models x 5 prompts, web search)
  All:       ~$1.78

CHECKPOINT / RESUME:
  Every eval result is auto-saved to data/benchmarks/.checkpoint.json.
  If a run crashes (network, timeout, Ctrl+C), resume with --resume:
    python scripts/benchmark_models.py --tier all --resume
  Completed evals are skipped, new ones pick up where you left off.
  The checkpoint is cleared after a successful run.

HOW TO USE:
  1. Validate:    python scripts/benchmark_models.py --validate
  2. Dry run:     python scripts/benchmark_models.py --dry-run --tier all
  3. Quick test:  python scripts/benchmark_models.py --tier news --quick --no-judge
  4. Full run:    python scripts/benchmark_models.py --tier all --save
  5. Resume:      python scripts/benchmark_models.py --tier all --resume --save
  6. Single model: python scripts/benchmark_models.py --model openai/gpt-5 --save
  7. Compare:     python scripts/benchmark_models.py --compare data/benchmarks/old.json

SCORING:
  Chat:     0.70 x judge + 0.30 x reference_match
  News:     0.60 x judge + 0.40 x citation_score (count + domain diversity)
  Research: 0.50 x judge + 0.50 x citation_score (count + diversity + length + structure)
  Docs:     0.55 x judge + 0.45 x citation_score (count + diversity + code examples + structure)

Full documentation: docs/BENCHMARKS.md
"""

import argparse
import importlib.util
import json
import logging
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load .env for API keys
try:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass  # dotenv not installed, rely on environment variables

logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


# ─── Data types ───────────────────────────────────────────────────────────────


@dataclass
class EvalPrompt:
    """A single evaluation prompt."""

    task_type: str
    difficulty: str
    prompt: str
    expected_contains: list[str]
    max_tokens: int = 500
    tier: str = "chat"


@dataclass
class EvalResult:
    """Result of evaluating one prompt against one model."""

    model_key: str  # provider/model
    task_type: str
    difficulty: str
    prompt: str
    response: str
    latency_ms: int
    error: str = ""
    tier: str = "chat"

    # Scoring
    judge_score: float = 0.0  # 0-1 weighted composite
    reference_score: float = 0.0  # 0-1 fraction of expected terms found
    combined_score: float = 0.0
    judge_details: dict = field(default_factory=dict)

    # Citation/research fields (news + research tiers)
    citation_count: int = 0
    citation_score: float = 0.0
    citations: list = field(default_factory=list)
    report_length: int = 0


@dataclass
class ModelSummary:
    """Aggregated results for one model."""

    model_key: str
    avg_quality: float = 0.0
    avg_latency_ms: float = 0.0
    total_cost: float = 0.0
    cost_per_quality: float = 0.0
    scores_by_type: dict = field(default_factory=dict)
    num_evals: int = 0
    errors: int = 0
    tier: str = "chat"


# ─── Eval prompt set ─────────────────────────────────────────────────────────

# Prompts are designed to test what actually matters for Deepr research output.
# Each task type has a different definition of "good":
#   - quick_lookup: Concise, correct, no fluff. Speed matters.
#   - technical_docs: Thorough, well-structured, citable details. Depth matters.
#   - knowledge_base: Accurate domain knowledge from training. Correctness matters.
#   - synthesis: Connects dots across topics, structured comparison. Insight matters.
#   - reasoning: Sound logic, considers tradeoffs, actionable. Rigor matters.
#   - document_analysis: Extracts signal from noise, identifies patterns. Precision matters.

EVAL_PROMPTS = [
    # ── Quick Lookups ─────────────────────────────────────────────────────
    # Good = concise, correct, fast. Not a 3-page essay.
    EvalPrompt(
        task_type="quick_lookup",
        difficulty="easy",
        prompt="What is the default port for PostgreSQL and what configuration file controls it?",
        expected_contains=["5432", "postgresql.conf"],
    ),
    EvalPrompt(
        task_type="quick_lookup",
        difficulty="easy",
        prompt="What HTTP status code means 'Too Many Requests' and what header indicates when to retry?",
        expected_contains=["429", "retry-after"],
    ),
    EvalPrompt(
        task_type="quick_lookup",
        difficulty="medium",
        prompt="What are the ACID properties in database transactions? One sentence each.",
        expected_contains=["atomicity", "consistency", "isolation", "durability"],
    ),
    # ── Technical Documentation ───────────────────────────────────────────
    # Good = thorough, structured, includes gotchas and examples.
    # A great answer is detailed and well-organized, not just long.
    EvalPrompt(
        task_type="technical_docs",
        difficulty="medium",
        prompt=(
            "Document how Python's asyncio event loop works. Cover: what it is, "
            "how coroutines are scheduled, the difference between tasks and futures, "
            "and common pitfalls when mixing sync and async code."
        ),
        expected_contains=["event loop", "coroutine", "await", "task", "future", "blocking"],
    ),
    EvalPrompt(
        task_type="technical_docs",
        difficulty="hard",
        prompt=(
            "Write a technical guide on implementing rate limiting for a REST API. "
            "Cover: token bucket vs sliding window algorithms, where to enforce limits "
            "(API gateway vs app), storage backends (Redis vs in-memory), handling "
            "distributed systems, and what response headers to return (429, Retry-After)."
        ),
        expected_contains=["token bucket", "sliding window", "redis", "429", "retry-after", "distributed"],
    ),
    EvalPrompt(
        task_type="technical_docs",
        difficulty="hard",
        prompt=(
            "Explain the tradeoffs of different database indexing strategies: B-tree, "
            "hash, GIN, and GiST indexes. For each, explain when to use it, what "
            "queries it accelerates, and what it costs in terms of write performance "
            "and storage. Use PostgreSQL as the reference implementation."
        ),
        expected_contains=["b-tree", "hash", "gin", "gist", "write", "storage", "postgresql"],
    ),
    # ── Knowledge Base (Domain Expertise) ────────────────────────────────
    # Good = accurate domain knowledge, specific details, no hallucination.
    # Tests training data quality — what the model actually "knows" —
    # which is what matters for expert chat and knowledge base building.
    # NOTE: No web access. Tests training data only.
    EvalPrompt(
        task_type="knowledge_base",
        difficulty="medium",
        prompt=(
            "Explain the CAP theorem in distributed systems. For each of the three "
            "properties (Consistency, Availability, Partition tolerance), give a "
            "concrete example of a database that prioritizes it and what it sacrifices."
        ),
        expected_contains=["consistency", "availability", "partition", "cp", "ap"],
    ),
    EvalPrompt(
        task_type="knowledge_base",
        difficulty="hard",
        prompt=(
            "Describe the differences between OAuth 2.0 authorization code flow, "
            "client credentials flow, and PKCE. For each: when to use it, what "
            "tokens are involved, and what security risks it mitigates."
        ),
        expected_contains=["authorization code", "client credentials", "pkce", "token", "redirect"],
    ),
    EvalPrompt(
        task_type="knowledge_base",
        difficulty="hard",
        prompt=(
            "Explain how TLS 1.3 handshake works compared to TLS 1.2. What was "
            "removed, what was added, and why is it faster? Include the number "
            "of round trips for each."
        ),
        expected_contains=["handshake", "round trip", "1-rtt", "cipher", "forward secrecy"],
    ),
    # ── Research Synthesis ────────────────────────────────────────────────
    # Good = connects ideas across domains, structured comparison,
    # actionable conclusions. Not just listing facts.
    EvalPrompt(
        task_type="synthesis",
        difficulty="medium",
        prompt=(
            "Compare the approaches to AI safety taken by OpenAI, Anthropic, and "
            "Google DeepMind. What are each organization's core safety frameworks, "
            "how do they differ in philosophy, and where do they agree?"
        ),
        expected_contains=["alignment", "safety", "anthropic", "openai", "deepmind"],
    ),
    EvalPrompt(
        task_type="synthesis",
        difficulty="hard",
        prompt=(
            "Analyze the tradeoffs between using a managed vector database (Pinecone, "
            "Weaviate Cloud) vs self-hosted (pgvector, Milvus) for a RAG system "
            "processing 10M documents. Consider: cost at scale, query latency, "
            "operational complexity, vendor lock-in, and data privacy requirements."
        ),
        expected_contains=["vector", "cost", "latency", "scale", "privacy"],
    ),
    EvalPrompt(
        task_type="synthesis",
        difficulty="hard",
        prompt=(
            "A SaaS company needs to choose between three architectures for their "
            "multi-tenant system: schema-per-tenant in PostgreSQL, row-level security "
            "in a shared schema, or a separate database per tenant. They have 500 "
            "tenants today and expect 5,000 in 2 years. Analyze each approach across "
            "cost, isolation, migration complexity, and operational overhead."
        ),
        expected_contains=["schema", "tenant", "isolation", "migration", "cost"],
    ),
    # ── Reasoning & Analysis ──────────────────────────────────────────────
    # Good = sound logic, considers edge cases, weighs tradeoffs,
    # arrives at a defensible recommendation.
    EvalPrompt(
        task_type="reasoning",
        difficulty="medium",
        prompt=(
            "A startup has $50K/month cloud budget and is choosing between AWS Lambda "
            "(serverless) and ECS Fargate (containers) for their API backend handling "
            "10,000 requests/minute with spiky traffic (10x during peak hours). "
            "Which should they choose and why? Consider cost, cold starts, and scaling."
        ),
        expected_contains=["lambda", "fargate", "cold start", "cost", "scale"],
    ),
    EvalPrompt(
        task_type="reasoning",
        difficulty="hard",
        prompt=(
            "You're designing an LLM-powered research system that needs to process "
            "queries ranging from simple factual lookups ($0.01) to deep multi-source "
            "research ($2.00). Design a routing strategy that minimizes cost while "
            "maintaining quality. How would you classify query complexity, what models "
            "would you assign to each tier, and how would you handle uncertainty in "
            "classification?"
        ),
        expected_contains=["routing", "complexity", "cost", "model", "tier", "fallback"],
    ),
    EvalPrompt(
        task_type="reasoning",
        difficulty="hard",
        prompt=(
            "A company is experiencing 99.5% uptime but needs 99.99%. Their current "
            "architecture is: single-region deployment, PostgreSQL primary with one "
            "replica, Redis cache, and a load balancer. What changes would you "
            "recommend, in what order, and what are the cost/complexity tradeoffs "
            "of each change?"
        ),
        expected_contains=["multi-region", "failover", "redundancy", "monitoring"],
    ),
    # ── Document Analysis ─────────────────────────────────────────────────
    # Good = extracts the right signal, identifies patterns, gives
    # precise answers from the provided data.
    EvalPrompt(
        task_type="document_analysis",
        difficulty="medium",
        prompt=(
            "Analyze this API response time data and identify the problem:\n"
            "```\n"
            "Endpoint: POST /api/research/submit\n"
            "  Mon 09:00  avg=120ms  p95=340ms  p99=890ms   errors=0.1%\n"
            "  Mon 14:00  avg=145ms  p95=380ms  p99=950ms   errors=0.2%\n"
            "  Tue 09:00  avg=130ms  p95=350ms  p99=910ms   errors=0.1%\n"
            "  Tue 14:00  avg=890ms  p95=2100ms p99=4500ms  errors=3.2%\n"
            "  Wed 09:00  avg=125ms  p95=345ms  p99=900ms   errors=0.1%\n"
            "  Wed 14:00  avg=920ms  p95=2300ms p99=5100ms  errors=4.1%\n"
            "```\n"
            "What pattern do you see? What are the likely causes? What would you "
            "investigate first?"
        ),
        expected_contains=["afternoon", "pattern", "load", "spike"],
    ),
    EvalPrompt(
        task_type="document_analysis",
        difficulty="medium",
        prompt=(
            "Review this cost breakdown and recommend where to cut:\n"
            "```\n"
            "Monthly AI API Costs - January 2025\n"
            "  openai/o3-deep-research:     $1,240  (62 queries, avg $20.00)\n"
            "  openai/gpt-5:                  $180  (1,200 queries, avg $0.15)\n"
            "  openai/gpt-4.1-mini:            $45  (4,500 queries, avg $0.01)\n"
            "  xai/grok-4-fast:                $12  (1,200 queries, avg $0.01)\n"
            "  gemini/gemini-2.5-flash:          $8  (4,000 queries, avg $0.002)\n"
            "  Total: $1,485\n"
            "```\n"
            "Which line item has the biggest optimization opportunity? What "
            "specific changes would you recommend?"
        ),
        expected_contains=["o3", "deep-research", "expensive", "route"],
    ),
    EvalPrompt(
        task_type="document_analysis",
        difficulty="hard",
        prompt=(
            "Given these error logs from a distributed system, identify the root cause "
            "and explain the failure cascade:\n"
            "```\n"
            "10:23:01 [service-a] INFO  Request received: job_id=j-4521\n"
            "10:23:01 [service-a] INFO  Forwarding to service-b for enrichment\n"
            "10:23:02 [service-b] WARN  Redis connection pool: 48/50 active\n"
            "10:23:03 [service-b] ERROR Redis ETIMEDOUT after 5000ms\n"
            "10:23:03 [service-b] WARN  Falling back to database lookup\n"
            "10:23:08 [service-b] ERROR Database query timeout after 5000ms\n"
            "10:23:08 [service-a] ERROR Upstream timeout from service-b after 10000ms\n"
            "10:23:08 [service-a] WARN  Circuit breaker opened for service-b\n"
            "10:23:09 [service-c] ERROR service-a returned 503 for callback\n"
            "10:23:09 [service-c] WARN  Retrying job j-4521 (attempt 2/3)\n"
            "10:23:10 [service-a] WARN  Rejecting request: circuit breaker open\n"
            "10:23:10 [service-c] ERROR All retries exhausted for job j-4521\n"
            "10:23:10 [service-c] INFO  Moving job j-4521 to dead letter queue\n"
            "```\n"
            "What is the root cause? What is the failure cascade sequence? "
            "What would you fix first?"
        ),
        expected_contains=["redis", "pool", "cascade", "circuit breaker", "timeout"],
    ),
]

# ─── News eval prompts (web search tier) ─────────────────────────────────────

NEWS_EVAL_PROMPTS = [
    # ── Freshness ─────────────────────────────────────────────────────────
    # Good = genuinely recent info from live web, not stale training data.
    EvalPrompt(
        task_type="freshness",
        difficulty="medium",
        prompt=(
            "What are the most recent major AI model releases in the last 30 days? "
            "Include the model name, releasing company, and approximate release date. "
            "Focus on foundation models, not fine-tunes or minor updates."
        ),
        expected_contains=["2025", "model", "release"],
        max_tokens=800,
        tier="news",
    ),
    EvalPrompt(
        task_type="freshness",
        difficulty="medium",
        prompt=(
            "What are the current API pricing rates for the major LLM providers "
            "(OpenAI, Anthropic, Google)? List the flagship model from each provider "
            "with input and output cost per million tokens."
        ),
        expected_contains=["price", "token", "million", "input", "output"],
        max_tokens=800,
        tier="news",
    ),
    # ── Citation Quality ──────────────────────────────────────────────────
    # Good = real, verifiable source URLs (not hallucinated).
    EvalPrompt(
        task_type="citation_quality",
        difficulty="medium",
        prompt=(
            "Summarize the most important recent research papers on AI agent safety. "
            "For each paper, provide the title, authors, and a URL to the paper. "
            "Focus on papers from 2024-2025."
        ),
        expected_contains=["safety", "paper", "http"],
        max_tokens=1000,
        tier="news",
    ),
    EvalPrompt(
        task_type="citation_quality",
        difficulty="medium",
        prompt=(
            "What is the current market capitalization and AI strategy of NVIDIA, "
            "Microsoft, and Google/Alphabet? Cite your sources with URLs."
        ),
        expected_contains=["market cap", "http", "billion"],
        max_tokens=1000,
        tier="news",
    ),
    # ── Source Diversity ───────────────────────────────────────────────────
    # Good = pulls from multiple domains, not just one source.
    EvalPrompt(
        task_type="source_diversity",
        difficulty="hard",
        prompt=(
            "What is the current state of quantum computing? Cover: recent hardware "
            "milestones, software frameworks, commercial availability, and remaining "
            "challenges. Cite diverse sources."
        ),
        expected_contains=["qubit", "quantum", "http"],
        max_tokens=1000,
        tier="news",
    ),
    EvalPrompt(
        task_type="source_diversity",
        difficulty="hard",
        prompt=(
            "Summarize the current global landscape of AI regulation. Cover the EU AI Act, "
            "US executive orders, China's AI regulations, and UK's approach. "
            "Cite sources from different domains."
        ),
        expected_contains=["regulation", "EU", "http"],
        max_tokens=1000,
        tier="news",
    ),
]

# ─── Research eval prompts (deep research tier) ──────────────────────────────

RESEARCH_EVAL_PROMPTS = [
    # ── Comprehensive Research ────────────────────────────────────────────
    # Good = 10+ sources, structured report, thorough analysis.
    EvalPrompt(
        task_type="comprehensive_research",
        difficulty="hard",
        prompt=(
            "Write a comprehensive comparison of the top LLM-powered code generation "
            "tools available today (GitHub Copilot, Cursor, Claude Code, Windsurf, etc). "
            "Compare: capabilities, supported languages, pricing, IDE integration, "
            "accuracy benchmarks, and user adoption. Use at least 10 sources and "
            "structure your report with clear headings."
        ),
        expected_contains=["copilot", "cursor", "code", "comparison"],
        max_tokens=4000,
        tier="research",
    ),
    EvalPrompt(
        task_type="comprehensive_research",
        difficulty="hard",
        prompt=(
            "Research the impact of AI on software engineering jobs over the next 5 years. "
            "Cover: current adoption rates, productivity studies, job market data, "
            "skill shifts, new roles created, and expert predictions. Use at least 10 "
            "sources and provide a structured report with executive summary."
        ),
        expected_contains=["software", "jobs", "AI", "productivity"],
        max_tokens=4000,
        tier="research",
    ),
    # ── Multi-Source Synthesis ─────────────────────────────────────────────
    # Good = cross-references multiple sources, identifies agreements/conflicts.
    EvalPrompt(
        task_type="multi_source_synthesis",
        difficulty="hard",
        prompt=(
            "Analyze the current state of AI evaluation and benchmarking. Cover: "
            "major benchmarks (MMLU, HumanEval, GPQA, etc), their limitations, "
            "emerging alternatives, contamination concerns, and how organizations "
            "actually evaluate models in practice. Synthesize findings from "
            "academic papers, industry blogs, and benchmark leaderboards."
        ),
        expected_contains=["benchmark", "evaluation", "MMLU"],
        max_tokens=4000,
        tier="research",
    ),
    EvalPrompt(
        task_type="multi_source_synthesis",
        difficulty="hard",
        prompt=(
            "Write a technical guide on RAG (Retrieval-Augmented Generation) architecture "
            "best practices in 2025. Cover: chunking strategies, embedding models, "
            "vector databases, reranking, hybrid search, evaluation metrics, and "
            "common failure modes. Synthesize from technical blogs, papers, and "
            "production case studies."
        ),
        expected_contains=["RAG", "retrieval", "embedding", "chunk"],
        max_tokens=4000,
        tier="research",
    ),
]

# ─── Documentation eval prompts (docs tier) ─────────────────────────────────
# Tests ability to fetch, extract, and structure real developer documentation.
# Good = detailed API reference, code examples, accurate params, cited sources.

DOCS_EVAL_PROMPTS = [
    EvalPrompt(
        task_type="api_reference",
        difficulty="hard",
        prompt=(
            "Document the Cloudflare Workers AI API for running inference on serverless GPUs. "
            "Cover: REST API endpoints, supported model types (LLMs, image generation, embeddings, "
            "speech-to-text), request/response formats, authentication (API tokens + account ID), "
            "streaming responses, rate limits, and pricing tiers. "
            "Include code examples using fetch and the Workers AI binding. "
            "Cite official Cloudflare documentation."
        ),
        expected_contains=["workers", "inference", "model", "api"],
        max_tokens=3000,
        tier="docs",
    ),
    EvalPrompt(
        task_type="api_reference",
        difficulty="hard",
        prompt=(
            "Document Azure AI Foundry's agent capabilities, focusing on the web search tool. "
            "Cover: creating an agent with web search, Bing grounding integration, the "
            "tool definition schema, how search results are returned in the conversation, "
            "Python SDK usage (azure-ai-projects), authentication setup, and pricing. "
            "Include working code examples. Cite Microsoft Learn docs."
        ),
        expected_contains=["agent", "web_search", "azure", "bing"],
        max_tokens=3000,
        tier="docs",
    ),
    EvalPrompt(
        task_type="sdk_documentation",
        difficulty="hard",
        prompt=(
            "Document the ElevenLabs Text-to-Speech API in detail. "
            "Cover: all voice settings (stability, similarity_boost, style, speaker_boost), "
            "available models (Turbo v2.5, Multilingual v2, Flash), streaming vs non-streaming, "
            "output formats (mp3, pcm, opus), voice cloning endpoints, pronunciation dictionaries, "
            "websocket streaming API, and rate limits. Include Python code examples. "
            "Cite elevenlabs.io documentation."
        ),
        expected_contains=["text-to-speech", "voice", "stability", "streaming"],
        max_tokens=3000,
        tier="docs",
    ),
    EvalPrompt(
        task_type="sdk_documentation",
        difficulty="hard",
        prompt=(
            "Document Vercel's AI SDK (ai package) for building AI applications. "
            "Cover: core concepts (generateText, streamText, generateObject), provider setup "
            "(OpenAI, Anthropic, Google), tool calling, structured output with Zod schemas, "
            "streaming UI components (useChat, useCompletion), middleware, "
            "and multi-step agent loops. Include TypeScript code examples. "
            "Cite vercel.com/docs and sdk.vercel.ai documentation."
        ),
        expected_contains=["generateText", "streamText", "useChat", "provider"],
        max_tokens=3000,
        tier="docs",
    ),
    EvalPrompt(
        task_type="integration_guide",
        difficulty="hard",
        prompt=(
            "Document Stripe's Payment Intents API for accepting online payments. "
            "Cover: creating PaymentIntents, confirming payments, handling 3D Secure, "
            "webhook events (payment_intent.succeeded, payment_intent.payment_failed), "
            "idempotency keys, error handling, test mode vs live mode, and PCI compliance. "
            "Include code examples in Python (stripe library) and JavaScript (stripe-node). "
            "Cite stripe.com/docs."
        ),
        expected_contains=["PaymentIntent", "webhook", "stripe", "3D Secure"],
        max_tokens=3000,
        tier="docs",
    ),
]

# ─── Default model set ────────────────────────────────────────────────────────

# Chat-tier models: standard chat completions API.
# Default: one model per routing tier. Tests the routing table, not duplicates.
# Azure Foundry runs the same models as OpenAI — test it separately for latency.
DEFAULT_MODELS = [
    # Frontier models
    "openai/gpt-5.2",  # Frontier enterprise reasoning, 400K context ($0.30/query)
    "anthropic/claude-opus-4-6",  # Most capable Claude ($0.80/query)
    "gemini/gemini-3-pro-preview",  # Newest gen, best quality ($0.20/query)
    "gemini/gemini-2.5-pro",  # Thinking model, can't disable thinking ($0.15/query)
    # Mid-tier
    "anthropic/claude-sonnet-4-5",  # Strong reasoning ($0.48/query)
    "openai/gpt-4.1",  # 1M context ($0.04/query)
    "openai/o3",  # Reasoning model for complex tasks ($0.10/query)
    "openai/o4-mini",  # Fast reasoning ($0.04/query)
    # Budget models
    "openai/gpt-5-mini",  # Budget reasoning ($0.03/query)
    "openai/gpt-4.1-mini",  # Cheap 1M context ($0.01/query)
    "openai/gpt-5-nano",  # Cheapest GPT-5 ($0.005/query)
    "openai/gpt-4.1-nano",  # Cheapest 1M context ($0.003/query)
    "xai/grok-4-fast",  # Cheapest overall ($0.01/query)
    "gemini/gemini-3-flash-preview",  # Newest gen, fast ($0.01/query)
    "gemini/gemini-2.5-flash",  # Cheapest Gemini ($0.005/query)
    "anthropic/claude-haiku-4-5",  # Budget Anthropic ($0.05/query)
]

EXPENSIVE_MODELS: list[str] = [
    # Reserved for future very expensive models
]

NEWS_MODELS = [
    # OpenAI (via Responses API web_search tool)
    "openai/gpt-5.2",
    "openai/gpt-5-mini",
    # xAI (native web search)
    "xai/grok-4-1-fast-reasoning",
    "xai/grok-4-fast-reasoning",
    # Gemini (Google grounding)
    "gemini/gemini-3-flash-preview",
    "gemini/gemini-3-pro-preview",
    "gemini/gemini-2.5-flash",
    "gemini/gemini-2.5-pro",
]

RESEARCH_MODELS = [
    "openai/o3-deep-research",
    "openai/o4-mini-deep-research",
    "gemini/deep-research",
]
_DEEP_RESEARCH_NAMES: set[str] = {m.split("/", 1)[1] for m in RESEARCH_MODELS}

# Web-search-augmented research models (no native deep research, but can do
# multi-source synthesis via web search tools). Scored with research judge.
ORCHESTRATED_RESEARCH_MODELS = [
    # OpenAI (Responses API + web_search)
    "openai/gpt-5.2",
    "openai/o3",
    "openai/gpt-5-mini",
    # Gemini (google_search grounding)
    "gemini/gemini-3-pro-preview",
    "gemini/gemini-2.5-pro",
    # xAI (Responses API + web_search)
    "xai/grok-4-1-fast-reasoning",
    "xai/grok-4-fast-reasoning",
]

# Documentation tier models: web-search-capable models that can fetch + document APIs.
DOCS_MODELS = [
    "openai/gpt-5.2",
    "openai/gpt-5-mini",
    "openai/o3",
    "gemini/gemini-3-pro-preview",
    "gemini/gemini-2.5-pro",
    "xai/grok-4-1-fast-reasoning",
    "xai/grok-4-fast-reasoning",
]

# Provider → (env var, API base URL)
_PROVIDER_CONFIG = {
    "openai": ("OPENAI_API_KEY", "https://api.openai.com/v1"),
    "xai": ("XAI_API_KEY", "https://api.x.ai/v1"),
    "gemini": ("GEMINI_API_KEY", "https://generativelanguage.googleapis.com"),
    "anthropic": ("ANTHROPIC_API_KEY", "https://api.anthropic.com/v1"),
    "azure-foundry": ("AZURE_PROJECT_ENDPOINT", ""),  # Endpoint IS the base URL
}

# Azure Foundry deployment name mappings (deployment name may differ from model name)
# Discovered via: az cognitiveservices account deployment list
_AZURE_DEPLOYMENT_MAP = {
    "gpt-4.1": "gpt-4.1",
    "gpt-4.1-mini": "gpt-4.1-mini",
    "gpt-5": "gpt-5-chat",
    "gpt-5-mini": "gpt-5-mini",
    "gpt-4o": "gpt-4o",
    "gpt-4o-mini": "gpt-4o-mini",
}

_AZURE_API_VERSION = "2024-10-01-preview"


# ─── Registry loader ─────────────────────────────────────────────────────────


def load_registry():
    """Load current model registry via importlib."""
    spec = importlib.util.spec_from_file_location("registry", PROJECT_ROOT / "deepr" / "providers" / "registry.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.MODEL_CAPABILITIES


# ─── Preflight ────────────────────────────────────────────────────────────────


def check_api_keys() -> dict[str, bool]:
    """Check which provider API keys are configured."""
    return {provider: bool(os.environ.get(env_var)) for provider, (env_var, _) in _PROVIDER_CONFIG.items()}


def select_models(
    args,
    registry: dict,
    key_status: dict[str, bool],
    tier: str = "chat",
) -> list[str]:
    """Select which models to benchmark based on args, tier, and available keys."""
    if args.model:
        # Single model specified
        return [args.model]

    if tier == "news":
        candidates = list(NEWS_MODELS)
    elif tier == "research":
        # Deep research only: models with native background-research APIs
        candidates = list(RESEARCH_MODELS)
    elif tier == "docs":
        candidates = list(DOCS_MODELS)
    else:
        candidates = list(DEFAULT_MODELS)
        if args.include_expensive:
            candidates.extend(EXPENSIVE_MODELS)

    # Filter by provider if specified
    if args.provider:
        candidates = [m for m in candidates if m.startswith(f"{args.provider}/")]

    # Filter to models with configured API keys
    available = []
    for model_key in candidates:
        provider = model_key.split("/")[0]
        if key_status.get(provider, False):
            available.append(model_key)

    return available


def _is_thinking_model(model_key: str) -> bool:
    """Check if a model uses thinking/reasoning tokens (billed as output)."""
    model = model_key.split("/", 1)[1] if "/" in model_key else model_key
    return (
        model.startswith("gpt-5")
        or model.startswith("gpt-6")
        or model.startswith("o3")
        or model.startswith("o4")
        or model.startswith("gemini-2.5")
        or model.startswith("gemini-3")
    )


def estimate_cost(models: list[str], prompts: list[EvalPrompt], registry: dict) -> float:
    """Estimate total cost for the benchmark run.

    Token estimates by tier:
      Chat:     ~400 in, ~450 out (+500 thinking for reasoning models)
      News:     ~400 in, ~800 out (+500 thinking, web search adds ~20%)
      Research: ~2000 in, ~15000 out (deep research uses massive token budgets)

    Models not in registry (e.g. grok-4-fast-reasoning) use a fallback estimate.
    """
    # Per-query fallback cost for models not in registry
    _FALLBACK_COST = {
        "news": 0.02,  # ~$0.02 per news query
        "research": 1.50,  # ~$1.50 per deep research query
        "docs": 0.03,  # ~$0.03 per docs query
        "chat": 0.005,
    }

    total = 0.0
    for model_key in models:
        # Azure Foundry models share pricing with their OpenAI equivalents
        lookup_key = model_key
        if model_key.startswith("azure-foundry/"):
            lookup_key = "openai/" + model_key.split("/", 1)[1]
        cap = registry.get(lookup_key) or registry.get(model_key)

        for ep in prompts:
            if cap:
                if ep.tier == "research":
                    # Deep research uses massive budgets; orchestrated uses web search
                    model_name = model_key.split("/", 1)[1] if "/" in model_key else model_key
                    if model_name in _DEEP_RESEARCH_NAMES:
                        input_cost = (2000 / 1_000_000) * cap.input_cost_per_1m
                        output_cost = (15000 / 1_000_000) * cap.output_cost_per_1m
                        per_eval = input_cost + output_cost
                    else:
                        input_cost = (600 / 1_000_000) * cap.input_cost_per_1m
                        output_tokens = 2500 + (500 if _is_thinking_model(model_key) else 0)
                        output_cost = (output_tokens / 1_000_000) * cap.output_cost_per_1m
                        per_eval = (input_cost + output_cost) * 1.2
                elif ep.tier == "docs":
                    # Docs: ~600 input, ~2000 output + web search overhead
                    input_cost = (600 / 1_000_000) * cap.input_cost_per_1m
                    output_tokens = 2000 + (500 if _is_thinking_model(model_key) else 0)
                    output_cost = (output_tokens / 1_000_000) * cap.output_cost_per_1m
                    per_eval = (input_cost + output_cost) * 1.2
                elif ep.tier == "news":
                    # News: ~400 input, ~800 output + web search overhead
                    input_cost = (400 / 1_000_000) * cap.input_cost_per_1m
                    output_tokens = 800 + (500 if _is_thinking_model(model_key) else 0)
                    output_cost = (output_tokens / 1_000_000) * cap.output_cost_per_1m
                    per_eval = (input_cost + output_cost) * 1.2  # 20% web search overhead
                else:
                    # Chat: ~400 input, ~450 output
                    input_cost = (400 / 1_000_000) * cap.input_cost_per_1m
                    output_tokens = 450 + (500 if _is_thinking_model(model_key) else 0)
                    output_cost = (output_tokens / 1_000_000) * cap.output_cost_per_1m
                    per_eval = input_cost + output_cost
                total += per_eval
            else:
                # Model not in registry — use fallback
                total += _FALLBACK_COST.get(ep.tier, 0.005)
    return total


# ─── API callers ──────────────────────────────────────────────────────────────


def call_openai_compatible(
    api_key: str, base_url: str, model: str, prompt: str, max_tokens: int
) -> tuple[str, int, list[dict]]:
    """Call OpenAI-compatible API (OpenAI, xAI). Returns (response_text, latency_ms, citations).

    GPT-5 family models require 'max_completion_tokens' instead of 'max_tokens'.
    We detect this and use the right parameter.
    """
    import requests

    # Reasoning models (GPT-5+, o3, o4-mini) require different parameters:
    #   - max_completion_tokens instead of max_tokens (and it includes BOTH
    #     reasoning + output tokens, so we need headroom for thinking)
    #   - temperature is fixed at 1 (any other value is rejected)
    #   - reasoning_effort controls thinking token budget
    is_reasoning = (
        model.startswith("gpt-5")
        or model.startswith("gpt-6")
        or model.startswith("o3")
        or model.startswith("o4")
    )

    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }
    if is_reasoning:
        # max_completion_tokens = reasoning + output combined.
        # Low effort keeps benchmarks fast (~5-15s) while still scoreable.
        body["max_completion_tokens"] = max(max_tokens * 2, 2048)
        body["reasoning_effort"] = "low"
    else:
        body["max_tokens"] = max_tokens
        body["temperature"] = 0.1

    # Safety-net timeout (reasoning_effort=low usually returns in 5-15s)
    req_timeout = 180 if is_reasoning else 60

    start = time.monotonic()
    resp = requests.post(
        f"{base_url}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=body,
        timeout=req_timeout,
    )
    latency_ms = int((time.monotonic() - start) * 1000)
    resp.raise_for_status()
    data = resp.json()
    text = data["choices"][0]["message"]["content"]
    return text, latency_ms, []


def call_anthropic(api_key: str, model: str, prompt: str, max_tokens: int) -> tuple[str, int, list[dict]]:
    """Call Anthropic API. Returns (response_text, latency_ms, citations)."""
    import requests

    start = time.monotonic()
    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=60,
    )
    latency_ms = int((time.monotonic() - start) * 1000)
    resp.raise_for_status()
    data = resp.json()
    text = data["content"][0]["text"]
    return text, latency_ms, []


def call_gemini(api_key: str, model: str, prompt: str, max_tokens: int) -> tuple[str, int, list[dict]]:
    """Call Gemini API. Returns (response_text, latency_ms, citations).

    Gemini 2.5+ and 3.x are "thinking" models that spend tokens on internal
    reasoning before producing output.  Pro models (2.5-pro, 3-pro) cannot
    disable thinking, so we must give them a large enough token budget.
    Flash models can have thinking disabled via thinkingBudget=0 for cheaper,
    faster benchmark calls.
    """
    import requests

    # Gemini counts thinking tokens toward maxOutputTokens.  Pro models
    # (2.5-pro, 3-pro) can't disable thinking and routinely spend 500-2000
    # tokens reasoning.  Flash models think dynamically.  Give both enough
    # headroom so thinking doesn't eat the whole budget.
    is_pro = "pro" in model
    thinking_headroom = 3072 if is_pro else 2048
    gen_config: dict = {"maxOutputTokens": max(max_tokens + thinking_headroom, 4096)}

    start = time.monotonic()
    resp = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}",
        headers={"Content-Type": "application/json"},
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": gen_config,
        },
        timeout=120,  # Pro thinking models can be slow
    )
    latency_ms = int((time.monotonic() - start) * 1000)
    resp.raise_for_status()
    data = resp.json()

    # Handle thinking models that may spend all tokens on reasoning
    # and return candidates with no text parts.
    candidates = data.get("candidates", [])
    if not candidates:
        raise ValueError(f"Gemini returned no candidates: {json.dumps(data)[:200]}")

    content = candidates[0].get("content", {})
    parts = content.get("parts", [])
    if not parts:
        finish = candidates[0].get("finishReason", "unknown")
        thought_tokens = data.get("usageMetadata", {}).get("thoughtsTokenCount", 0)
        raise ValueError(
            f"Gemini returned no text (finishReason={finish}, "
            f"thoughtTokens={thought_tokens}). Model may need higher maxOutputTokens."
        )

    text = parts[0].get("text", "")
    return text, latency_ms, []


def call_azure_foundry(endpoint: str, model: str, prompt: str, max_tokens: int) -> tuple[str, int, list[dict]]:
    """Call Azure AI Foundry (OpenAI-compatible with api-key auth). Returns (response_text, latency_ms, citations)."""
    import requests

    # Map model name to deployment name
    deployment = _AZURE_DEPLOYMENT_MAP.get(model, model)

    # Get API key via az CLI or env var
    api_key = os.environ.get("AZURE_FOUNDRY_API_KEY", "")
    if not api_key:
        # Try to get key from Azure CLI
        import subprocess

        try:
            result = subprocess.run(
                [
                    "az",
                    "cognitiveservices",
                    "account",
                    "keys",
                    "list",
                    "--name",
                    endpoint.split("//")[1].split(".")[0],
                    "--resource-group",
                    os.environ.get("AZURE_RESOURCE_GROUP", "testagents"),
                    "--query",
                    "key1",
                    "--output",
                    "tsv",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                api_key = result.stdout.strip()
        except Exception:
            pass

    if not api_key:
        raise ValueError("Azure Foundry API key not found. Set AZURE_FOUNDRY_API_KEY or ensure az CLI is configured.")

    endpoint_url = endpoint.rstrip("/")
    start = time.monotonic()
    resp = requests.post(
        f"{endpoint_url}/openai/deployments/{deployment}/chat/completions?api-version={_AZURE_API_VERSION}",
        headers={"api-key": api_key, "Content-Type": "application/json"},
        json={
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": 0.1,
        },
        timeout=60,
    )
    latency_ms = int((time.monotonic() - start) * 1000)
    resp.raise_for_status()
    data = resp.json()
    text = data["choices"][0]["message"]["content"]
    return text, latency_ms, []


def call_openai_news(api_key: str, model: str, prompt: str, max_tokens: int) -> tuple[str, int, list[dict]]:
    """Call OpenAI Responses API with web_search tool for news queries. Returns (text, latency_ms, citations)."""
    import requests

    body: dict = {
        "model": model,
        "input": prompt,
        "tools": [{"type": "web_search"}],
    }
    # GPT-5+ reasoning models need max_output_tokens with headroom for thinking
    is_reasoning = (
        model.startswith("gpt-5")
        or model.startswith("gpt-6")
        or model.startswith("o3")
        or model.startswith("o4")
    )
    if is_reasoning:
        body["max_output_tokens"] = max(max_tokens * 2, 4096)
        body["reasoning"] = {"effort": "low"}
    else:
        body["max_output_tokens"] = max_tokens

    start = time.monotonic()
    resp = requests.post(
        "https://api.openai.com/v1/responses",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=body,
        timeout=180 if is_reasoning else 120,
    )
    latency_ms = int((time.monotonic() - start) * 1000)
    resp.raise_for_status()
    data = resp.json()

    # Extract text from output blocks
    text = data.get("output_text", "")
    if not text:
        for block in data.get("output", []):
            if block.get("type") == "message":
                for item in block.get("content", []):
                    if item.get("type") == "output_text":
                        text += item.get("text", "")

    # Extract citations from annotations
    citations = []
    for block in data.get("output", []):
        for item in block.get("content", []):
            for ann in item.get("annotations", []):
                if ann.get("type") == "url_citation":
                    citations.append({"url": ann.get("url", ""), "title": ann.get("title", "")})

    return text, latency_ms, citations


def call_grok_news(api_key: str, model: str, prompt: str, max_tokens: int) -> tuple[str, int, list[dict]]:
    """Call Grok via xAI Responses API with web_search tool. Returns (text, latency_ms, citations)."""
    import requests

    body = {
        "model": model,
        "input": prompt,
        "tools": [{"type": "web_search"}],
        "max_output_tokens": max_tokens,
    }

    start = time.monotonic()
    resp = requests.post(
        "https://api.x.ai/v1/responses",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=body,
        timeout=120,
    )
    latency_ms = int((time.monotonic() - start) * 1000)
    resp.raise_for_status()
    data = resp.json()

    # Extract text from output blocks
    text = data.get("output_text", "")
    if not text:
        for block in data.get("output", []):
            if block.get("type") == "message":
                for item in block.get("content", []):
                    if item.get("type") == "output_text":
                        text += item.get("text", "")

    # Extract citations
    citations = []
    for cite in data.get("citations", []):
        citations.append({"url": cite.get("url", ""), "title": cite.get("title", "")})

    # Also check output blocks for URL citations (annotations)
    for block in data.get("output", []):
        for item in block.get("content", []):
            for ann in item.get("annotations", []):
                if ann.get("type") == "url_citation":
                    citations.append({"url": ann.get("url", ""), "title": ann.get("title", "")})

    return text, latency_ms, citations


def call_gemini_news(api_key: str, model: str, prompt: str, max_tokens: int) -> tuple[str, int, list[dict]]:
    """Call Gemini generateContent with google_search grounding. Returns (text, latency_ms, citations)."""
    import requests

    is_pro = "pro" in model
    thinking_headroom = 3072 if is_pro else 2048
    gen_config: dict = {"maxOutputTokens": max(max_tokens + thinking_headroom, 4096)}

    start = time.monotonic()
    resp = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}",
        headers={"Content-Type": "application/json"},
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": gen_config,
            "tools": [{"google_search": {}}],
        },
        timeout=120,
    )
    latency_ms = int((time.monotonic() - start) * 1000)
    resp.raise_for_status()
    data = resp.json()

    candidates = data.get("candidates", [])
    if not candidates:
        raise ValueError(f"Gemini returned no candidates: {json.dumps(data)[:200]}")

    content = candidates[0].get("content", {})
    parts = content.get("parts", [])
    text = parts[0].get("text", "") if parts else ""

    # Extract citations from groundingMetadata
    citations = []
    grounding = candidates[0].get("groundingMetadata", {})
    for chunk in grounding.get("groundingChunks", []):
        web = chunk.get("web", {})
        if web:
            citations.append({"url": web.get("uri", ""), "title": web.get("title", "")})

    return text, latency_ms, citations


def call_openai_deep_research(api_key: str, model: str, prompt: str, max_tokens: int) -> tuple[str, int, list[dict]]:
    """Call OpenAI Responses API in background mode for deep research. Returns (text, latency_ms, citations).

    Submits a background job, polls until completed. Timeout: 1200s (20 min).
    """
    import requests

    # Model name mapping
    model_map = {
        "o3-deep-research": "o3-deep-research-2025-06-26",
        "o4-mini-deep-research": "o4-mini-deep-research",
    }
    api_model = model_map.get(model, model)

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    # Submit background job
    body = {
        "model": api_model,
        "input": prompt,
        "background": True,
        "tools": [{"type": "web_search_preview"}],
        "store": True,
    }

    start = time.monotonic()
    resp = requests.post("https://api.openai.com/v1/responses", headers=headers, json=body, timeout=60)
    resp.raise_for_status()
    job = resp.json()
    job_id = job["id"]

    # Poll until completed (max 3600s = 60 min; some deep research jobs take 45+)
    poll_interval = 10
    timeout = 3600
    while True:
        elapsed = time.monotonic() - start
        if elapsed > timeout:
            raise TimeoutError(
                f"OpenAI deep research timed out after {timeout}s. "
                f"Job {job_id} may still be running — check with: "
                f"GET https://api.openai.com/v1/responses/{job_id}"
            )

        time.sleep(poll_interval)
        # Ramp up interval: 10s for first 2 min, 20s up to 10 min, then 30s
        if elapsed > 600:
            poll_interval = 30
        elif elapsed > 120:
            poll_interval = 20

        poll_resp = requests.get(f"https://api.openai.com/v1/responses/{job_id}", headers=headers, timeout=30)
        poll_resp.raise_for_status()
        status_data = poll_resp.json()

        status = status_data.get("status", "")
        if status == "completed":
            break
        elif status in ("failed", "cancelled"):
            error = status_data.get("error", {}).get("message", status)
            raise RuntimeError(f"OpenAI deep research {status}: {error}")
        # else: in_progress, queued — keep polling

    latency_ms = int((time.monotonic() - start) * 1000)

    # Extract report text and citations from output
    text = ""
    citations = []
    for block in status_data.get("output", []):
        for item in block.get("content", []):
            if item.get("type") in ("output_text", "text"):
                text += item.get("text", "")
            # Collect URL citation annotations
            for ann in item.get("annotations", []):
                if ann.get("type") == "url_citation":
                    citations.append({"url": ann.get("url", ""), "title": ann.get("title", "")})

    return text, latency_ms, citations


def call_gemini_deep_research(api_key: str, prompt: str) -> tuple[str, int, list[dict]]:
    """Call Gemini Deep Research via Interactions API. Returns (text, latency_ms, citations).

    Submits a background interaction, polls until completed. Timeout: 1200s (20 min).
    """
    import requests

    agent = "deep-research-pro-preview-12-2025"
    base = "https://generativelanguage.googleapis.com/v1beta"
    headers = {"Content-Type": "application/json"}

    # Submit background interaction
    body = {
        "input": prompt,
        "agent": agent,
        "background": True,
    }

    start = time.monotonic()
    resp = requests.post(f"{base}/interactions?key={api_key}", headers=headers, json=body, timeout=60)
    resp.raise_for_status()
    interaction = resp.json()
    interaction_id = interaction.get("id") or interaction.get("name", "").split("/")[-1]

    # Poll until completed (max 3600s = 60 min; some jobs take 45+)
    timeout = 3600
    while True:
        elapsed = time.monotonic() - start
        if elapsed > timeout:
            raise TimeoutError(
                f"Gemini deep research timed out after {timeout}s. "
                f"Interaction {interaction_id} may still be running."
            )

        # Adaptive polling: 5s → 10s → 20s → 30s
        if elapsed < 60:
            time.sleep(5)
        elif elapsed < 300:
            time.sleep(10)
        elif elapsed < 600:
            time.sleep(20)
        else:
            time.sleep(30)

        poll_resp = requests.get(f"{base}/interactions/{interaction_id}?key={api_key}", timeout=30)
        poll_resp.raise_for_status()
        status_data = poll_resp.json()

        status = status_data.get("status", "")
        if status == "completed":
            break
        elif status == "failed":
            error = status_data.get("error", {}).get("message", "unknown error")
            raise RuntimeError(f"Gemini deep research failed: {error}")

    latency_ms = int((time.monotonic() - start) * 1000)

    # Extract text and citations from outputs
    # The Interactions API response structure can vary — try multiple paths:
    #   - outputs[].text (primary)
    #   - outputs[].content[].text (alternate)
    #   - outputs[].groundingMetadata.groundingChunks (grounding citations)
    #   - outputs[].citations (direct citations array)
    #   - Inline markdown links in the report text itself
    text = ""
    citations = []
    for output in status_data.get("outputs", []):
        # Text extraction: try direct .text first, then .content[].text
        if output.get("text"):
            text += output["text"]
        for part in output.get("content", []):
            if isinstance(part, dict) and part.get("text"):
                text += part["text"]

        # Citations path 1: groundingMetadata.groundingChunks
        grounding = output.get("groundingMetadata", {})
        for chunk in grounding.get("groundingChunks", []):
            web = chunk.get("web", {})
            if web:
                citations.append({"url": web.get("uri", ""), "title": web.get("title", "")})

        # Citations path 2: direct citations array
        for cite in output.get("citations", []):
            url = cite.get("url", "") or cite.get("uri", "")
            if url:
                citations.append({"url": url, "title": cite.get("title", "")})

        # Citations path 3: groundingMetadata.webSearchQueries (at least shows search was done)
        for query in grounding.get("webSearchQueries", []):
            if isinstance(query, str) and not citations:
                # No structured citations but search was performed
                pass

    # Citations path 4: extract markdown links from the report text
    # Deep research reports often embed [title](url) references
    if not citations and text:
        import re

        for match in re.finditer(r'\[([^\]]+)\]\((https?://[^)]+)\)', text):
            citations.append({"title": match.group(1), "url": match.group(2)})

    return text, latency_ms, citations


def call_model(model_key: str, prompt: str, max_tokens: int, tier: str = "chat") -> tuple[str, int, list[dict]]:
    """Route a call to the right provider API. Returns (response_text, latency_ms, citations).

    For chat tier, uses standard chat completions. For news/research tiers,
    uses specialized API callers with web search and citation extraction.
    """
    provider, model = model_key.split("/", 1)
    env_var, base_url = _PROVIDER_CONFIG[provider]
    api_key = os.environ.get(env_var, "")

    # News tier: web search enabled callers
    if tier == "news":
        if provider == "openai":
            return call_openai_news(api_key, model, prompt, max_tokens)
        elif provider == "xai":
            return call_grok_news(api_key, model, prompt, max_tokens)
        elif provider == "gemini":
            return call_gemini_news(api_key, model, prompt, max_tokens)

    # Docs tier: web search callers with larger token budgets
    if tier == "docs":
        if provider == "openai":
            return call_openai_news(api_key, model, prompt, max_tokens)
        elif provider == "xai":
            return call_grok_news(api_key, model, prompt, max_tokens)
        elif provider == "gemini":
            return call_gemini_news(api_key, model, prompt, max_tokens)

    # Research tier: deep research models → background API, others → web search
    if tier == "research":
        if model in _DEEP_RESEARCH_NAMES:
            if provider == "openai":
                return call_openai_deep_research(api_key, model, prompt, max_tokens)
            elif provider == "gemini":
                return call_gemini_deep_research(api_key, prompt)
        else:
            # Orchestrated research: web search callers with research-tier budgets
            if provider == "openai":
                return call_openai_news(api_key, model, prompt, max_tokens)
            elif provider == "xai":
                return call_grok_news(api_key, model, prompt, max_tokens)
            elif provider == "gemini":
                return call_gemini_news(api_key, model, prompt, max_tokens)

    # Chat tier (default): standard chat completions
    if provider in ("openai", "xai"):
        return call_openai_compatible(api_key, base_url, model, prompt, max_tokens)
    elif provider == "anthropic":
        return call_anthropic(api_key, model, prompt, max_tokens)
    elif provider == "gemini":
        return call_gemini(api_key, model, prompt, max_tokens)
    elif provider == "azure-foundry":
        return call_azure_foundry(api_key, model, prompt, max_tokens)
    else:
        raise ValueError(f"Unknown provider: {provider}")


# ─── Checkpoint / Resume ──────────────────────────────────────────────────────

_CHECKPOINT_DIR = PROJECT_ROOT / "data" / "benchmarks"
_CHECKPOINT_FILE = _CHECKPOINT_DIR / ".checkpoint.json"
_checkpoint_lock = threading.Lock()
_budget_lock = threading.Lock()


def _eval_key(model_key: str, prompt_text: str) -> str:
    """Unique key for a (model, prompt) eval — for dedup on resume."""
    import hashlib

    h = hashlib.sha256(prompt_text.encode()).hexdigest()[:12]
    return f"{model_key}::{h}"


def _save_checkpoint(results: list[EvalResult]) -> None:
    """Persist current eval results to checkpoint file (atomic write, thread-safe)."""
    with _checkpoint_lock:
        _CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
        data = [
            {
                "model_key": r.model_key,
                "task_type": r.task_type,
                "difficulty": r.difficulty,
                "prompt": r.prompt,
                "response": r.response,
                "latency_ms": r.latency_ms,
                "error": r.error,
                "tier": r.tier,
                "reference_score": r.reference_score,
                "citations": r.citations,
                "citation_count": r.citation_count,
                "report_length": r.report_length,
            }
            for r in results
        ]
        # Write checkpoint — use atomic rename with fallback for Windows/OneDrive locks
        content = json.dumps(data, indent=2)
        tmp = _CHECKPOINT_FILE.with_suffix(".tmp")
        try:
            tmp.write_text(content)
            tmp.replace(_CHECKPOINT_FILE)
        except PermissionError:
            # OneDrive or antivirus may lock the file; fall back to direct write
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            _CHECKPOINT_FILE.write_text(content)


def _load_checkpoint() -> list[EvalResult]:
    """Load eval results from checkpoint file."""
    if not _CHECKPOINT_FILE.exists():
        return []
    try:
        data = json.loads(_CHECKPOINT_FILE.read_text())
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Corrupt checkpoint file, ignoring: %s", e)
        return []

    results = []
    for d in data:
        try:
            r = EvalResult(
                model_key=d["model_key"],
                task_type=d["task_type"],
                difficulty=d["difficulty"],
                prompt=d["prompt"],
                response=d.get("response", ""),
                latency_ms=d.get("latency_ms", 0),
                error=d.get("error", ""),
                tier=d.get("tier", "chat"),
                reference_score=d.get("reference_score", 0.0),
                citations=d.get("citations", []),
                citation_count=d.get("citation_count", 0),
                report_length=d.get("report_length", 0),
            )
            results.append(r)
        except (KeyError, TypeError) as e:
            logger.warning("Skipping corrupt checkpoint entry: %s", e)
    return results


def _clear_checkpoint() -> None:
    """Delete checkpoint file after successful completion."""
    if _CHECKPOINT_FILE.exists():
        _CHECKPOINT_FILE.unlink()


# ─── Phase 2: Evaluate ───────────────────────────────────────────────────────


def _eval_single(
    model_key: str, ep: EvalPrompt, registry: dict
) -> tuple[EvalResult, float]:
    """Run a single model+prompt evaluation. Returns (result, cost_estimate).

    Thread-safe — no shared mutable state.
    """
    lookup = "openai/" + model_key.split("/", 1)[1] if model_key.startswith("azure-foundry/") else model_key
    cap = registry.get(lookup) or registry.get(model_key)

    result = EvalResult(
        model_key=model_key,
        task_type=ep.task_type,
        difficulty=ep.difficulty,
        prompt=ep.prompt,
        response="",
        latency_ms=0,
        tier=ep.tier,
    )
    cost = 0.0

    try:
        text, latency_ms, citations = call_model(model_key, ep.prompt, ep.max_tokens, tier=ep.tier)
        result.response = text
        result.latency_ms = latency_ms
        result.citations = citations
        result.citation_count = len(citations)
        result.report_length = len(text.split()) if ep.tier in ("research", "docs") else 0

        # Estimate cost — tier-specific token budgets
        thinking_extra = 500 if _is_thinking_model(model_key) else 0
        if ep.tier == "research":
            model_name = model_key.split("/", 1)[1]
            if model_name in _DEEP_RESEARCH_NAMES:
                in_tokens, out_tokens = 2000, 15000
            else:
                in_tokens, out_tokens = 600, 2500 + thinking_extra
        elif ep.tier == "docs":
            in_tokens, out_tokens = 600, 2000 + thinking_extra
        elif ep.tier == "news":
            in_tokens, out_tokens = 400, 800 + thinking_extra
        else:
            in_tokens, out_tokens = 400, 450 + thinking_extra

        if cap:
            cost = (in_tokens / 1_000_000) * cap.input_cost_per_1m + (
                out_tokens / 1_000_000
            ) * cap.output_cost_per_1m
            if ep.tier in ("news", "docs"):
                cost *= 1.2  # web search overhead
        else:
            fallback = {"research": 1.50, "news": 0.02, "docs": 0.03, "chat": 0.005}
            cost = fallback.get(ep.tier, 0.005)
    except Exception as e:
        result.error = str(e)
        logger.warning("Error evaluating %s: %s", model_key, e)

    result.reference_score = score_reference(result.response, ep.expected_contains)
    return result, cost


def run_evaluations(
    models: list[str],
    prompts: list[EvalPrompt],
    budget: float | None,
    registry: dict,
    prior_results: list[EvalResult] | None = None,
    max_workers: int = 5,
) -> list[EvalResult]:
    """Send each prompt to each model and collect results (parallel).

    If prior_results is provided (from --resume), skip already-completed evals.
    Checkpoints to disk after every eval so progress is never lost.
    """
    # Build set of already-completed eval keys
    results = list(prior_results) if prior_results else []
    done_keys: set[str] = set()
    for r in results:
        if not r.error:  # Only skip successful evals
            done_keys.add(_eval_key(r.model_key, r.prompt))

    # Build task list, skipping cached evals
    tasks: list[tuple[str, EvalPrompt]] = []
    skipped = 0
    for model_key in models:
        for ep in prompts:
            key = _eval_key(model_key, ep.prompt)
            if key in done_keys:
                skipped += 1
            else:
                tasks.append((model_key, ep))

    if skipped:
        print(f"  Resumed: {skipped} cached, {len(tasks)} new evals")

    if not tasks:
        print()
        return results

    spent = 0.0
    done_count = 0
    budget_exceeded = False

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {}
        for model_key, ep in tasks:
            fut = pool.submit(_eval_single, model_key, ep, registry)
            futures[fut] = (model_key, ep)

        for fut in as_completed(futures):
            model_key, ep = futures[fut]
            done_count += 1
            try:
                result, cost = fut.result()
            except Exception as e:
                # Unexpected error in thread — create error result
                result = EvalResult(
                    model_key=model_key,
                    task_type=ep.task_type,
                    difficulty=ep.difficulty,
                    prompt=ep.prompt,
                    response="",
                    latency_ms=0,
                    error=str(e),
                    tier=ep.tier,
                )
                cost = 0.0

            results.append(result)

            with _budget_lock:
                spent += cost
                over_budget = budget is not None and spent >= budget

            print(
                f"\r  [{done_count}/{len(tasks)}] {model_key} — {ep.task_type}/{ep.difficulty} "
                f"({result.latency_ms}ms)" + (" ERROR" if result.error else ""),
                end="",
                flush=True,
            )

            _save_checkpoint(results)

            if over_budget and not budget_exceeded:
                budget_exceeded = True
                print(f"\n  Budget limit ${budget:.2f} reached after ${spent:.2f}")
                # Cancel remaining futures
                for pending in futures:
                    pending.cancel()
                break

    print()  # newline after progress
    return results


def score_reference(response: str, expected_contains: list[str]) -> float:
    """Score response by checking how many expected terms are present."""
    if not expected_contains:
        return 0.0
    response_lower = response.lower()
    found = sum(1 for term in expected_contains if term.lower() in response_lower)
    return found / len(expected_contains)


def score_news_citations(citations: list[dict]) -> float:
    """Score news-tier citations: 60% count (0-8 → 0-1), 40% domain diversity (0-5 unique → 0-1)."""
    # Count score: 0-8 citations maps to 0-1
    count_score = min(len(citations), 8) / 8.0

    # Domain diversity: extract unique domains from URLs
    domains = set()
    for c in citations:
        url = c.get("url", "")
        if url:
            try:
                # Extract domain from URL
                from urllib.parse import urlparse

                domain = urlparse(url).netloc.replace("www.", "")
                if domain:
                    domains.add(domain)
            except Exception:
                pass
    diversity_score = min(len(domains), 5) / 5.0

    return 0.60 * count_score + 0.40 * diversity_score


def score_research_citations(citations: list[dict], text: str) -> float:
    """Score research-tier citations and report quality.

    35% count (0-20 → 0-1), 25% domain diversity (0-10 → 0-1),
    25% report length (0-2000 words → 0-1), 15% structure (headings/sections).
    """
    # Count score: 0-20 citations maps to 0-1
    count_score = min(len(citations), 20) / 20.0

    # Domain diversity: 0-10 unique domains maps to 0-1
    domains = set()
    for c in citations:
        url = c.get("url", "")
        if url:
            try:
                from urllib.parse import urlparse

                domain = urlparse(url).netloc.replace("www.", "")
                if domain:
                    domains.add(domain)
            except Exception:
                pass
    diversity_score = min(len(domains), 10) / 10.0

    # Report length: 0-2000 words maps to 0-1
    word_count = len(text.split())
    length_score = min(word_count, 2000) / 2000.0

    # Structure: presence of markdown headings (# or ##)
    lines = text.split("\n")
    heading_count = sum(1 for line in lines if line.strip().startswith("#"))
    structure_score = min(heading_count, 5) / 5.0

    return 0.35 * count_score + 0.25 * diversity_score + 0.25 * length_score + 0.15 * structure_score


def score_docs_citations(citations: list[dict], text: str) -> float:
    """Score docs-tier citations and documentation quality.

    30% citation count (0-10 → 0-1), 25% domain diversity (0-5 → 0-1),
    25% code examples (count of code blocks), 20% structure (headings + length).
    """
    # Citation count: 0-10 maps to 0-1
    count_score = min(len(citations), 10) / 10.0

    # Domain diversity: 0-5 unique domains maps to 0-1
    domains = set()
    for c in citations:
        url = c.get("url", "")
        if url:
            try:
                from urllib.parse import urlparse

                domain = urlparse(url).netloc.replace("www.", "")
                if domain:
                    domains.add(domain)
            except Exception:
                pass
    diversity_score = min(len(domains), 5) / 5.0

    # Code examples: count fenced code blocks (```...```)
    code_blocks = text.count("```")
    code_score = min(code_blocks // 2, 5) / 5.0  # pairs of ``` = blocks

    # Structure: headings + reasonable length
    lines = text.split("\n")
    heading_count = sum(1 for line in lines if line.strip().startswith("#"))
    word_count = len(text.split())
    structure_score = (min(heading_count, 8) / 8.0 + min(word_count, 1500) / 1500.0) / 2.0

    return 0.30 * count_score + 0.25 * diversity_score + 0.25 * code_score + 0.20 * structure_score


# ─── Phase 3: Judge ──────────────────────────────────────────────────────────

JUDGE_PROMPT = """You are evaluating an AI model's response to a research question.
Judge the QUALITY of the research output, not just correctness.

QUESTION:
{question}

RESPONSE:
{response}

Score the response on these 5 dimensions (0-10 each):
- accuracy: Are the facts correct and claims verifiable? (0=wrong, 10=precise)
- completeness: Does it cover the key aspects without major gaps? (0=superficial, 10=thorough)
- reasoning: Is the analysis sound? Does it weigh tradeoffs and consider edge cases? (0=shallow, 10=rigorous)
- clarity: Is it well-structured and easy to act on? Good formatting, no fluff? (0=rambling, 10=crisp)
- relevance: Does it directly address the question with actionable specifics, not generic filler? (0=off-topic, 10=targeted)

A great response is detailed WHERE IT MATTERS and concise WHERE IT DOESN'T.
Longer is NOT better. A focused 200-word answer can score higher than a vague 800-word one.

Return ONLY valid JSON, no markdown fences:
{{"accuracy": 8, "completeness": 7, "reasoning": 9, "clarity": 8, "relevance": 9}}"""

# Weights for combining judge dimensions (chat tier)
JUDGE_WEIGHTS = {
    "accuracy": 0.30,
    "completeness": 0.25,
    "reasoning": 0.25,
    "clarity": 0.10,
    "relevance": 0.10,
}

NEWS_JUDGE_PROMPT = """You are evaluating an AI model's web-search-augmented response.
Judge the QUALITY of the response, focusing on freshness and citation quality.

QUESTION:
{question}

RESPONSE:
{response}

Score the response on these 5 dimensions (0-10 each):
- freshness: Does it contain genuinely recent information, not stale training data? (0=outdated, 10=current)
- accuracy: Are the facts correct and verifiable? (0=wrong, 10=precise)
- citation_quality: Are citations real, relevant URLs (not hallucinated)? (0=no citations, 10=excellent sourcing)
- completeness: Does it cover the key aspects? (0=superficial, 10=thorough)
- source_diversity: Does it pull from multiple domains/sources? (0=single source, 10=diverse)

Return ONLY valid JSON, no markdown fences:
{{"freshness": 8, "accuracy": 7, "citation_quality": 9, "completeness": 8, "source_diversity": 7}}"""

NEWS_JUDGE_WEIGHTS = {
    "freshness": 0.30,
    "accuracy": 0.20,
    "citation_quality": 0.25,
    "completeness": 0.15,
    "source_diversity": 0.10,
}

RESEARCH_JUDGE_PROMPT = """You are evaluating an AI model's deep research report.
Judge the QUALITY of the research output as a comprehensive report.

QUESTION:
{question}

RESPONSE (first 3000 chars):
{response}

Score the response on these 5 dimensions (0-10 each):
- comprehensiveness: Does it cover the topic thoroughly with sufficient depth? (0=superficial, 10=exhaustive)
- accuracy: Are claims factually correct and well-supported? (0=wrong, 10=precise)
- synthesis: Does it connect ideas across sources, identify patterns? (0=listing facts, 10=insightful synthesis)
- structure: Is it well-organized with clear headings, sections, executive summary? (0=unstructured, 10=professional)
- citation_integration: Are citations woven into the text naturally, supporting claims? (0=no integration, 10=seamless)

Return ONLY valid JSON, no markdown fences:
{{"comprehensiveness": 8, "accuracy": 7, "synthesis": 9, "structure": 8, "citation_integration": 7}}"""

RESEARCH_JUDGE_WEIGHTS = {
    "comprehensiveness": 0.25,
    "accuracy": 0.25,
    "synthesis": 0.20,
    "structure": 0.15,
    "citation_integration": 0.15,
}

DOCS_JUDGE_PROMPT = """You are evaluating an AI model's technical documentation output.
Judge the QUALITY of the documentation for a developer audience.

QUESTION:
{question}

RESPONSE (first 3000 chars):
{response}

Score the response on these 5 dimensions (0-10 each):
- accuracy: Are API details, parameters, and behaviors correctly documented? (0=wrong, 10=precise)
- completeness: Does it cover endpoints, params, auth, errors, edge cases? (0=superficial, 10=exhaustive)
- code_examples: Are there working, idiomatic code examples? (0=none, 10=excellent examples)
- structure: Is it organized like good developer docs with headings, tables, code blocks? (0=wall of text, 10=professional)
- citation_quality: Does it cite official docs with real URLs? (0=no sources, 10=well-sourced)

Return ONLY valid JSON, no markdown fences:
{{"accuracy": 8, "completeness": 7, "code_examples": 9, "structure": 8, "citation_quality": 7}}"""

DOCS_JUDGE_WEIGHTS = {
    "accuracy": 0.25,
    "completeness": 0.25,
    "code_examples": 0.20,
    "structure": 0.15,
    "citation_quality": 0.15,
}


def pick_judge_model(models_being_tested: list[str], forced_judge: str | None) -> str | None:
    """Pick a judge model that isn't being tested.

    Preference: gpt-4.1-mini > claude-haiku-4-5 > grok-4-fast > gemini-2.5-flash
    """
    if forced_judge:
        return forced_judge

    # Judge candidates in preference order
    candidates = [
        ("openai", "gpt-4.1-mini", "OPENAI_API_KEY"),
        ("anthropic", "claude-haiku-4-5", "ANTHROPIC_API_KEY"),
        ("xai", "grok-4-fast", "XAI_API_KEY"),
        ("gemini", "gemini-2.5-flash", "GEMINI_API_KEY"),
    ]

    for provider, model, env_var in candidates:
        key = f"{provider}/{model}"
        if os.environ.get(env_var) and key not in models_being_tested:
            return key

    # If all cheap models are being tested, still use gpt-4.1-mini as judge
    for provider, model, env_var in candidates:
        if os.environ.get(env_var):
            return f"{provider}/{model}"

    return None


def _get_judge_config(tier: str) -> tuple[str, dict[str, float]]:
    """Return (judge_prompt_template, weights) for the given tier."""
    if tier == "news":
        return NEWS_JUDGE_PROMPT, NEWS_JUDGE_WEIGHTS
    elif tier == "research":
        return RESEARCH_JUDGE_PROMPT, RESEARCH_JUDGE_WEIGHTS
    elif tier == "docs":
        return DOCS_JUDGE_PROMPT, DOCS_JUDGE_WEIGHTS
    return JUDGE_PROMPT, JUDGE_WEIGHTS


def _judge_single(
    result: EvalResult, judge_model: str
) -> tuple[dict[str, float] | None, float]:
    """Judge a single eval result. Returns (judge_details, judge_score).

    Thread-safe — no shared mutable state.
    """
    judge_template, weights = _get_judge_config(result.tier)
    trunc = 3000 if result.tier in ("research", "docs") else 2000
    prompt = judge_template.format(
        question=result.prompt,
        response=result.response[:trunc],
    )

    try:
        judge_response, _, _ = call_model(judge_model, prompt, 200)
        scores = _parse_judge_response(judge_response, weights)
        weighted = sum(scores.get(dim, 0) * weight for dim, weight in weights.items())
        return scores, weighted / 10.0
    except Exception as e:
        logger.warning("Judge error for %s: %s", result.model_key, e)
        return None, 0.0


def run_judge(
    results: list[EvalResult], judge_model: str, max_workers: int = 5
) -> list[EvalResult]:
    """Score each eval result using the LLM judge (tier-aware, parallel)."""
    judgeable = [(i, r) for i, r in enumerate(results) if not r.error]
    total = len(judgeable)
    done_count = 0

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {}
        for idx, result in judgeable:
            fut = pool.submit(_judge_single, result, judge_model)
            futures[fut] = idx

        for fut in as_completed(futures):
            idx = futures[fut]
            done_count += 1
            try:
                scores, score = fut.result()
                results[idx].judge_details = scores or {}
                results[idx].judge_score = score
            except Exception as e:
                logger.warning("Judge thread error: %s", e)
                results[idx].judge_score = 0.0

            print(
                f"\r  Judging [{done_count}/{total}] {results[idx].model_key} — {results[idx].task_type}",
                end="",
                flush=True,
            )

    print()
    return results


def _parse_judge_response(text: str, valid_keys: dict[str, float] | None = None) -> dict[str, float]:
    """Parse judge JSON response. Filters to valid dimension keys."""
    if valid_keys is None:
        valid_keys = JUDGE_WEIGHTS

    text = text.strip()
    # Strip markdown fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [line for line in lines if not line.strip().startswith("```")]
        text = "\n".join(lines)

    # Find JSON object in response
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        text = text[start:end]

    data = json.loads(text)
    return {k: float(v) for k, v in data.items() if k in valid_keys}


def compute_combined_scores(results: list[EvalResult], use_judge: bool) -> list[EvalResult]:
    """Compute combined quality score for each result (tier-aware).

    Chat:     combined = 0.70 * judge + 0.30 * reference_match
    News:     combined = 0.60 * judge + 0.40 * citation_score
    Research: combined = 0.50 * judge + 0.50 * citation_score
    """
    for r in results:
        if r.error:
            r.combined_score = 0.0
            continue

        # Compute citation scores for news/research/docs tiers
        if r.tier == "news":
            r.citation_score = score_news_citations(r.citations)
        elif r.tier == "research":
            r.citation_score = score_research_citations(r.citations, r.response)
        elif r.tier == "docs":
            r.citation_score = score_docs_citations(r.citations, r.response)

        if use_judge:
            if r.tier == "news":
                r.combined_score = 0.60 * r.judge_score + 0.40 * r.citation_score
            elif r.tier == "research":
                r.combined_score = 0.50 * r.judge_score + 0.50 * r.citation_score
            elif r.tier == "docs":
                r.combined_score = 0.55 * r.judge_score + 0.45 * r.citation_score
            else:
                r.combined_score = 0.70 * r.judge_score + 0.30 * r.reference_score
        else:
            if r.tier in ("news", "research", "docs"):
                r.combined_score = r.citation_score
            else:
                r.combined_score = r.reference_score
    return results


# ─── Phase 4: Report ─────────────────────────────────────────────────────────


def build_summaries(results: list[EvalResult], registry: dict) -> list[ModelSummary]:
    """Aggregate results into per-model-per-tier summaries."""
    by_model_tier: dict[tuple[str, str], list[EvalResult]] = {}
    for r in results:
        by_model_tier.setdefault((r.model_key, r.tier), []).append(r)

    summaries = []
    for (model_key, tier), model_results in by_model_tier.items():
        valid = [r for r in model_results if not r.error]
        errors = [r for r in model_results if r.error]

        avg_quality = sum(r.combined_score for r in valid) / len(valid) if valid else 0.0
        avg_latency = sum(r.latency_ms for r in valid) / len(valid) if valid else 0.0

        # Cost estimate (azure-foundry shares pricing with openai equivalents)
        lookup = "openai/" + model_key.split("/", 1)[1] if model_key.startswith("azure-foundry/") else model_key
        cap = registry.get(lookup) or registry.get(model_key)
        total_cost = 0.0
        if cap:
            output_tokens = 450 + (500 if _is_thinking_model(model_key) else 0)
            per_eval = (400 / 1_000_000) * cap.input_cost_per_1m + (output_tokens / 1_000_000) * cap.output_cost_per_1m
            total_cost = per_eval * len(valid)

        cost_per_quality = total_cost / avg_quality if avg_quality > 0 else float("inf")

        # Scores by task type
        by_type: dict[str, list[float]] = {}
        for r in valid:
            by_type.setdefault(r.task_type, []).append(r.combined_score)

        scores_by_type = {t: sum(s) / len(s) for t, s in by_type.items()}

        summaries.append(
            ModelSummary(
                model_key=model_key,
                avg_quality=avg_quality,
                avg_latency_ms=avg_latency,
                total_cost=total_cost,
                cost_per_quality=cost_per_quality,
                scores_by_type=scores_by_type,
                num_evals=len(valid),
                errors=len(errors),
                tier=tier,
            )
        )

    return sorted(summaries, key=lambda s: s.avg_quality, reverse=True)


def _print_tier_section(tier: str, tier_summaries: list[ModelSummary], tier_results: list[EvalResult]):
    """Print a single tier's rankings section."""
    n_models = len(tier_summaries)
    n_prompts = len({(r.prompt, r.model_key) for r in tier_results}) // max(n_models, 1)
    print()
    print(f"  TIER: {tier.upper()} ({n_models} models, {n_prompts} prompts)")
    print("  " + "-" * 72)

    if tier == "chat":
        header = f"  {'Rank':<6}{'Model':<28}{'Quality':>8}{'Latency':>10}{'Cost':>9}{'$/Quality':>10}"
        print(header)
        print("  " + "-" * 72)
        for i, s in enumerate(tier_summaries, 1):
            cost_q = f"${s.cost_per_quality:.3f}" if s.cost_per_quality < 1000 else "N/A"
            print(
                f"  {i:<6}{s.model_key:<28}{s.avg_quality:>7.2f}"
                f"{s.avg_latency_ms:>8.0f}ms"
                f"  ${s.total_cost:>6.3f}"
                f"  {cost_q:>8}"
            )
    elif tier == "news":
        header = f"  {'Rank':<6}{'Model':<28}{'Quality':>8}{'Latency':>10}{'Citations':>10}{'Cost':>9}"
        print(header)
        print("  " + "-" * 72)
        for i, s in enumerate(tier_summaries, 1):
            model_results = [r for r in tier_results if r.model_key == s.model_key and not r.error]
            avg_cites = sum(r.citation_count for r in model_results) / max(len(model_results), 1)
            print(
                f"  {i:<6}{s.model_key:<28}{s.avg_quality:>7.2f}"
                f"{s.avg_latency_ms:>8.0f}ms"
                f"{avg_cites:>9.1f}"
                f"  ${s.total_cost:>6.3f}"
            )
    elif tier in ("research", "docs"):
        header = f"  {'Rank':<6}{'Model':<28}{'Quality':>8}{'Latency':>10}{'Citations':>10}{'Words':>8}{'Cost':>9}"
        print(header)
        print("  " + "-" * 80)
        for i, s in enumerate(tier_summaries, 1):
            model_results = [r for r in tier_results if r.model_key == s.model_key and not r.error]
            avg_cites = sum(r.citation_count for r in model_results) / max(len(model_results), 1)
            avg_words = sum(r.report_length for r in model_results) / max(len(model_results), 1)
            print(
                f"  {i:<6}{s.model_key:<28}{s.avg_quality:>7.2f}"
                f"{s.avg_latency_ms:>8.0f}ms"
                f"{avg_cites:>9.1f}"
                f"{avg_words:>7.0f}"
                f"  ${s.total_cost:>6.3f}"
            )


def print_report(summaries: list[ModelSummary], results: list[EvalResult], total_cost: float):
    """Print the full benchmark report as formatted tables (tier-aware)."""
    print()
    print("  Model Quality Benchmark")
    print("  " + "=" * 72)

    # Group summaries and results by tier
    _TIER_ORDER = {"chat": 0, "news": 1, "research": 2, "docs": 3}
    tiers_present = sorted({s.tier for s in summaries}, key=lambda t: _TIER_ORDER.get(t, 99))

    for tier in tiers_present:
        tier_summaries = sorted(
            [s for s in summaries if s.tier == tier],
            key=lambda s: s.avg_quality,
            reverse=True,
        )
        tier_results = [r for r in results if r.tier == tier]
        _print_tier_section(tier, tier_summaries, tier_results)

    # Errors
    if any(s.errors > 0 for s in summaries):
        print()
        print("  Errors:")
        for s in summaries:
            if s.errors > 0:
                print(f"    {s.model_key}: {s.errors} failed eval(s)")

    # Rankings by task type (within each tier)
    for tier in tiers_present:
        tier_summaries = [s for s in summaries if s.tier == tier]
        tier_results = [r for r in results if r.tier == tier]
        task_types = sorted({r.task_type for r in tier_results})
        if task_types and len(tier_summaries) > 1:
            print()
            print(f"  Rankings by Task Type ({tier.upper()})")
            print("  " + "-" * 64)
            for tt in task_types:
                ranked = sorted(tier_summaries, key=lambda s: s.scores_by_type.get(tt, 0), reverse=True)
                top3 = []
                for i, s in enumerate(ranked[:3], 1):
                    score = s.scores_by_type.get(tt, 0)
                    if score > 0:
                        short_name = s.model_key.split("/")[-1]
                        top3.append(f"{i}. {short_name} ({score:.2f})")
                if top3:
                    print(f"  {tt.upper():<22} {'  '.join(top3)}")

    # Cross-tier routing recommendations (only when multiple tiers)
    if len(tiers_present) > 1:
        print()
        print("  Cross-Tier Routing Recommendations")
        print("  " + "-" * 64)
        for tier in tiers_present:
            tier_summaries = sorted(
                [s for s in summaries if s.tier == tier],
                key=lambda s: s.avg_quality,
                reverse=True,
            )
            if tier_summaries:
                best = tier_summaries[0]
                cost_per = best.total_cost / max(best.num_evals, 1)
                label = {"chat": "Quick lookup", "news": "Live news", "research": "Deep research", "docs": "Documentation"}.get(tier, tier)
                print(f"  {label:<20} -> {best.model_key:<30} ${cost_per:.2f}/query")
    else:
        # Single-tier routing recommendations
        tier = tiers_present[0]
        tier_summaries = [s for s in summaries if s.tier == tier]
        tier_results = [r for r in results if r.tier == tier]
        task_types = sorted({r.task_type for r in tier_results})
        if task_types and tier_summaries:
            print()
            print("  Routing Recommendations")
            print("  " + "-" * 64)
            header = f"  {'Task Type':<22}{'Best Quality':<24}{'Best Value (Quality/$)'}"
            print(header)
            print("  " + "-" * 64)
            for tt in task_types:
                best_q = max(tier_summaries, key=lambda s: s.scores_by_type.get(tt, 0))
                best_v = max(
                    tier_summaries,
                    key=lambda s: s.scores_by_type.get(tt, 0) / max(s.total_cost, 0.0001),
                )
                print(f"  {tt:<22}{best_q.model_key:<24}{best_v.model_key}")

    print()
    print(f"  Total estimated cost: ${total_cost:.2f}")
    print()


def print_json_report(summaries: list[ModelSummary], results: list[EvalResult], total_cost: float):
    """Print report as JSON."""
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_cost": total_cost,
        "models": len(summaries),
        "evals": len(results),
        "rankings": [asdict(s) for s in summaries],
        "results": [
            {
                "model": r.model_key,
                "tier": r.tier,
                "task_type": r.task_type,
                "difficulty": r.difficulty,
                "quality": r.combined_score,
                "judge_score": r.judge_score,
                "reference_score": r.reference_score,
                "citation_score": r.citation_score,
                "citation_count": r.citation_count,
                "report_length": r.report_length,
                "latency_ms": r.latency_ms,
                "error": r.error,
            }
            for r in results
        ],
    }
    print(json.dumps(report, indent=2))


# ─── Persistence ──────────────────────────────────────────────────────────────


def save_results(summaries: list[ModelSummary], results: list[EvalResult], total_cost: float) -> Path:
    """Save benchmark results to data/benchmarks/."""
    out_dir = PROJECT_ROOT / "data" / "benchmarks"
    out_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = out_dir / f"benchmark_{timestamp}.json"

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_cost": total_cost,
        "rankings": [asdict(s) for s in summaries],
        "results": [
            {
                "model": r.model_key,
                "tier": r.tier,
                "task_type": r.task_type,
                "difficulty": r.difficulty,
                "quality": r.combined_score,
                "judge_score": r.judge_score,
                "reference_score": r.reference_score,
                "citation_score": r.citation_score,
                "citation_count": r.citation_count,
                "report_length": r.report_length,
                "latency_ms": r.latency_ms,
                "error": r.error,
                "judge_details": r.judge_details,
            }
            for r in results
        ],
    }

    out_file.write_text(json.dumps(report, indent=2))
    return out_file


def load_all_prior_results() -> list[dict]:
    """Load results from all saved benchmark files. Returns raw result dicts (saved format)."""
    out_dir = PROJECT_ROOT / "data" / "benchmarks"
    if not out_dir.exists():
        return []
    results = []
    for path in sorted(out_dir.glob("benchmark_*.json")):
        try:
            data = json.loads(path.read_text())
            for r in data.get("results", []):
                results.append(r)
        except (json.JSONDecodeError, OSError):
            continue
    return results


def get_covered_model_tiers(prior: list[dict]) -> set[tuple[str, str]]:
    """Return set of (model_key, tier) pairs already benchmarked with non-error results."""
    covered = set()
    for r in prior:
        model = r.get("model", "")
        tier = r.get("tier", "chat")
        error = r.get("error", "")
        if model and not error:
            covered.add((model, tier))
    return covered


def emit_routing_config(summaries: list[ModelSummary], results: list[EvalResult]) -> Path:
    """Write routing preferences JSON for future auto_mode integration."""
    out_dir = PROJECT_ROOT / "data" / "benchmarks"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "routing_preferences.json"

    task_types = sorted({r.task_type for r in results})
    preferences = {}
    for tt in task_types:
        best_quality = max(summaries, key=lambda s: s.scores_by_type.get(tt, 0))
        best_value = max(
            summaries,
            key=lambda s: s.scores_by_type.get(tt, 0) / max(s.total_cost, 0.0001),
        )
        preferences[tt] = {
            "best_quality": best_quality.model_key,
            "best_quality_score": best_quality.scores_by_type.get(tt, 0),
            "best_value": best_value.model_key,
            "best_value_score": best_value.scores_by_type.get(tt, 0),
        }

    # Deduplicate overall ranking (models appear in multiple tiers)
    seen: set[str] = set()
    overall_ranking: list[str] = []
    for s in summaries:
        if s.model_key not in seen:
            seen.add(s.model_key)
            overall_ranking.append(s.model_key)

    config = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model_count": len(summaries),
        "task_preferences": preferences,
        "overall_ranking": overall_ranking,
    }

    out_file.write_text(json.dumps(config, indent=2))
    return out_file


def compare_results(current_summaries: list[ModelSummary], compare_file: str):
    """Compare current results against a previous benchmark run."""
    prev_path = Path(compare_file)
    if not prev_path.exists():
        print(f"  Compare file not found: {compare_file}")
        return

    prev = json.loads(prev_path.read_text())
    prev_rankings = {r["model_key"]: r for r in prev.get("rankings", [])}

    print()
    print("  Comparison with Previous Run")
    print("  " + "-" * 64)
    header = f"  {'Model':<28}{'Quality':>10}{'Delta':>10}{'Latency':>10}{'Delta':>10}"
    print(header)
    print("  " + "-" * 64)

    for s in current_summaries:
        prev_m = prev_rankings.get(s.model_key)
        if prev_m:
            q_delta = s.avg_quality - prev_m.get("avg_quality", 0)
            l_delta = s.avg_latency_ms - prev_m.get("avg_latency_ms", 0)
            q_sign = "+" if q_delta >= 0 else ""
            l_sign = "+" if l_delta >= 0 else ""
            print(
                f"  {s.model_key:<28}{s.avg_quality:>9.2f}"
                f"  {q_sign}{q_delta:>+7.2f}"
                f"{s.avg_latency_ms:>8.0f}ms"
                f"  {l_sign}{l_delta:>+7.0f}ms"
            )
        else:
            print(f"  {s.model_key:<28}{s.avg_quality:>9.2f}      (new)")

    print()


# ─── Display helpers ──────────────────────────────────────────────────────────


def run_validation(tier: str = "chat"):
    """Send 1 cheap prompt to each available provider to verify APIs work.

    Chat + News: cheap validation. Research: skipped by default (costs $0.50+).
    """
    key_status = check_api_keys()

    # Chat tier validation (existing)
    if tier in ("chat", "all"):
        test_prompt = "What is 2+2? Reply with just the number."
        test_models = [
            ("openai", "openai/gpt-4.1-mini"),
            ("openai", "openai/gpt-5-mini"),
            ("xai", "xai/grok-4-fast"),
            ("gemini", "gemini/gemini-2.5-flash"),
            ("gemini", "gemini/gemini-2.5-pro"),
            ("gemini", "gemini/gemini-3-flash-preview"),
            ("gemini", "gemini/gemini-3-pro-preview"),
            ("anthropic", "anthropic/claude-haiku-4-5"),
            ("azure-foundry", "azure-foundry/gpt-4.1"),
        ]

        print()
        print("  Chat Tier Validation")
        print("  " + "=" * 64)

        passed = failed = skipped = 0
        for provider, model_key in test_models:
            if not key_status.get(provider, False):
                print(f"  [ ] {model_key:<35} SKIPPED (no API key)")
                skipped += 1
                continue
            try:
                text, latency_ms, _ = call_model(model_key, test_prompt, 10)
                has_four = "4" in text
                status = "OK" if has_four else f"OK (unexpected: {text[:30]})"
                print(f"  [+] {model_key:<35} {status} ({latency_ms}ms)")
                passed += 1
            except Exception as e:
                print(f"  [X] {model_key:<35} FAILED: {str(e)[:60]}")
                failed += 1

        print()
        print(f"  {passed} passed, {failed} failed, {skipped} skipped")

    # News tier validation
    if tier in ("news", "all"):
        news_prompt = "What day is it today? Include the date."
        news_tests = [
            ("xai", "xai/grok-4-1-fast-reasoning"),
            ("xai", "xai/grok-4-fast-reasoning"),
            ("gemini", "gemini/gemini-3-flash-preview"),
            ("gemini", "gemini/gemini-3-pro-preview"),
            ("gemini", "gemini/gemini-2.5-flash"),
            ("gemini", "gemini/gemini-2.5-pro"),
        ]

        print()
        print("  News Tier Validation (web search)")
        print("  " + "=" * 64)

        passed = failed = skipped = 0
        for provider, model_key in news_tests:
            if not key_status.get(provider, False):
                print(f"  [ ] {model_key:<35} SKIPPED (no API key)")
                skipped += 1
                continue
            try:
                text, latency_ms, citations = call_model(model_key, news_prompt, 100, tier="news")
                cite_count = len(citations)
                print(f"  [+] {model_key:<35} OK ({latency_ms}ms, {cite_count} citations)")
                passed += 1
            except Exception as e:
                print(f"  [X] {model_key:<35} FAILED: {str(e)[:60]}")
                failed += 1

        print()
        print(f"  {passed} passed, {failed} failed, {skipped} skipped")

    # Research tier validation — skipped unless explicitly requested
    if tier == "research":
        print()
        print("  Research Tier Validation")
        print("  " + "=" * 64)
        print("  WARNING: Research validation costs ~$0.50+ per model.")
        print("  Testing with a minimal prompt...")

        research_prompt = "Briefly summarize the current state of AI safety research in 2-3 sentences."
        research_tests = [
            ("openai", "openai/o3-deep-research"),
            ("gemini", "gemini/deep-research"),
        ]

        passed = failed = skipped = 0
        for provider, model_key in research_tests:
            if not key_status.get(provider, False):
                print(f"  [ ] {model_key:<35} SKIPPED (no API key)")
                skipped += 1
                continue
            try:
                text, latency_ms, citations = call_model(model_key, research_prompt, 500, tier="research")
                cite_count = len(citations)
                words = len(text.split())
                print(f"  [+] {model_key:<35} OK ({latency_ms}ms, {cite_count} cites, {words} words)")
                passed += 1
            except Exception as e:
                print(f"  [X] {model_key:<35} FAILED: {str(e)[:60]}")
                failed += 1

        print()
        print(f"  {passed} passed, {failed} failed, {skipped} skipped")

    # Docs tier validation — uses same web search callers as news
    if tier in ("docs", "all"):
        docs_prompt = "What are the main endpoints of the Stripe API? List 3."
        docs_tests = [
            ("openai", "openai/gpt-5-mini"),
            ("gemini", "gemini/gemini-3-flash-preview"),
            ("xai", "xai/grok-4-fast-reasoning"),
        ]

        print()
        print("  Docs Tier Validation (web search + documentation)")
        print("  " + "=" * 64)

        passed = failed = skipped = 0
        for provider, model_key in docs_tests:
            if not key_status.get(provider, False):
                print(f"  [ ] {model_key:<35} SKIPPED (no API key)")
                skipped += 1
                continue
            try:
                text, latency_ms, citations = call_model(model_key, docs_prompt, 500, tier="docs")
                cite_count = len(citations)
                print(f"  [+] {model_key:<35} OK ({latency_ms}ms, {cite_count} citations)")
                passed += 1
            except Exception as e:
                print(f"  [X] {model_key:<35} FAILED: {str(e)[:60]}")
                failed += 1

        print()
        print(f"  {passed} passed, {failed} failed, {skipped} skipped")

    if tier == "all":
        print()
        print("  NOTE: Research tier skipped (costs $0.50+). Use --validate --tier research to test.")

    print()


def show_prompts(tier: str = "all"):
    """Display eval prompts for the specified tier(s)."""
    prompt_sets = []
    if tier in ("chat", "all"):
        prompt_sets.append(("CHAT", EVAL_PROMPTS))
    if tier in ("news", "all"):
        prompt_sets.append(("NEWS", NEWS_EVAL_PROMPTS))
    if tier in ("research", "all"):
        prompt_sets.append(("RESEARCH", RESEARCH_EVAL_PROMPTS))
    if tier in ("docs", "all"):
        prompt_sets.append(("DOCS", DOCS_EVAL_PROMPTS))

    total_count = 0
    all_types: set[str] = set()

    for tier_name, prompts in prompt_sets:
        print()
        print(f"  {tier_name} Tier Prompts")
        print("  " + "=" * 64)
        current_type = ""
        for i, ep in enumerate(prompts, 1):
            if ep.task_type != current_type:
                current_type = ep.task_type
                all_types.add(current_type)
                print()
                print(f"  {current_type.upper()}")
                print("  " + "-" * 60)
            prompt_short = ep.prompt[:80].replace("\n", " ")
            if len(ep.prompt) > 80:
                prompt_short += "..."
            print(f"    {i:>2}. [{ep.difficulty}] {prompt_short}")
            print(f"        expects: {', '.join(ep.expected_contains)}")
        total_count += len(prompts)

    print()
    print(f"  Total: {total_count} prompts across {len(all_types)} task types")
    print()


def show_dry_run(
    tier_plans: list[tuple[str, list[str], list[EvalPrompt]]],
    est_cost: float,
    judge_model: str | None,
):
    """Show what would happen without making API calls."""
    print()
    print("  Benchmark Plan (Dry Run)")
    print("  " + "=" * 64)

    for tier_name, models, prompts in tier_plans:
        print()
        print(f"  TIER: {tier_name.upper()}")
        print(f"  Models to test ({len(models)}):")
        for m in models:
            print(f"    - {m}")

        print(f"  Eval prompts ({len(prompts)}):")
        by_type: dict[str, int] = {}
        for p in prompts:
            by_type[p.task_type] = by_type.get(p.task_type, 0) + 1
        for tt, count in sorted(by_type.items()):
            print(f"    {tt}: {count} prompts")

    total_evals = sum(len(models) * len(prompts) for _, models, prompts in tier_plans)
    print()
    print(f"  Total API calls: {total_evals} (eval) + {total_evals} (judge)")
    print(f"  Judge model: {judge_model or 'none (--no-judge)'}")
    print(f"  Estimated cost: ${est_cost:.2f}")
    print()


def print_preflight(key_status: dict[str, bool], models: list[str], est_cost: float):
    """Print preflight status."""
    print()
    print("  API Key Status")
    print("  " + "-" * 44)
    for provider, has_key in sorted(key_status.items()):
        marker = "[+]" if has_key else "[-]"
        status = "OK" if has_key else "MISSING"
        print(f"  {marker} {provider:<15} {status}")
    print("  " + "-" * 44)

    configured = sum(1 for v in key_status.values() if v)
    print(f"  {configured} providers configured, {len(models)} models selected")
    print(f"  Estimated cost: ${est_cost:.2f}")
    print()


# ─── Main ─────────────────────────────────────────────────────────────────────


def _select_prompts_for_tier(tier: str, args) -> list[EvalPrompt]:
    """Select prompts for a given tier, applying --task-type and --quick filters."""
    if tier == "news":
        prompts = list(NEWS_EVAL_PROMPTS)
    elif tier == "research":
        prompts = list(RESEARCH_EVAL_PROMPTS)
    elif tier == "docs":
        prompts = list(DOCS_EVAL_PROMPTS)
    else:
        prompts = list(EVAL_PROMPTS)

    if args.task_type:
        prompts = [p for p in prompts if p.task_type == args.task_type]
    if args.quick:
        seen_types: set[str] = set()
        quick_prompts = []
        for p in prompts:
            if p.task_type not in seen_types:
                seen_types.add(p.task_type)
                quick_prompts.append(p)
        prompts = quick_prompts

    return prompts


def main():
    parser = argparse.ArgumentParser(
        description="Benchmark model quality across providers to validate routing decisions.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/benchmark_models.py --validate                    # Test provider APIs
  python scripts/benchmark_models.py --dry-run --tier all          # Show plan + cost
  python scripts/benchmark_models.py                               # Chat tier (default)
  python scripts/benchmark_models.py --tier news --quick --no-judge # Cheapest news test
  python scripts/benchmark_models.py --tier docs                   # Documentation tier
  python scripts/benchmark_models.py --tier all --save             # Full run, save results
  python scripts/benchmark_models.py --tier all --resume --save    # Resume crashed run
  python scripts/benchmark_models.py --tier news --provider gemini # Vendor + tier
  python scripts/benchmark_models.py --show-prompts --tier all     # Display all prompts
  python scripts/benchmark_models.py --compare data/benchmarks/benchmark_PREV.json
        """,
    )
    parser.add_argument(
        "--tier",
        choices=["chat", "news", "research", "docs", "all"],
        default="chat",
        help="Benchmark tier: chat (default), news (web search), research (deep research), docs (API documentation), or all",
    )
    parser.add_argument("--quick", action="store_true", help="Run 1 prompt per task type")
    parser.add_argument(
        "--task-type",
        help="Only run prompts for this task type",
    )
    parser.add_argument("--model", help="Only benchmark this model (e.g. openai/gpt-5)")
    parser.add_argument(
        "--provider",
        choices=["openai", "xai", "gemini", "anthropic", "azure-foundry"],
        help="Only benchmark models from this provider",
    )
    parser.add_argument("--include-expensive", action="store_true", help="Include expensive models (gpt-5.2, opus)")
    parser.add_argument("--budget", type=float, help="Maximum spend in dollars for the run")
    parser.add_argument("--judge-model", help="Force a specific judge model (e.g. openai/gpt-4.1-mini)")
    parser.add_argument("--no-judge", action="store_true", help="Skip LLM judge, use reference/citation scoring only")
    parser.add_argument("--format", choices=["table", "json"], default="table", help="Output format")
    parser.add_argument("--save", action="store_true", help="Save results to data/benchmarks/")
    parser.add_argument("--emit-routing-config", action="store_true", help="Write routing_preferences.json")
    parser.add_argument("--compare", metavar="FILE", help="Compare against a previous benchmark run")
    parser.add_argument("--dry-run", action="store_true", help="Show plan without making API calls")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from checkpoint — skip already-completed evals (auto-saved after each eval)",
    )
    parser.add_argument(
        "--validate", action="store_true", help="Validate provider APIs (chat + news; use --tier research for research)"
    )
    parser.add_argument("--show-prompts", action="store_true", help="Display eval prompts and exit")
    parser.add_argument(
        "--fill-gaps",
        action="store_true",
        help="Load all prior results and only run missing model+tier combos. Saves merged output.",
    )
    parser.add_argument("--workers", type=int, default=5, help="Parallel eval workers (default: 5)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")

    args = parser.parse_args()
    args.workers = max(1, min(args.workers, 50))

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Show prompts and exit
    if args.show_prompts:
        show_prompts(tier=args.tier)
        return

    # Validate: test provider APIs
    if args.validate:
        run_validation(tier=args.tier)
        return

    # ─── Phase 1: Preflight ───────────────────────────────────────────────
    print("Loading registry...")
    registry = load_registry()
    print(f"  {len(registry)} models registered")

    key_status = check_api_keys()

    # Determine which tiers to run
    tiers = ["chat", "news", "research", "docs"] if args.tier == "all" else [args.tier]

    # --fill-gaps: load prior results and skip already-covered (model, tier) combos
    prior_saved: list[dict] = []
    covered: set[tuple[str, str]] = set()
    if args.fill_gaps:
        prior_saved = load_all_prior_results()
        covered = get_covered_model_tiers(prior_saved)
        print(f"  Prior results: {len(prior_saved)} evals, {len(covered)} model+tier combos covered")

    # Build per-tier model + prompt lists
    tier_plans: list[tuple[str, list[str], list[EvalPrompt]]] = []
    all_models: list[str] = []
    all_prompts: list[EvalPrompt] = []

    for tier in tiers:
        models = select_models(args, registry, key_status, tier=tier)
        if args.fill_gaps:
            before = len(models)
            models = [m for m in models if (m, tier) not in covered]
            skipped = before - len(models)
            if skipped:
                print(f"  {tier}: skipping {skipped} already-benchmarked models, {len(models)} remaining")
        prompts = _select_prompts_for_tier(tier, args)
        if models and prompts:
            tier_plans.append((tier, models, prompts))
            all_models.extend(models)
            all_prompts.extend(prompts)

    if not tier_plans:
        if args.fill_gaps:
            print("\n  All gaps filled! No new models to benchmark.")
        else:
            print("\n  No models available to benchmark.")
            print("  Set API keys for at least one provider, or check --provider/--model/--tier flags.")
        sys.exit(0 if args.fill_gaps else 1)

    # Cost estimate
    est_cost = sum(estimate_cost(models, prompts, registry) for _, models, prompts in tier_plans)
    judge_cost = sum(len(models) * len(prompts) for _, models, prompts in tier_plans) * 0.0003
    if args.no_judge:
        judge_cost = 0
    est_total = est_cost + judge_cost

    print_preflight(key_status, all_models, est_total)

    # Dry run (before budget prompts)
    if args.dry_run:
        judge_model = None if args.no_judge else pick_judge_model(all_models, args.judge_model)
        show_dry_run(tier_plans, est_total, judge_model)
        return

    # Budget safety prompts (after dry-run, before spending money)
    if "research" in tiers and est_total > 2.0 and not args.budget:
        print(f"  WARNING: Research tier estimated cost ${est_total:.2f}.")
        print("  Use --budget to set a hard cap, or press Enter to continue (Ctrl+C to cancel).")
        try:
            input()
        except KeyboardInterrupt:
            print("\n  Cancelled.")
            return
    elif est_total > 5.0 and not args.budget:
        print(f"  WARNING: Estimated cost ${est_total:.2f} exceeds $5.00.")
        print("  Use --budget to set a hard cap, or press Ctrl+C to cancel.")
        print()

    # ─── Resume from checkpoint ─────────────────────────────────────────
    prior_results: list[EvalResult] | None = None
    if args.resume:
        prior_results = _load_checkpoint()
        if prior_results:
            print(f"  Resuming: {len(prior_results)} cached results from checkpoint")
        else:
            print("  No checkpoint found, starting fresh.")

    # ─── Phase 2: Evaluate ────────────────────────────────────────────────
    # Cumulative results — each tier builds on prior results so the
    # checkpoint always contains everything completed so far.
    all_results: list[EvalResult] = list(prior_results) if prior_results else []
    for tier, models, prompts in tier_plans:
        print(f"Running {tier.upper()} tier evaluations...")
        all_results = run_evaluations(
            models, prompts, args.budget, registry, prior_results=all_results, max_workers=args.workers
        )

    if not all_results:
        print("  No results collected. Check API keys and network.")
        sys.exit(1)

    # ─── Phase 3: Judge ───────────────────────────────────────────────────
    use_judge = not args.no_judge
    if use_judge:
        judge_model = pick_judge_model(all_models, args.judge_model)
        if judge_model:
            print(f"Running LLM judge ({judge_model})...")
            all_results = run_judge(all_results, judge_model, max_workers=args.workers)
        else:
            print("  No judge model available, falling back to reference/citation scoring.")
            use_judge = False

    all_results = compute_combined_scores(all_results, use_judge)

    # ─── Merge prior saved results (--fill-gaps) ─────────────────────────
    if args.fill_gaps and prior_saved:
        # Convert prior saved results to EvalResult objects for merged reporting
        new_keys = {(r.model_key, r.tier) for r in all_results}
        merged_count = 0
        for r in prior_saved:
            model = r.get("model", "")
            tier = r.get("tier", "chat")
            if (model, tier) in new_keys:
                continue  # don't duplicate — new results take precedence
            er = EvalResult(
                model_key=model,
                task_type=r.get("task_type", ""),
                difficulty=r.get("difficulty", ""),
                prompt="",  # not stored in saved format
                response="",
                latency_ms=r.get("latency_ms", 0),
                error=r.get("error", ""),
                tier=tier,
                judge_score=r.get("judge_score", 0.0),
                reference_score=r.get("reference_score", 0.0),
                combined_score=r.get("quality", 0.0),
                judge_details=r.get("judge_details", {}),
                citation_count=r.get("citation_count", 0),
                citation_score=r.get("citation_score", 0.0),
                report_length=r.get("report_length", 0),
            )
            all_results.append(er)
            merged_count += 1
        if merged_count:
            print(f"  Merged {merged_count} prior results into output")

    # ─── Phase 4: Report ─────────────────────────────────────────────────
    summaries = build_summaries(all_results, registry)

    # Calculate actual cost
    total_cost = sum(s.total_cost for s in summaries)

    # Save results first (before report printing, which can fail on encoding)
    if args.save:
        out_file = save_results(summaries, all_results, total_cost)
        print(f"  Results saved to {out_file}")
        config_file = emit_routing_config(summaries, all_results)
        print(f"  Routing config saved to {config_file}")

    if args.emit_routing_config and not args.save:
        config_file = emit_routing_config(summaries, all_results)
        print(f"  Routing config saved to {config_file}")

    if args.format == "json":
        print_json_report(summaries, all_results, total_cost)
    else:
        print_report(summaries, all_results, total_cost)

    # Compare against previous run
    if args.compare:
        compare_results(summaries, args.compare)

    # Clear checkpoint on successful completion
    _clear_checkpoint()


if __name__ == "__main__":
    main()
