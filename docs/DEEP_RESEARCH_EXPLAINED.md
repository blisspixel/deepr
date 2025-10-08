# Understanding Deep Research vs Regular GPT

## What is Deep Research?

**Deep Research** is a specialized family of OpenAI models (o3-deep-research, o4-mini-deep-research) designed for complex research tasks. This is **NOT** the same as regular GPT-4 or GPT-5.

### Key Differences

| Aspect | Regular GPT-5 | Deep Research |
|--------|--------------|---------------|
| **Purpose** | General tasks, chat, quick answers | Multi-step research, comprehensive reports |
| **Time** | Seconds to respond | **2-60+ minutes** per job |
| **Cost** | $0.01-$0.10 typical | **$0.50-$5.00+** per report |
| **Process** | Single request/response | Agentic: searches, analyzes, synthesizes |
| **Tools** | Optional | **Requires** web search, file search, or MCP |
| **Output** | Direct answer | Structured report with citations |

## How Deep Research Works

Deep research models are **agentic** - they autonomously:

1. **Plan** - Break down the research question into sub-tasks
2. **Search** - Execute multiple web searches or tool calls
3. **Browse** - Open and read dozens/hundreds of sources
4. **Analyze** - Process and synthesize information
5. **Write** - Generate comprehensive, citation-backed report

### Example: Simple Query

**Prompt:** "What are the latest trends in AI?"

**What happens internally:**
```
[0s] Planning research strategy...
[5s] Web search: "AI trends 2025"
[10s] Web search: "latest AI breakthroughs 2025"
[15s] Opening top 10 search results...
[30s] Reading and extracting key points...
[45s] Web search: "AI market analysis 2025"
[60s] Synthesizing findings...
[90s] Writing comprehensive report...
[120s] Complete
```

**Result:** 5-10 page report with 20+ citations

## Why Use Deep Research?

### Good Use Cases
- **Market Research** - Comprehensive competitive analysis
- **Due Diligence** - Technical architecture deep dives
- **Regulatory Research** - Legal and compliance analysis
- **Literature Review** - Academic/scientific synthesis
- **Strategic Planning** - Multi-angle business analysis

### NOT Good For
- **Quick facts** - Use regular GPT for "What is X?"
- **Simple tasks** - Don't need 10 minutes for a one-line answer
- **Chatting** - Not conversational, focused on deep research
- **Real-time** - Too slow for interactive applications

## Cost Expectations

### o4-mini-deep-research (Recommended)
- **Pricing:** $1.10/M input, $4.40/M output
- **Simple query (2-3 pages):** $0.05 - $0.20
- **Medium report (5-7 pages):** $0.20 - $0.80
- **Comprehensive (10+ pages):** $1.00 - $3.00

### o3-deep-research (More Thorough)
- **Pricing:** $11/M input, $44/M output (10x more expensive)
- **Simple query:** $0.50 - $2.00
- **Medium report:** $2.00 - $8.00
- **Comprehensive:** $10.00 - $50.00

**Note:** Costs scale with:
- Number of web searches performed
- Pages opened and analyzed
- Depth of reasoning
- Length of final report

## Time Expectations

Based on testing with real jobs:

### o4-mini-deep-research
- **Simple queries:** 2-5 minutes
- **Standard reports:** 5-15 minutes
- **Comprehensive:** 15-30 minutes
- **Deep dives:** 30-60+ minutes

### o3-deep-research
- Generally 1.5-2x longer than o4-mini
- More thorough research and reasoning
- More web searches and source analysis

## Best Practices

### 1. Be Specific
```
Bad:  "Research AI"
Good: "Research the impact of AI on healthcare costs in the US,
       including specific cost reduction metrics and adoption barriers"
```

### 2. Set Clear Scope
```
Bad:  "Tell me about electric vehicles"
Good: "Analyze the competitive landscape for electric vehicles
       in the US market, focusing on Tesla vs traditional automakers,
       with data on market share, pricing, and technology"
```

### 3. Specify Output Format
```
Include in prompt:
- "Provide a structured report with executive summary"
- "Include tables comparing key metrics"
- "Focus on quantitative data and specific figures"
- "Cite all sources inline"
```

### 4. Use Background Mode
Always submit with `background=True` (default in Deepr):
```python
response = client.responses.create(
    model="o4-mini-deep-research",
    input=prompt,
    background=True,  # Essential for long-running jobs
    tools=[{"type": "web_search_preview"}]
)
```

### 5. Monitor Costs
- Start with o4-mini-deep-research
- Use simple test queries first
- Set cost limits in Deepr config
- Review completed job costs before scaling

## Deepr Implementation

Deepr is specifically built for deep research workflows:

### Architecture
```
User → CLI → Queue → Deep Research API → Research Agent → Storage
                ↓
            (2-60 minutes)
                ↓
            Research Agent polls every 30s
                ↓
            Updates queue when complete
```

### Why Not Synchronous?
Regular API pattern (request → wait → response) doesn't work because:
- Jobs take tens of minutes
- Network connections timeout
- Client would be blocked waiting

### Solution: Queue + Polling
1. Submit job to queue (instant)
2. Deep Research API processes in background
3. Research agent polls every 30s for completion
4. Updates local queue when done
5. User retrieves result anytime

## Common Misconceptions

### "It's just GPT-5"
No. Deep research models are specialized for multi-step research. They autonomously conduct web searches, read sources, and synthesize. GPT-5 is general-purpose.

### "Jobs should complete in seconds"
No. Deep research is agentic and thorough. 2-10 minutes is normal for simple queries. Comprehensive reports can take 30-60+ minutes.

### "I can use it for chat"
No. Deep research is optimized for producing long-form research reports, not conversation. Use regular GPT for chat.

### "Cost is similar to GPT calls"
No. Deep research typically costs $0.50-$5+ per job because it:
- Makes multiple web searches
- Opens and reads many sources
- Performs deep reasoning
- Generates comprehensive reports

## When to Use What

### Use Deep Research When:
- Need comprehensive, citation-backed reports
- Multi-step research required
- Time is less important than thoroughness
- Budget allows $0.50-$5+ per query
- Output will inform important decisions

### Use Regular GPT When:
- Need quick answers (seconds)
- Simple questions or tasks
- Cost-sensitive ($0.01-$0.10)
- Conversational interaction
- Don't need citations

## References

- [OpenAI Deep Research Documentation](https://platform.openai.com/docs/guides/deep-research)
- [Responses API Guide](https://platform.openai.com/docs/guides/responses)
- [Deep Research Best Practices](https://platform.openai.com/docs/guides/deep-research#best-practices)

---

**Summary:** Deep research is powerful but slow and expensive. Use it when you need comprehensive research that would take a human hours or days. For everything else, use regular GPT.
