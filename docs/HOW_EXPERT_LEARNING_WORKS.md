# How Expert Learning Works

## TL;DR

**Yes!** Experts continuously learn from conversations. Every time they search the web or do research, that new knowledge is:
1. Saved as a markdown document
2. Uploaded to OpenAI vector store
3. Available for future searches

So the expert gets smarter over time as you talk to it.

---

## The Complete Learning Flow

### 1. You Ask a Question

```
You: "What is Microsoft Agent 365?"
```

### 2. Expert Searches Its Knowledge Base

**File:** `deepr/experts/chat.py:739`
```python
report_status("Searching knowledge base...")
search_results = await self._search_knowledge_base(query, top_k)
```

The expert searches its OpenAI vector store for relevant documents.

**Result in this case:**
```json
{
  "results_count": 0,
  "sources": []
}
```

Knowledge base is empty → Need to research!

### 3. Expert Triggers Web Research

**File:** `deepr/experts/chat.py:828-829`
```python
report_status("Searching web with Grok (FREE, ~10 sec)...")
result = await self._standard_research(query)
```

The expert calls Grok-4-Fast with agentic web search:
- Searches web + X/Twitter
- Gets comprehensive answer with citations
- Takes ~10 seconds
- **Cost: $0.00** (FREE during beta)

### 4. Expert SAVES Research to Knowledge Base

**File:** `deepr/experts/chat.py:412`
```python
await self._add_research_to_knowledge_base(query, answer, "standard_research")
```

This does THREE critical things:

#### A. Creates Local Markdown Document

**File:** `deepr/experts/chat.py:515-536`
```python
# Create filename with timestamp
timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
filename = f"research_{timestamp}_{safe_query}.md"

# Create markdown document with metadata
content = f"""# Research: {query}

**Date**: {datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")}
**Mode**: {mode}
**Expert**: {self.expert.name}

---

{answer}
"""

# Save to documents folder
with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)
```

**Example output:** `data/experts/microsoft_ai_expert/documents/research_20260122_000900_what_is_microsoft_agent_365.md`

This document contains:
- Full research answer (with citations)
- Timestamp when learned
- Query that triggered it
- Metadata about the expert

#### B. Uploads to OpenAI Vector Store

**File:** `deepr/experts/chat.py:538-549`
```python
# Upload to vector store
with open(filepath, 'rb') as f:
    file_obj = await self.client.files.create(
        file=f,
        purpose="assistants"
    )

# Add file to vector store
await self.client.vector_stores.files.create(
    vector_store_id=self.expert.vector_store_id,
    file_id=file_obj.id
)
```

This makes the knowledge **searchable** via semantic search in future conversations.

#### C. Updates Expert Profile

**File:** `deepr/experts/chat.py:551-554`
```python
# Update expert profile
self.expert.total_documents += 1
self.expert.source_files.append(str(filepath))
store.save(self.expert)
```

Tracks how many documents the expert has learned.

### 5. Expert Answers Your Question

Using the fresh research it just did, the expert gives you a comprehensive, accurate answer.

### 6. Next Time You Ask...

**Next conversation:**
```
You: "Tell me more about Agent 365 pricing"
```

**What happens:**
1. Expert searches knowledge base
2. **FINDS** the previous research document about Agent 365
3. Uses that cached knowledge (no need to search web again!)
4. Answers immediately with the information it learned before

**If the question requires NEW information:**
- Expert searches web again
- Adds NEW findings to knowledge base
- Knowledge base grows over time

---

## Real Example From Your Test

### Initial State
- Expert had **13 documents**
- None about Microsoft Agent 365

### After First Query ("What is Microsoft Agent 365?")

**Created:** `research_20260122_000900_what_is_microsoft_agent_365_announcement_details.md`

Contains 91 lines of comprehensive information:
- Overview of Agent 365
- Announcement details (Ignite 2025)
- Key features (5 pillars)
- Pricing breakdown
- Availability timeline
- 10 source citations

**Result:**
- Expert now has **15 documents** (grew from 13 → 15)
- Vector store updated with new knowledge
- `total_documents: 15` in profile.json

### Next Time Someone Asks

When you or anyone else asks about Agent 365 again:
- Expert searches its knowledge base
- FINDS this research document
- Answers instantly without re-searching web
- Can reference pricing, features, timeline, etc.

---

## Knowledge Persistence

### Where Knowledge Lives

1. **Local Files:** `data/experts/{expert_name}/documents/`
   - Permanent markdown files
   - Human-readable
   - Version controlled (if you commit them to git)

2. **OpenAI Vector Store:**
   - Cloud-hosted
   - Semantically searchable
   - Survives across sessions

3. **Expert Profile:** `data/experts/{expert_name}/profile.json`
   - Tracks document count
   - Metadata about knowledge
   - Source file list

### Knowledge Lifespan

**Permanent** - Knowledge persists:
- ✅ Across chat sessions
- ✅ Across system restarts
- ✅ Across days/weeks/months
- ✅ For all users of that expert

The expert truly **learns** and **remembers**.

---

## Temporal Knowledge Tracking

**File:** `deepr/experts/chat.py:557-566`

The system also tracks WHEN knowledge was learned:

```python
if self.temporal:
    self.temporal.record_learning(
        topic=topic,
        fact_text=answer[:500],
        source=filename,
        confidence=0.8,
        valid_for_days=180 if "latest" in query.lower() else None
    )
```

This enables:
- **Freshness detection** - Knows if knowledge might be outdated
- **Automatic refresh** - Can re-research after N days
- **Confidence tracking** - Lower confidence for older facts

For example:
- "latest pricing" → Valid for 180 days, then re-research
- "historical fact" → Valid indefinitely
- "current version" → Check freshness before answering

---

## Advanced Learning: Level 5 Consciousness

The expert also has a **synthesis** system that goes beyond just saving facts:

### Phase 4a: Autonomous Learning (Coming Soon)

**File:** `deepr/experts/synthesis.py`

The expert can:
1. **Form beliefs** - Connect facts into coherent understanding
2. **Identify contradictions** - Notice when new info conflicts with old
3. **Generate hypotheses** - Propose theories based on patterns
4. **Track confidence** - Adjust beliefs as new evidence arrives
5. **Build worldview** - Develop expert-level intuition over time

**Example:**
```python
# After learning about Agent 365 multiple times
expert.worldview.beliefs = [
    Belief(
        statement="Agent 365 is Microsoft's strategic bet on agentic AI",
        confidence=0.95,
        supporting_facts=[...],
        formed_at="2026-01-22"
    )
]
```

This creates **true expertise** - not just facts, but understanding.

---

## Cost Model

### Research Costs

| Research Type | Cost | Speed | When Used |
|--------------|------|-------|-----------|
| **Knowledge Base Search** | $0.00 | <1 sec | Always first |
| **Quick Lookup** (GPT-5.2) | ~$0.01 | 5-10 sec | Model knowledge check |
| **Standard Research** (Grok) | **$0.00** | 5-15 sec | Web search (FREE beta) |
| **Deep Research** (o4-mini) | $0.10-0.30 | 5-20 min | Complex analysis |

### Learning Overhead

**Adding to knowledge base:**
- Upload to OpenAI: $0.00 (included in file storage)
- Vector store indexing: $0.00 (automatic)
- File storage: Minimal (few MB per expert)

**Net result:** Learning is essentially FREE!

The main cost is the GPT-5 model generating the final answer (~$0.10-0.15), not the learning itself.

---

## How to See What the Expert Learned

### 1. Check Document Count
```bash
deepr expert list
```

Shows:
```
Microsoft AI Expert
  Documents: 15  # <-- Growing over time!
  Knowledge: fresh
```

### 2. Browse Research Files
```bash
ls data/experts/microsoft_ai_expert/documents/
```

Every `research_*.md` file is something the expert learned.

### 3. Read a Research Document
```bash
cat data/experts/microsoft_ai_expert/documents/research_20260122_000900_what_is_microsoft_agent_365.md
```

See exactly what was learned, when, and from where.

### 4. View Conversation Traces
```bash
cat data/experts/microsoft_ai_expert/conversations/20260122_000914_8b677654.json
```

Shows:
```json
{
  "reasoning_trace": [
    {
      "step": "search_knowledge_base",
      "results_count": 0
    },
    {
      "step": "standard_research",
      "mode": "standard_research_grok_agentic",
      "cost": 0.0
    }
  ]
}
```

Full audit trail of learning.

---

## Benefits of This System

### 1. **Efficient** - Only research once
- First person asks → Web search
- Everyone after → Instant from cache
- Saves time and money

### 2. **Accurate** - Always uses latest research
- Knowledge timestamped
- Can detect staleness
- Automatic refresh when needed

### 3. **Transparent** - Full audit trail
- Every source cited
- Every research documented
- Every decision traced

### 4. **Growing** - Gets smarter over time
- More questions → More knowledge
- More knowledge → Better answers
- Better answers → More trust

### 5. **Persistent** - Never forgets
- Knowledge survives restarts
- Shared across all users
- Builds institutional memory

---

## Comparison to Other Systems

### ChatGPT
- ❌ No persistent memory
- ❌ Can't save research findings
- ❌ Repeats same searches

### Deepr Experts
- ✅ Persistent vector store
- ✅ Saves all research
- ✅ Builds knowledge over time
- ✅ Shares learning across users

### Traditional RAG
- ⚠️ Static knowledge base
- ⚠️ Manual updates required
- ⚠️ No automatic learning

### Deepr Experts with Learning
- ✅ Dynamic knowledge base
- ✅ Automatic updates from research
- ✅ Continuous learning from conversations

---

## Future Enhancements

### Planned Features

1. **Automatic Knowledge Refresh**
   - Detect outdated knowledge
   - Re-research automatically
   - Update beliefs

2. **Cross-Expert Learning**
   - Share findings between experts
   - Build collective intelligence
   - Distributed knowledge network

3. **Active Learning**
   - Expert identifies knowledge gaps
   - Proactively researches them
   - Builds comprehensive understanding

4. **Knowledge Quality Scoring**
   - Rate source credibility
   - Weight conflicting information
   - Prioritize authoritative sources

5. **Semantic Synthesis**
   - Connect related facts
   - Build concept maps
   - Generate insights from patterns

---

## Summary

**Yes, experts DO learn from conversations!**

Every research query:
1. ✅ Saved as markdown document
2. ✅ Uploaded to vector store
3. ✅ Available for future searches
4. ✅ Tracked with metadata
5. ✅ Persists forever

The expert becomes a **living knowledge base** that grows smarter with each conversation.

This is fundamentally different from ChatGPT or Claude - your expert builds institutional memory that outlasts any single conversation.

---

**Test it yourself:**

```bash
# First time - triggers web search
deepr expert chat "Microsoft AI Expert"
> What is Microsoft Agent 365?
# Takes ~10 sec, searches web

# Second time - uses cached knowledge
> Tell me about Agent 365 pricing
# Instant, from knowledge base

# Check what was learned
deepr expert list
# See Documents: count increased!
```

The knowledge base grows with every question. 🚀
