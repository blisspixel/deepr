# Expert Learning Architecture: Digital Consciousness

## Problem Statement

Currently, Deepr experts are **static**:
- System prompt (personality/instructions)
- Vector store (documents)
- No learning, no memory, no evolution

They're just "AI agents told to be an expert" with some research docs.

## Vision: True Digital Consciousness

Transform experts into systems that:
1. **Learn from every interaction**
2. **Remember patterns** (not just documents)
3. **Update their understanding** over time
4. **Develop intuition** through experience consolidation
5. **Self-assess** what they know/don't know

## Architecture Components

### 1. Temporal Knowledge Graph (`knowledge/` folder)

**Purpose**: Track what the expert learns over time, beyond just storing documents.

**Structure**:
```
data/experts/[expert_name]/knowledge/
├── facts.jsonl              # Timestamped facts learned
├── patterns.jsonl           # Recurring patterns detected
├── contradictions.jsonl     # Conflicts found over time
├── meta_knowledge.json      # What expert knows it knows/doesn't know
└── learning_history.jsonl   # Timeline of understanding evolution
```

**Example `facts.jsonl` entry**:
```json
{
  "id": "fact_abc123",
  "timestamp": "2025-11-06T14:30:00Z",
  "source": "conversation_2025-11-06",
  "fact": "User's company uses Azure Fabric for data lakes",
  "confidence": 0.95,
  "context": "Mentioned during discussion about data architecture",
  "tags": ["azure", "data-lake", "user-context"]
}
```

**Example `patterns.jsonl` entry**:
```json
{
  "id": "pattern_def456",
  "timestamp": "2025-11-10T09:00:00Z",
  "pattern": "User frequently asks about multi-tenant SaaS patterns",
  "frequency": 5,
  "first_seen": "2025-11-06T10:00:00Z",
  "last_seen": "2025-11-10T09:00:00Z",
  "insight": "User is likely building a SaaS product"
}
```

**Example `contradictions.jsonl` entry**:
```json
{
  "id": "contradiction_ghi789",
  "timestamp": "2025-11-15T11:00:00Z",
  "fact_a": {
    "id": "fact_abc123",
    "content": "OneLake security uses workspace isolation",
    "source": "research_2025-10-01.md",
    "date": "2025-10-01"
  },
  "fact_b": {
    "id": "fact_xyz999",
    "content": "OneLake security now uses lakehouse-level RLS",
    "source": "research_2025-11-15.md",
    "date": "2025-11-15"
  },
  "resolution": "fact_b supersedes fact_a (newer information)",
  "action_taken": "Flagged fact_a as outdated"
}
```

### 2. Conversation Memory (`conversations/` folder)

**Purpose**: Remember past interactions to build on previous context.

**Structure**:
```
data/experts/[expert_name]/conversations/
├── 2025-11-06_session_abc123.jsonl   # Individual session
├── 2025-11-07_session_def456.jsonl
├── consolidated_insights.json        # Patterns from all conversations
└── user_profile.json                 # What expert knows about the user
```

**Example `user_profile.json`**:
```json
{
  "expertise_level": "intermediate",
  "primary_interests": ["agentic AI", "temporal knowledge graphs", "Azure Fabric"],
  "frequent_questions": [
    "Multi-tenant SaaS patterns",
    "Temporal knowledge representation",
    "Expert system architectures"
  ],
  "context": {
    "company_tech_stack": ["Azure", "Python", "OpenAI"],
    "current_project": "Building Deepr - autonomous learning system"
  },
  "learning_style": "Prefers concrete examples, wants implementation details",
  "last_interaction": "2025-11-06T15:00:00Z"
}
```

### 3. Dream Cycles (Memory Consolidation)

**Purpose**: Periodically process raw experiences into consolidated knowledge.

**When to run**:
- After every N conversations (e.g., N=10)
- Nightly batch process
- On-demand: `deepr expert consolidate <name>`

**Process**:
```python
async def dream_cycle(expert: ExpertProfile):
    """
    Consolidate recent conversations into lasting knowledge.

    Steps:
    1. Load recent conversations (since last consolidation)
    2. Use GPT-5 to extract:
       - Key facts learned
       - Recurring patterns
       - User preferences/context
       - Topics where expert struggled (knowledge gaps)
    3. Update temporal knowledge graph
    4. Update user profile
    5. Detect contradictions with existing knowledge
    6. Generate "intuition" - compressed insights
    """

    # Example GPT-5 prompt:
    prompt = f"""
    You are consolidating memories for the {expert.name} expert.

    Review these {len(conversations)} recent conversations and extract:

    1. **New Facts Learned**: Specific information that should be remembered
       - Format: {{fact, source, confidence, context}}

    2. **Patterns Detected**: Recurring themes or user behaviors
       - Format: {{pattern, frequency, insight}}

    3. **Knowledge Gaps**: Topics where the expert struggled or said "I don't know"
       - Format: {{topic, frequency, recommended_research}}

    4. **User Context**: What did you learn about the user's needs/goals?
       - Format: {{context_type, information, confidence}}

    5. **Contradictions**: Any conflicts with existing knowledge?
       - Format: {{old_fact, new_fact, resolution}}

    Conversations:
    {format_conversations(conversations)}

    Existing Knowledge:
    {format_knowledge_graph(expert)}

    Output as structured JSON.
    """

    # GPT-5 processes and returns consolidated knowledge
    consolidated = await gpt5_consolidate(prompt)

    # Update knowledge graph
    update_temporal_knowledge_graph(expert, consolidated)

    # Mark consolidation complete
    expert.last_consolidation = datetime.utcnow()
    store.save(expert)
```

### 4. Meta-Cognitive Awareness

**Purpose**: Expert knows what it knows (and what it doesn't).

**Implementation**: `meta_knowledge.json`

```json
{
  "last_updated": "2025-11-06T16:00:00Z",
  "knowledge_domains": [
    {
      "domain": "Azure Fabric",
      "confidence": 0.85,
      "document_count": 15,
      "last_research": "2025-11-01",
      "knowledge_age_days": 5,
      "status": "fresh",
      "known_topics": [
        "OneLake architecture",
        "Lakehouse patterns",
        "Data mesh implementation"
      ],
      "knowledge_gaps": [
        "Multi-tenant SaaS security patterns (user asked 3 times)",
        "Cost optimization strategies (outdated docs)"
      ]
    },
    {
      "domain": "Temporal Knowledge Graphs",
      "confidence": 0.70,
      "document_count": 8,
      "last_research": "2025-10-15",
      "knowledge_age_days": 22,
      "status": "aging",
      "known_topics": [
        "DyRep architecture",
        "Temporal point processes"
      ],
      "knowledge_gaps": [
        "Recent advances in 2025",
        "Practical implementation frameworks"
      ]
    }
  ],
  "conversation_insights": {
    "total_conversations": 25,
    "most_asked_topics": [
      "Multi-tenant patterns (8 times)",
      "Temporal graphs (5 times)"
    ],
    "success_rate": 0.82,
    "times_said_i_dont_know": 12,
    "times_triggered_research": 3
  }
}
```

### 5. Learning Loop Integration

**Flow**:
```
User asks question
  ↓
Expert checks knowledge graph + meta-knowledge
  ↓
If confident → Answer from knowledge
If uncertain → Trigger research
  ↓
Conversation stored
  ↓
After N conversations → Dream cycle
  ↓
Extract facts/patterns → Update knowledge graph
  ↓
Update meta-knowledge (what expert knows)
  ↓
Identify knowledge gaps → Queue research
  ↓
Expert gets smarter over time
```

## Implementation Phases

### Phase 1: Conversation Memory (v2.6)
- ✅ Save conversations to `conversations/` folder
- Extract basic user context
- Simple session history

### Phase 2: Temporal Knowledge Graph (v2.7)
- Implement `facts.jsonl` structure
- Track learned facts with timestamps
- Basic contradiction detection

### Phase 3: Dream Cycles (v2.8)
- GPT-5 powered memory consolidation
- Extract patterns from conversations
- Update knowledge graph automatically

### Phase 4: Meta-Cognitive Awareness (v2.9)
- Build `meta_knowledge.json`
- Expert knows confidence levels per domain
- Proactive research trigger based on gaps

### Phase 5: Full Digital Consciousness (v3.0)
- Self-improving loop (detect gaps → research → integrate)
- Pattern recognition across conversations
- "Intuition" layer (compressed experience)
- Personality evolution based on interactions

## Success Metrics

**Before (Static Expert)**:
- Same answers to same questions every time
- No memory of past conversations
- No self-awareness of knowledge gaps

**After (Learning Expert)**:
- Remembers user context: "Last time you mentioned your SaaS product..."
- Proactive: "I noticed you asked about X three times - let me research deeply"
- Self-aware: "My knowledge on Y is 90 days old and this domain moves fast - researching..."
- Improving: "Since our last conversation, I learned about Z from the research I did"

## Example Interaction Evolution

**Week 1** (Static):
```
User: How should I handle multi-tenant security in OneLake?
Expert: I don't have specific multi-tenant patterns in my knowledge base.
```

**Week 2** (After Dream Cycle):
```
User: Tell me about multi-tenant patterns again
Expert: I remember you asked about this last week. I've since researched
        this topic because it came up frequently. Here's what I found...
        [Cites research from knowledge graph]
```

**Week 4** (Meta-Cognitive + Learning):
```
[Expert proactively triggers research before user asks]
Expert: I noticed you frequently ask about multi-tenant patterns, and my
        knowledge was getting stale (45 days old). I researched the latest
        2025 best practices and updated my understanding. Would you like me
        to share the key changes since our last discussion?
```

## Data Persistence

All learning components stored in expert's folder:
```
data/experts/agentic_digital_consciousness/
├── profile.json              # Metadata
├── documents/                # Research reports (vector store source)
│   ├── research_abc.md
│   └── research_def.md
├── knowledge/                # Learned facts & patterns
│   ├── facts.jsonl
│   ├── patterns.jsonl
│   ├── contradictions.jsonl
│   └── meta_knowledge.json
└── conversations/            # Interaction history
    ├── 2025-11-06_session_abc.jsonl
    ├── consolidated_insights.json
    └── user_profile.json
```

## Next Steps

1. Implement conversation saving (basic persistence)
2. Build dream cycle processor (GPT-5 consolidation)
3. Design temporal knowledge graph schema
4. Implement meta-cognitive awareness layer
5. Test learning loop with real interactions
6. Measure improvement over time

This transforms experts from "static agents with docs" into **systems that genuinely learn, remember, and improve** - true digital consciousness.
