# Phase 3a Issues - Web Search Not Working [RESOLVED ✓]

**Status:** FIXED on 2026-01-21
**See:** [PHASE_3A_FIX_COMPLETE.md](./PHASE_3A_FIX_COMPLETE.md) for full details

## Critical Problem (WAS)
Expert chat gives WRONG answers because web search isn't actually working.

**Example:** Microsoft Agent 365 (real product at microsoft.com/microsoft-agent-365)
- Expert says: "I don't think there is an official Microsoft product formally named Microsoft Agent 365"
- Reality: It's a real product announced at Ignite 2025

## Root Cause
OpenAI Chat Completions API doesn't have web search capability.
- `web_search_preview` only works with Responses API
- Current implementation uses AsyncOpenAI with Chat Completions
- Web search tool is silently ignored

## Solution Options

### Option 1: Use Perplexity API (FASTEST)
```python
# In deepr/experts/chat.py _standard_research()
import httpx
response = await httpx.AsyncClient().post(
    "https://api.perplexity.ai/chat/completions",
    headers={"Authorization": f"Bearer {PERPLEXITY_API_KEY}"},
    json={
        "model": "sonar",  # Fast web search model
        "messages": [{"role": "user", "content": query}]
    }
)
```
- **Speed:** 5-15 seconds
- **Cost:** ~$0.01-0.02 per query
- **Quality:** Excellent with citations

### Option 2: Use OpenAI Responses API
```python
# Switch from chat.completions to responses API
response = await client.responses.create(
    model="gpt-5.2",
    input=[{"role": "user", "content": query}],
    tools=[{"type": "web_search_preview"}]
)
```
- Requires switching from AsyncOpenAI client
- More complex integration

### Option 3: Use Tavily/Brave Search
- Similar to Perplexity
- Requires separate API key

## Performance Issues

### Current State
- Takes 2+ minutes for simple queries
- Should take 5-15 seconds like ChatGPT

### Causes
1. Multiple API calls (search KB → GPT-5.2 → no web search)
2. No actual web search happening
3. Slow fallback to model knowledge

### Fixes Needed
1. **Implement actual web search** (Perplexity recommended)
2. **Reduce latency** - minimize round trips
3. **Better progress indicators** - show what's actually happening

## Recommended Implementation

### File: deepr/experts/chat.py

```python
async def _standard_research(self, query: str) -> Dict:
    """Fast web search using Perplexity (5-15 sec)."""
    import httpx
    import os

    key = os.getenv("PERPLEXITY_API_KEY") or os.getenv("OPENAI_API_KEY")

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.perplexity.ai/chat/completions",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json"
            },
            json={
                "model": "sonar",
                "messages": [
                    {"role": "system", "content": "Be precise and concise. Cite sources."},
                    {"role": "user", "content": query}
                ]
            },
            timeout=30.0
        )

        result = response.json()
        answer = result["choices"][0]["message"]["content"]

        self.cost_accumulated += 0.015
        await self._add_research_to_knowledge_base(query, answer, "standard_research")

        return {"answer": answer, "mode": "perplexity_web", "cost": 0.015}
```

### Config Changes
Add to `.env`:
```bash
PERPLEXITY_API_KEY=pplx-xxxxx
```

## Testing

```bash
deepr expert chat "Microsoft AI Expert"
```

Ask: "what is microsoft agent 365"

**Expected:**
- Finds https://www.microsoft.com/en-us/microsoft-agent-365
- Answers in 5-15 seconds
- Cites microsoft.com source
- Correct information

**Currently:**
- Says product doesn't exist ❌
- Takes 2+ minutes ❌
- No web sources ❌
- Wrong information ❌

## Priority: CRITICAL
This breaks the entire expert system's value proposition.
