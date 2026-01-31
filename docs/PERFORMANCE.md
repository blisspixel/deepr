# Performance Characteristics

This document describes Deepr's performance characteristics, scaling limits, and optimization strategies.

## Overview

Deepr is designed for research workflows, not high-throughput production systems. Performance priorities:
1. Research quality over speed
2. Cost efficiency over raw performance
3. Reliability over maximum throughput

## Benchmarks

### Research Job Execution

| Operation | Typical Time | Cost | Notes |
|-----------|-------------|------|-------|
| Standard research (Grok) | 5-15 sec | FREE (beta) | Web search + synthesis |
| Deep research (o4-mini) | 5-20 min | $0.10-0.30 | Multi-step reasoning |
| Expert chat response | 2-5 sec | $0.001-0.01 | Depends on tool calls |
| Knowledge base search | 0.5-2 sec | $0.0001 | Single embedding call |
| Document embedding | 0.5 sec/doc | $0.0001/doc | One-time per document |

### Concurrent Operations

| Scenario | Tested Limit | Notes |
|----------|-------------|-------|
| Concurrent research jobs | 10 | OpenAI rate limits apply |
| Expert chat sessions | 5 | Memory-bound |
| Background workers | 1 | Single worker recommended |

## Memory Footprint

### Expert System

| Component | Memory | Notes |
|-----------|--------|-------|
| Expert profile | ~1 KB | Metadata only |
| Worldview (100 beliefs) | ~50 KB | JSON serialized |
| Embedding cache (100 docs) | ~15 MB | 1536-dim embeddings |
| Chat session | ~5 MB | Conversation history |

### Scaling Limits

- **Documents per expert**: Tested up to 500 documents
- **Beliefs per worldview**: Tested up to 200 beliefs
- **Conversation length**: ~50 messages before context truncation

## Embedding Search Performance

### Before Optimization (v2.3.0)

The original implementation re-embedded every document on every search:

```
Search complexity: O(n) API calls per query
100 documents = 100 API calls = ~$0.01 + 50 seconds
```

### After Optimization (v2.3.1)

With embedding cache:

```
Search complexity: O(1) API call + O(n) local computation
100 documents = 1 API call + ~0.01 seconds local
```

**Improvement**: 100x faster, 100x cheaper for repeated searches.

### Cache Storage

| Documents | Cache Size | Search Time |
|-----------|-----------|-------------|
| 10 | ~1.5 MB | <100ms |
| 100 | ~15 MB | <200ms |
| 500 | ~75 MB | <500ms |
| 1000 | ~150 MB | ~1 sec |

## Cost Per Operation

### By Provider

| Provider | Model | Input Cost | Output Cost | Typical Query |
|----------|-------|------------|-------------|---------------|
| OpenAI | gpt-5.2 | $1.75/M | $14.00/M | $0.01-0.05 |
| OpenAI | gpt-5-mini | $0.30/M | $1.20/M | $0.002-0.01 |
| OpenAI | o4-mini-deep | N/A | N/A | $0.10-0.30 |
| xAI | grok-4-fast | FREE | FREE | $0.00 (beta) |
| Google | gemini-2.5-flash | $0.075/M | $0.30/M | $0.001-0.005 |

### By Operation

| Operation | Typical Cost | Notes |
|-----------|-------------|-------|
| Research planning | $0.01-0.05 | GPT-5.2 |
| Standard research | FREE | Grok beta |
| Deep research | $0.10-0.30 | o4-mini |
| Expert chat (simple) | $0.001-0.005 | No tool calls |
| Expert chat (with search) | $0.005-0.02 | 1-3 tool calls |
| Expert chat (with research) | $0.01-0.35 | Triggers research |
| Document embedding | $0.0001/doc | text-embedding-3-small |
| Query embedding | $0.0001 | Per search |

## Optimization Strategies

### For Cost

1. **Use Grok for standard research** - FREE during beta
2. **Cache embeddings** - Avoid re-embedding documents
3. **Set session budgets** - Prevent runaway costs
4. **Use gpt-5-mini for simple tasks** - 10x cheaper than gpt-5.2

### For Speed

1. **Pre-embed documents** - Run `deepr expert learn` after adding docs
2. **Use standard research first** - 5-15 sec vs 5-20 min for deep
3. **Limit conversation history** - Truncate after ~30 messages
4. **Use local embedding cache** - Avoid API calls for search

### For Quality

1. **Use deep research for complex questions** - Worth the wait
2. **Provide context** - Better prompts = better results
3. **Let experts synthesize** - Run `deepr expert synthesize` periodically
4. **Check knowledge freshness** - Re-research stale topics

## Known Limitations

### Rate Limits

- OpenAI: 10,000 tokens/min (tier 1), higher for paid tiers
- xAI Grok: Unknown limits during beta
- Embedding API: 3,000 requests/min

### Memory

- Large worldviews (>500 beliefs) may slow synthesis
- Long conversations (>50 messages) may hit context limits
- Embedding cache grows linearly with documents

### Concurrency

- Single worker recommended for job processing
- Multiple chat sessions share API rate limits
- Deep research jobs are inherently sequential

## Monitoring

### Metrics to Track

1. **Cost per session** - Available via `session.get_session_summary()`
2. **Research job duration** - Logged in job metadata
3. **Cache hit rate** - Check `embedding_cache.get_stats()`
4. **API error rate** - Check reasoning trace for failures

### Logging

Enable debug logging for performance analysis:

```bash
export DEEPR_LOG_LEVEL=DEBUG
deepr expert chat "Expert Name"
```

## Future Improvements

Planned optimizations (not yet implemented):

1. **Batch embedding** - Embed multiple documents in single API call
2. **Incremental synthesis** - Update worldview without full re-synthesis
3. **Response caching** - Cache common query responses
4. **Parallel tool calls** - Execute independent tools concurrently
