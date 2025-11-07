# Deepr Development Tasks

Comprehensive task list for implementing all planned features from the ROADMAP.

Last updated: 2025-11-06

## Current Status Summary

**COMPLETED (Recent Work):**
- Self-directed learning curriculum (GPT-5 generates research topics, submits jobs, polls completion, integrates into vector store)
- Interactive expert chat mode with GPT-5 tool calling for vector store search
- Agentic research integration (3-tier: quick_lookup, standard_research, deep_research)
- Per-session budget tracking with multi-layer protection
- Expert profile system with usage tracking
- Metacognition tracking (knowledge gaps, research triggers)
- Temporal knowledge tracking (when facts learned, stale detection)
- Diagnostics commands (meta, temporal, all)

**IN PROGRESS:**
- Knowledge base auto-update (research findings → permanent learning)
- Metacognition and temporal systems connected to chat workflow

**PRIORITY ORDER:**
1. Complete knowledge base auto-update and metacognition integration
2. Fix known issues
3. MCP Server integration
4. Additional semantic commands
5. Observability enhancements
6. Provider routing optimization

---

## Phase 1: Complete Agentic Expert System

### Task 1.1: Knowledge Base Auto-Update After Research ⭐ HIGH PRIORITY

**Goal:** When expert triggers research, automatically integrate findings into permanent knowledge base.

**Files to modify:**
- `deepr/experts/chat.py` (lines 400-600, research handling section)

**Implementation steps:**
1. After research job completes and results retrieved:
   - Download research report markdown
   - Extract key findings (first 500 chars or summary section)
   - Upload research report to expert's vector store
   - Update expert profile with new document count
   - Track temporal knowledge: topic, source=job_id, confidence=0.8

2. Add to chat.py after research completion (around line 550):
```python
# Auto-update knowledge base with research findings
if research_complete:
    result = self._get_research_result(job_id)

    # Upload to vector store
    report_path = f"data/experts/{self.expert.name}/research_{job_id}.md"
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(result['markdown'])

    file_obj = self.client.files.create(
        file=open(report_path, 'rb'),
        purpose='assistants'
    )

    self.client.beta.vector_stores.files.create(
        vector_store_id=self.expert.vector_store_id,
        file_id=file_obj.id
    )

    # Track temporal knowledge
    if self.temporal:
        topic = query[:100]
        self.temporal.record_learning(
            topic=topic,
            fact_text=result['markdown'][:500],
            source=f"research_{job_id}",
            confidence=0.8,
            valid_for_days=180 if "latest" in query.lower() else None
        )

    # Update expert profile
    self.expert.update_usage(documents_added=1)
```

3. Test that research findings are retrievable in next conversation

**Acceptance criteria:**
- Expert triggers research for knowledge gap
- Research completes successfully
- Markdown report uploaded to vector store
- Temporal knowledge recorded with source
- Expert profile document count increments
- Next conversation can retrieve research findings

**Estimated time:** 2-3 hours

---

### Task 1.2: Fix Metacognition Integration Issues

**Goal:** Ensure metacognition tracker properly records all knowledge gaps and research triggers.

**Files to modify:**
- `deepr/experts/chat.py` (metacognition tracking calls)
- `deepr/experts/metacognition.py` (verify tracking logic)

**Current issues:**
1. Metacognition may not record every knowledge gap
2. Research triggers not consistently logged
3. Learning events missing from some flows

**Implementation steps:**
1. Review all places where metacognition.record_knowledge_gap() should be called
2. Add tracking at:
   - Empty vector store search results
   - Low-confidence search results (<0.7)
   - When expert explicitly says "I don't know"
   - User asks about recency and docs are >6 months old

3. Add metacognition tracking after each research trigger:
```python
if self.metacognition and research_triggered:
    self.metacognition.record_research_triggered(
        topic=topic,
        research_type=research_type,  # quick_lookup, standard_research, deep_research
        estimated_cost=estimated_cost
    )
```

4. Add learning completion tracking:
```python
if self.metacognition and research_complete:
    self.metacognition.record_learning_completed(
        topic=topic,
        source=f"research_{job_id}",
        confidence=0.8
    )
```

**Acceptance criteria:**
- All knowledge gaps tracked in metacognition.json
- All research triggers logged with type and cost
- Learning completions recorded
- `deepr diagnostics meta` shows accurate stats

**Estimated time:** 1-2 hours

---

### Task 1.3: Temporal Knowledge Stale Detection

**Goal:** Expert proactively detects outdated knowledge and suggests refresh research.

**Files to modify:**
- `deepr/experts/chat.py` (add staleness check before answering)
- `deepr/experts/temporal_knowledge.py` (enhance get_stale_knowledge)

**Implementation steps:**
1. Before answering from vector store, check temporal staleness:
```python
# Check if answering from stale knowledge
if self.temporal and search_results:
    # Extract topics from search results
    topics_retrieved = [result.metadata.get('topic') for result in search_results]

    # Check staleness (>90 days default, >30 days for fast-moving domains)
    stale_topics = self.temporal.get_stale_knowledge(
        max_age_days=30 if self._is_fast_moving_domain() else 90
    )

    if any(topic in stale_topics for topic in topics_retrieved):
        # Warn user and offer refresh
        print(f"\n[WARNING] My knowledge on {topic} is from {learned_date} ({age} days ago).")
        print("Would you like me to research current information? [y/N]")

        if user_confirms():
            # Trigger refresh research
            self._trigger_research(f"Latest {topic} updates {current_year}")
```

2. Add domain velocity awareness:
```python
def _is_fast_moving_domain(self) -> bool:
    """Detect if expert's domain changes rapidly."""
    fast_moving_keywords = [
        "AI", "machine learning", "crypto", "blockchain",
        "latest", "current", "2025", "technology", "startup"
    ]
    return any(kw.lower() in self.expert.domain.lower() for kw in fast_moving_keywords)
```

3. Add to temporal_knowledge.py:
```python
def suggest_refresh_topics(self, max_age_days: int = 90) -> List[Dict]:
    """Suggest topics that should be refreshed with priority scores."""
    stale_topics = self.get_stale_knowledge(max_age_days)
    suggestions = []

    for topic_id in stale_topics:
        facts = [f for f in self.knowledge_timeline if f.topic == topic_id]
        if facts:
            latest_fact = max(facts, key=lambda f: f.learned_at)
            age_days = (datetime.utcnow() - latest_fact.learned_at).days

            # Priority score: older = higher priority
            priority = age_days / max_age_days

            suggestions.append({
                'topic': topic_id,
                'age_days': age_days,
                'priority': priority,
                'last_learned': latest_fact.learned_at.isoformat(),
                'source': latest_fact.source
            })

    return sorted(suggestions, key=lambda x: x['priority'], reverse=True)
```

**Acceptance criteria:**
- Expert detects stale knowledge before answering
- Warning shown with age and last learned date
- Offers to research current information
- Fast-moving domains use shorter staleness threshold (30 days)
- `deepr diagnostics temporal` shows stale topics

**Estimated time:** 2-3 hours

---

## Phase 2: MCP Server Integration

### Task 2.1: MCP Protocol Implementation

**Goal:** Create MCP server that exposes expert chat functionality to other AI agents.

**Files to create:**
- `deepr/mcp/server.py` (MCP server implementation)
- `deepr/mcp/__init__.py`
- `deepr/mcp/tools.py` (tool definitions)

**Implementation steps:**

1. Install MCP dependencies:
```bash
pip install mcp
```

2. Create `deepr/mcp/server.py`:
```python
"""MCP Server for Deepr Experts.

Exposes expert chat functionality via Model Context Protocol
for use by other AI agents (Claude Desktop, Cursor, etc.).
"""
import os
from typing import Any, Dict
from mcp.server import Server
from mcp.server.stdio import stdio_server
from deepr.experts.profile import ExpertProfile
from deepr.experts.chat import ExpertChatSession

server = Server("deepr-experts")

@server.list_tools()
async def list_tools() -> list[dict]:
    """List available MCP tools."""
    return [
        {
            "name": "list_experts",
            "description": "List all available domain experts",
            "inputSchema": {
                "type": "object",
                "properties": {},
            },
        },
        {
            "name": "query_expert",
            "description": "Ask a question to a specific domain expert",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "expert_name": {
                        "type": "string",
                        "description": "Name of the expert to query",
                    },
                    "question": {
                        "type": "string",
                        "description": "Question to ask the expert",
                    },
                    "budget": {
                        "type": "number",
                        "description": "Optional budget for research (if expert needs to research)",
                        "default": 0,
                    },
                },
                "required": ["expert_name", "question"],
            },
        },
        {
            "name": "get_expert_info",
            "description": "Get detailed information about a specific expert",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "expert_name": {
                        "type": "string",
                        "description": "Name of the expert",
                    },
                },
                "required": ["expert_name"],
            },
        },
    ]

@server.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> list[dict]:
    """Handle tool calls from AI agents."""

    if name == "list_experts":
        experts = ExpertProfile.list_all()
        return [{
            "type": "text",
            "text": "\n".join([
                f"- {e['name']}: {e['description']} (docs: {e['stats']['documents']})"
                for e in experts
            ])
        }]

    elif name == "query_expert":
        expert_name = arguments["expert_name"]
        question = arguments["question"]
        budget = arguments.get("budget", 0)

        expert = ExpertProfile.load(expert_name)
        if not expert:
            return [{"type": "text", "text": f"Expert '{expert_name}' not found"}]

        # Create chat session
        agentic = budget > 0
        session = ExpertChatSession(expert, agentic=agentic, budget=budget)

        # Get response
        response = session.send_message(question)

        # Format with sources
        text = response["content"]
        if response.get("sources"):
            text += "\n\nSources:\n" + "\n".join([
                f"- {s['filename']}" for s in response["sources"]
            ])

        if response.get("cost"):
            text += f"\n\nCost: ${response['cost']:.4f}"

        return [{"type": "text", "text": text}]

    elif name == "get_expert_info":
        expert_name = arguments["expert_name"]
        expert = ExpertProfile.load(expert_name)

        if not expert:
            return [{"type": "text", "text": f"Expert '{expert_name}' not found"}]

        info = [
            f"Expert: {expert.name}",
            f"Domain: {expert.domain}",
            f"Description: {expert.description}",
            f"Knowledge Base: {expert.stats['documents']} documents",
            f"Conversations: {expert.stats['conversations']}",
            f"Research Triggered: {expert.stats['research_jobs_triggered']}",
            f"Total Cost: ${expert.stats['total_cost']:.2f}",
            f"Created: {expert.created_at}",
        ]

        return [{"type": "text", "text": "\n".join(info)}]

    return [{"type": "text", "text": f"Unknown tool: {name}"}]

async def main():
    """Run the MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

3. Create CLI command to run MCP server:
```bash
deepr mcp serve
```

4. Add to `deepr/cli/commands/mcp.py`:
```python
import click
import asyncio
from deepr.mcp.server import main as mcp_main

@click.command()
def serve():
    """Start MCP server for AI agent integration."""
    click.echo("Starting Deepr MCP Server...")
    asyncio.run(mcp_main())
```

5. Register command in `deepr/cli/main.py`

**Acceptance criteria:**
- MCP server runs with `deepr mcp serve`
- AI agents can list experts
- AI agents can query experts
- AI agents can get expert info
- Responses include sources and costs
- Works with Claude Desktop and Cursor

**Estimated time:** 4-6 hours

---

### Task 2.2: MCP Configuration Documentation

**Goal:** Provide clear setup instructions for Claude Desktop and Cursor integration.

**Files to create/modify:**
- `docs/mcp_integration.md` (new documentation)
- `README.md` (add MCP section)

**Content:**

Create `docs/mcp_integration.md`:
```markdown
# MCP Integration: AI Agents <> Deepr Experts

Model Context Protocol (MCP) enables AI agents like Claude Desktop and Cursor to chat with your Deepr experts.

## Setup for Claude Desktop

1. Create or edit Claude Desktop config:
```
C:\Users\<USER>\AppData\Roaming\Claude\claude_desktop_config.json
```

2. Add Deepr MCP server:
```json
{
  "mcpServers": {
    "deepr-experts": {
      "command": "python",
      "args": ["-m", "deepr.mcp.server"],
      "env": {
        "OPENAI_API_KEY": "sk-..."
      }
    }
  }
}
```

3. Restart Claude Desktop

4. Test by asking Claude: "List available Deepr experts"

## Setup for Cursor

[Similar instructions for Cursor]

## Available Tools

Claude/Cursor can now:
- `list_experts()` - See all your domain experts
- `query_expert(name, question)` - Ask expert a question
- `get_expert_info(name)` - Get expert details

## Example Usage

```
You (to Claude): "Ask my Azure Architect expert about Landing Zone best practices"

Claude: [Uses query_expert tool]
Here's what your Azure Architect expert says:

According to azure-lz-best-practices.md, Landing Zones should...

Sources:
- azure-lz-best-practices.md
- fabric-governance.md

Cost: $0.0012
```

## Cost Tracking

Each query costs ~$0.001-0.01 depending on:
- Knowledge base size
- Response complexity
- Whether research was triggered

Set budget if you want expert to research: `query_expert(name, question, budget=2.0)`
```

**Acceptance criteria:**
- Documentation covers Claude Desktop setup
- Documentation covers Cursor setup
- Example usage included
- Cost expectations documented
- Troubleshooting section added

**Estimated time:** 2-3 hours

---

## Phase 3: Additional Semantic Commands

### Task 3.1: Implement `deepr check` Command

**Goal:** Fact verification command that researches and validates claims.

**Files to create/modify:**
- `deepr/cli/commands/check.py` (new command)
- Register in `deepr/cli/main.py`

**Implementation:**

```python
# deepr/cli/commands/check.py
import click
from deepr.research.runner import submit_research_job

@click.command()
@click.argument('claim')
@click.option('--provider', default='openai', help='Provider to use')
@click.option('--model', help='Model to use')
@click.option('--sources', help='Restrict to specific domains')
@click.option('--out', help='Save result to file')
def check(claim: str, provider: str, model: str, sources: str, out: str):
    """Verify a factual claim through research.

    Example:
        deepr check "Does Fabric support private endpoints?"
        deepr check "React 19 was released in 2024" --sources react.dev
    """

    # Build verification prompt
    prompt = f"""Verify the following claim through comprehensive research:

CLAIM: {claim}

Your task:
1. Research authoritative sources for this claim
2. Determine if the claim is:
   - TRUE (supported by evidence)
   - FALSE (contradicted by evidence)
   - PARTIALLY TRUE (needs clarification)
   - UNKNOWN (insufficient evidence)
3. Provide evidence with citations
4. Note any important caveats or context

Output format:
VERDICT: [TRUE/FALSE/PARTIALLY TRUE/UNKNOWN]
CONFIDENCE: [HIGH/MEDIUM/LOW]
EVIDENCE: [Your detailed analysis with citations]
"""

    click.echo(f"Verifying claim: {claim}")
    click.echo("Researching authoritative sources...")

    # Submit as focused research job
    job = submit_research_job(
        prompt=prompt,
        provider=provider,
        model=model,
        mode='focus',
        sources=sources.split(',') if sources else None
    )

    # Wait and display result
    # ... (wait logic similar to other commands)
```

**Acceptance criteria:**
- `deepr check "claim"` verifies factual claims
- Returns verdict (TRUE/FALSE/PARTIALLY TRUE/UNKNOWN)
- Includes confidence level
- Provides evidence with citations
- Works with --sources flag to restrict domains

**Estimated time:** 2-3 hours

---

### Task 3.2: Implement `deepr make docs` Command

**Goal:** Generate living documentation from research.

**Files to create/modify:**
- `deepr/cli/commands/make.py` (new command group)
- Register in `deepr/cli/main.py`

**Implementation:**

```python
# deepr/cli/commands/make.py
import click
from deepr.research.runner import submit_research_job

@click.group()
def make():
    """Generate documentation and strategic materials."""
    pass

@make.command()
@click.argument('topic')
@click.option('--upload', help='Include files for context')
@click.option('--out', required=True, help='Output file path')
@click.option('--format', default='guide', type=click.Choice(['guide', 'reference', 'tutorial', 'api']))
@click.option('--provider', default='openai')
@click.option('--budget', type=float, help='Budget limit')
def docs(topic: str, upload: str, out: str, format: str, provider: str, budget: float):
    """Generate comprehensive documentation.

    Examples:
        deepr make docs "Azure Landing Zone setup" --format guide --out alz-guide.md
        deepr make docs "FastAPI authentication" --format tutorial --out fastapi-auth.md
        deepr make docs "Fabric REST API" --format reference --out fabric-api-reference.md
    """

    format_prompts = {
        'guide': "Create a comprehensive how-to guide with step-by-step instructions",
        'reference': "Create a detailed technical reference with all concepts and APIs documented",
        'tutorial': "Create a beginner-friendly tutorial with examples and explanations",
        'api': "Create API documentation with endpoints, parameters, and examples"
    }

    prompt = f"""Research and write comprehensive documentation on: {topic}

Format: {format.upper()}
Style: {format_prompts[format]}

Requirements:
- Comprehensive coverage of all important aspects
- Clear organization with sections and subsections
- Practical examples where applicable
- Links to authoritative sources
- Up-to-date information (2025)
- Professional technical writing style

Target audience: Developers and technical practitioners
Output: Markdown format suitable for direct use
"""

    click.echo(f"Generating {format} documentation for: {topic}")
    click.echo(f"Output will be saved to: {out}")

    # Submit research job
    # ... (submit and wait logic)
```

**Acceptance criteria:**
- `deepr make docs "topic"` generates documentation
- Supports formats: guide, reference, tutorial, api
- Includes practical examples
- Citations to authoritative sources
- Saves to specified output file
- Markdown format ready for use

**Estimated time:** 2-3 hours

---

### Task 3.3: Implement `deepr make strategy` Command

**Goal:** Generate strategic analysis and roadmaps.

**Implementation:**

```python
@make.command()
@click.argument('goal')
@click.option('--context', help='Business context or constraints')
@click.option('--timeframe', default='12 months', help='Planning timeframe')
@click.option('--out', required=True, help='Output file path')
@click.option('--provider', default='openai')
@click.option('--budget', type=float)
def strategy(goal: str, context: str, timeframe: str, out: str, provider: str, budget: float):
    """Generate strategic analysis and recommendations.

    Examples:
        deepr make strategy "Fabric adoption roadmap" --timeframe "18 months" --out roadmap.md
        deepr make strategy "Migrate from AWS to Azure" --context "500 VMs, 50TB data" --out migration-strategy.md
    """

    prompt = f"""Develop a comprehensive strategic plan for: {goal}

Timeframe: {timeframe}
{f'Context: {context}' if context else ''}

Your task:
1. Research current state of the art and best practices
2. Identify key challenges and opportunities
3. Analyze available options and alternatives
4. Recommend optimal approach with rationale
5. Provide phased implementation roadmap
6. Identify risks and mitigation strategies
7. Estimate resources, costs, and timelines

Output structure:
# Executive Summary
# Current Landscape
# Strategic Options Analysis
# Recommended Approach
# Implementation Roadmap
# Risk Management
# Success Metrics
# Appendix: Research Sources
"""

    click.echo(f"Developing strategic plan: {goal}")
    click.echo(f"Timeframe: {timeframe}")

    # Submit as project-mode research (multi-phase)
    # ... (submit logic)
```

**Acceptance criteria:**
- `deepr make strategy "goal"` generates strategic analysis
- Includes current landscape research
- Analyzes multiple options
- Provides phased roadmap
- Risk analysis included
- Citations and sources
- Professional business document format

**Estimated time:** 2-3 hours

---

## Phase 4: Observability Enhancements

### Task 4.1: Reasoning Timeline Visualization

**Goal:** Show how expert's understanding evolved during research.

**Files to create/modify:**
- `deepr/experts/chat.py` (track reasoning events)
- `deepr/cli/commands/diagnostics.py` (add timeline command)

**Implementation:**

1. Track reasoning events in chat session:
```python
# In chat.py
self.reasoning_timeline = []

def _track_reasoning(self, event_type: str, content: str, metadata: Dict = None):
    """Track reasoning events for observability."""
    self.reasoning_timeline.append({
        'timestamp': datetime.utcnow().isoformat(),
        'event_type': event_type,  # query, search, gap_detected, research_triggered, answer
        'content': content,
        'metadata': metadata or {}
    })
```

2. Add events at key points:
```python
# When user asks question
self._track_reasoning('query', user_message)

# When searching knowledge base
self._track_reasoning('search', f"Searching for: {search_query}",
                      {'results_count': len(results)})

# When gap detected
self._track_reasoning('gap_detected', f"No knowledge about: {topic}",
                      {'confidence': 0.0})

# When research triggered
self._track_reasoning('research_triggered', f"Researching: {topic}",
                      {'type': research_type, 'estimated_cost': cost})

# When answering
self._track_reasoning('answer', response_text[:200],
                      {'sources': len(sources), 'cost': total_cost})
```

3. Save timeline with conversation:
```python
# At end of conversation
conversation_data = {
    'messages': self.messages,
    'reasoning_timeline': self.reasoning_timeline,
    'summary': {...}
}
```

4. Add diagnostics command:
```python
@diagnostics_cli.command(name="timeline")
@click.argument("expert_name")
@click.argument("conversation_id")
def show_timeline(expert_name: str, conversation_id: str):
    """Show reasoning timeline for a conversation."""

    # Load conversation
    conv_path = f"data/experts/{expert_name}/conversations/{conversation_id}.json"
    with open(conv_path, 'r') as f:
        data = json.load(f)

    timeline = data.get('reasoning_timeline', [])

    click.echo(f"\nReasoning Timeline for {expert_name}")
    click.echo(f"Conversation: {conversation_id}\n")

    for event in timeline:
        timestamp = event['timestamp'].split('T')[1][:8]  # HH:MM:SS
        event_type = event['event_type'].upper()
        content = event['content'][:80]

        click.echo(f"[{timestamp}] {event_type:20} {content}")

        if event.get('metadata'):
            for key, value in event['metadata'].items():
                click.echo(f"           {key}: {value}")
```

**Acceptance criteria:**
- All reasoning events tracked in timeline
- Timeline saved with conversation
- `deepr diagnostics timeline <expert> <conv_id>` displays chronological events
- Shows: queries, searches, gaps, research triggers, answers
- Metadata included (costs, result counts, etc.)

**Estimated time:** 3-4 hours

---

### Task 4.2: Enhanced Cost Attribution

**Goal:** Break down costs by phase, tool, and provider.

**Files to modify:**
- `deepr/experts/chat.py` (detailed cost tracking)
- Conversation save format

**Implementation:**

```python
# In chat.py
self.cost_breakdown = {
    'vector_search': 0,
    'quick_lookup': 0,
    'standard_research': 0,
    'deep_research': 0,
    'total': 0
}

def _track_cost(self, category: str, amount: float):
    """Track cost by category."""
    self.cost_breakdown[category] += amount
    self.cost_breakdown['total'] += amount
    self.cost_accumulated += amount

# Update each tool to track costs
# In quick_lookup:
self._track_cost('quick_lookup', 0)  # Free

# In standard_research:
self._track_cost('standard_research', result['cost'])

# In deep_research:
self._track_cost('deep_research', result['cost'])
```

Save with conversation and display in summary.

**Acceptance criteria:**
- Costs tracked by category
- Breakdown saved in conversation
- Summary shows cost attribution
- Cost per message tracked
- Total cost accurate

**Estimated time:** 1-2 hours

---

## Phase 5: Provider Routing Optimization

### Task 5.1: Provider Performance Tracking

**Goal:** Track per-provider performance metrics for intelligent routing.

**Files to create:**
- `deepr/providers/benchmarks.py` (performance tracking)
- `data/provider_benchmarks.json` (persisted metrics)

**Implementation:**

```python
# deepr/providers/benchmarks.py
from typing import Dict, List
from datetime import datetime, timedelta
import json
from pathlib import Path

class ProviderBenchmarks:
    """Track and analyze provider performance."""

    def __init__(self):
        self.benchmarks_path = Path("data/provider_benchmarks.json")
        self.benchmarks = self._load_benchmarks()

    def _load_benchmarks(self) -> Dict:
        if self.benchmarks_path.exists():
            with open(self.benchmarks_path, 'r') as f:
                return json.load(f)
        return {
            'providers': {},
            'last_updated': datetime.utcnow().isoformat()
        }

    def record_job(self, provider: str, model: str, metrics: Dict):
        """Record job metrics for benchmarking."""
        if provider not in self.benchmarks['providers']:
            self.benchmarks['providers'][provider] = {
                'models': {},
                'jobs_completed': 0,
                'jobs_failed': 0
            }

        provider_data = self.benchmarks['providers'][provider]

        if model not in provider_data['models']:
            provider_data['models'][model] = {
                'jobs': [],
                'avg_cost': 0,
                'avg_latency': 0,
                'success_rate': 1.0
            }

        model_data = provider_data['models'][model]

        # Record job
        model_data['jobs'].append({
            'timestamp': datetime.utcnow().isoformat(),
            'cost': metrics.get('cost', 0),
            'latency_seconds': metrics.get('latency', 0),
            'success': metrics.get('success', True),
            'tokens': metrics.get('tokens', 0),
            'citations': metrics.get('citations', 0)
        })

        # Keep only last 30 days
        cutoff = datetime.utcnow() - timedelta(days=30)
        model_data['jobs'] = [
            j for j in model_data['jobs']
            if datetime.fromisoformat(j['timestamp']) > cutoff
        ]

        # Update aggregate stats
        jobs = model_data['jobs']
        model_data['avg_cost'] = sum(j['cost'] for j in jobs) / len(jobs)
        model_data['avg_latency'] = sum(j['latency_seconds'] for j in jobs) / len(jobs)
        model_data['success_rate'] = sum(j['success'] for j in jobs) / len(jobs)

        if metrics.get('success'):
            provider_data['jobs_completed'] += 1
        else:
            provider_data['jobs_failed'] += 1

        self._save_benchmarks()

    def get_best_provider(self, task_type: str = 'deep_research') -> Dict:
        """Get best provider for task type based on benchmarks."""
        providers = self.benchmarks['providers']

        # Score providers (weighted formula)
        scores = {}
        for provider, data in providers.items():
            if data['jobs_completed'] < 3:  # Need minimum data
                continue

            # Normalize metrics (lower cost and latency = better)
            cost_score = 1 / (data['models'][task_type]['avg_cost'] + 0.01)
            latency_score = 1 / (data['models'][task_type]['avg_latency'] + 1)
            success_score = data['models'][task_type]['success_rate']

            # Weighted score (success most important)
            scores[provider] = (
                success_score * 0.6 +
                cost_score * 0.2 +
                latency_score * 0.2
            )

        if not scores:
            return {'provider': 'openai', 'model': 'o1'}  # Default

        best_provider = max(scores, key=scores.get)
        return {
            'provider': best_provider,
            'model': task_type,
            'score': scores[best_provider]
        }

    def _save_benchmarks(self):
        self.benchmarks['last_updated'] = datetime.utcnow().isoformat()
        with open(self.benchmarks_path, 'w') as f:
            json.dump(self.benchmarks, f, indent=2)
```

**Acceptance criteria:**
- Tracks cost, latency, success rate per provider/model
- Rolling 30-day window
- Calculates best provider for task type
- Persists to JSON
- Requires minimum 3 jobs for recommendations

**Estimated time:** 4-5 hours

---

### Task 5.2: Auto-Fallback on Provider Failure

**Goal:** Automatically retry with different provider if primary fails.

**Files to modify:**
- `deepr/research/runner.py` (add retry logic)
- `deepr/providers/__init__.py` (provider selection)

**Implementation:**

```python
# In runner.py
def submit_research_job_with_fallback(
    prompt: str,
    provider: str = 'openai',
    model: str = None,
    **kwargs
) -> Dict:
    """Submit research job with automatic fallback on failure."""

    provider_order = [provider, 'gemini', 'grok']  # Fallback order

    for attempt, fallback_provider in enumerate(provider_order):
        try:
            click.echo(f"Attempting with {fallback_provider}...")

            job = submit_research_job(
                prompt=prompt,
                provider=fallback_provider,
                model=model,
                **kwargs
            )

            # Track success
            benchmarks.record_job(
                provider=fallback_provider,
                model=model or 'default',
                metrics={'success': True, 'cost': job.cost}
            )

            return job

        except Exception as e:
            # Track failure
            benchmarks.record_job(
                provider=fallback_provider,
                model=model or 'default',
                metrics={'success': False}
            )

            if attempt < len(provider_order) - 1:
                click.echo(f"Failed: {e}")
                click.echo(f"Falling back to {provider_order[attempt + 1]}...")
            else:
                raise RuntimeError("All providers failed")
```

**Acceptance criteria:**
- Attempts primary provider first
- Falls back to alternative providers on failure
- Tracks failures in benchmarks
- User sees fallback messages
- Raises error only if all fail

**Estimated time:** 2-3 hours

---

## Phase 6: Testing & Validation

### Task 6.1: Integration Tests for Learning Workflow

**Goal:** End-to-end tests for complete learning cycle.

**Files to create:**
- `tests/integration/test_learning_workflow.py`

**Test cases:**
1. Expert creation with autonomous learning
2. Research job submission and polling
3. Report download and integration
4. Vector store update
5. Knowledge retrieval in next conversation
6. Metacognition and temporal tracking

**Implementation:**
```python
def test_complete_learning_workflow():
    """Test complete learning cycle end-to-end."""

    # 1. Create expert with learning
    expert = create_expert(
        name="Test Expert",
        topics=["topic1"],
        budget=1.0
    )

    # 2. Verify research job submitted
    assert len(expert.research_jobs) == 1

    # 3. Wait for completion (or mock)
    # ...

    # 4. Verify vector store updated
    assert expert.stats['documents'] > 0

    # 5. Chat with expert
    session = ExpertChatSession(expert)
    response = session.send_message("What did you learn about topic1?")

    # 6. Verify can retrieve research
    assert "topic1" in response['content'].lower()
    assert len(response['sources']) > 0

    # 7. Verify metacognition tracked
    meta = MetaCognitionTracker(expert.name)
    stats = meta.get_learning_stats()
    assert stats['knowledge_gaps_tracked'] >= 0

    # 8. Verify temporal knowledge
    temporal = TemporalKnowledgeTracker(expert.name)
    stats = temporal.get_statistics()
    assert stats['topics_tracked'] > 0
```

**Estimated time:** 4-6 hours

---

### Task 6.2: MCP Integration Tests

**Goal:** Test MCP server with mock AI agent.

**Files to create:**
- `tests/integration/test_mcp_server.py`

**Test cases:**
1. Server starts successfully
2. list_experts returns experts
3. query_expert returns response
4. get_expert_info returns details
5. Error handling (expert not found, etc.)

**Estimated time:** 3-4 hours

---

## Phase 7: Documentation

### Task 7.1: Expert System User Guide

**Goal:** Comprehensive guide for creating and using experts.

**Files to create:**
- `docs/expert_system_guide.md`

**Sections:**
- Creating experts from documents
- Autonomous learning curriculum
- Interactive chat mode
- Agentic research integration
- Budget management
- Metacognition and temporal awareness
- Best practices

**Estimated time:** 3-4 hours

---

### Task 7.2: API Documentation

**Goal:** Document all CLI commands with examples.

**Files to create:**
- `docs/cli_reference.md`

**Content:** Complete reference for all commands with examples, flags, use cases.

**Estimated time:** 4-5 hours

---

## Total Effort Estimate

**Phase 1: Complete Agentic Expert System** - 5-8 hours
**Phase 2: MCP Server Integration** - 6-9 hours
**Phase 3: Additional Semantic Commands** - 6-9 hours
**Phase 4: Observability Enhancements** - 4-6 hours
**Phase 5: Provider Routing Optimization** - 6-8 hours
**Phase 6: Testing & Validation** - 7-10 hours
**Phase 7: Documentation** - 7-9 hours

**TOTAL: 41-59 hours** (5-7 full work days)

---

## Priority Order for Implementation

1. **Task 1.1** - Knowledge base auto-update (HIGH PRIORITY, completes learning loop)
2. **Task 1.2** - Fix metacognition integration (HIGH PRIORITY, core feature)
3. **Task 1.3** - Temporal staleness detection (MEDIUM PRIORITY, quality improvement)
4. **Task 6.1** - Integration tests (MEDIUM PRIORITY, validate everything works)
5. **Task 2.1** - MCP server implementation (HIGH VALUE, ecosystem integration)
6. **Task 2.2** - MCP documentation (REQUIRED for Task 2.1)
7. **Task 4.1** - Reasoning timeline (MEDIUM PRIORITY, observability)
8. **Task 4.2** - Cost attribution (LOW PRIORITY, nice to have)
9. **Task 3.1-3.3** - Additional semantic commands (MEDIUM VALUE, user experience)
10. **Task 5.1-5.2** - Provider optimization (LOW PRIORITY, advanced feature)

---

## Notes

- All file paths are relative to project root: `c:\Users\nicks\OneDrive\deepr\`
- Test after each task to ensure no regressions
- Use GPT-5 for all OpenAI operations (not GPT-4)
- Track costs and include in budget estimates
- Keep documentation updated as features are implemented
