# MCP Integration Refinement Plan

Analysis based on Anthropic's Knowledge Work Plugins architecture and Model Context Protocol patterns, applied to Deepr's existing implementation.

---

## Current State Assessment

Deepr's MCP integration already implements several advanced patterns well:

| Pattern | Implementation | Status |
|---------|----------------|--------|
| Dynamic Tool Discovery | BM25 search via `deepr_tool_search` | Complete |
| Resource Subscriptions | Push notifications for job status | Complete |
| Human-in-the-Loop Elicitation | Budget decisions with 3 options | Complete |
| Sandboxed Execution | Isolated research contexts | Complete |
| Progressive Disclosure | SKILL.md + references/ directory | Partial |
| Structured Errors | Error codes, retry hints, fallbacks | Complete |
| Multi-Runtime Configs | 5 runtimes supported | Complete |

**Context Reduction Achieved:** 85%+ via gateway pattern

---

## Identified Gaps and Opportunities

### Gap 1: Commands Directory (Imperative Entry Points)

**Research Insight (Section 2.1.1):**
> "Commands map to imperative programming: the user explicitly tells the agent what to do. Skills map to declarative programming: the agent observes the context and infers how to act."

**Current State:** Deepr only has `skills/` directory with SKILL.md
**Opportunity:** Add explicit `commands/` directory for slash commands

**Proposed Structure:**
```
skills/deepr-research/
├── SKILL.md              # Declarative (agent-triggered)
├── commands/             # Imperative (user-triggered)
│   ├── research.md       # /research <query>
│   ├── expert.md         # /expert <name> <question>
│   ├── check.md          # /check <job_id>
│   └── costs.md          # /costs [period]
└── references/           # Detail appendix
```

**Benefit:** Users get deterministic, predictable entry points while agent retains flexibility for autonomous operation.

---

### Gap 2: Security Scoping via `allowed-tools`

**Research Insight (Section 4.3):**
> "The `allowed-tools` field acts as a security scope, preventing this skill from accessing unrelated tools."

**Current State:** SKILL.md lists tools but doesn't enforce boundaries
**Opportunity:** Add `allowed-tools` to frontmatter with server-side enforcement

**Proposed SKILL.md Enhancement:**
```yaml
---
name: deepr-research
description: Deep research infrastructure...
allowed-tools:
  - deepr_tool_search
  - deepr_research
  - deepr_check_status
  - deepr_get_result
  - deepr_cancel_job
  - deepr_agentic_research
restricted-tools:  # Explicitly excluded
  - deepr_delete_expert
  - deepr_reset_costs
---
```

**Implementation:** MCP server checks skill context before tool execution.

---

### Gap 3: Plugin Manifest (.claude-plugin/plugin.json)

**Research Insight (Section 2.1.1):**
> "The entry point for any plugin lies in a strict folder structure that enforces separation of concerns."

**Current State:** No standard plugin manifest
**Opportunity:** Add `.claude-plugin/` directory for better discoverability

**Proposed Structure:**
```
skills/deepr-research/
├── .claude-plugin/
│   └── plugin.json       # Identity, version, dependencies
├── .mcp.json             # Server configuration
├── SKILL.md
├── commands/
└── references/
```

**plugin.json:**
```json
{
  "name": "deepr-research",
  "version": "2.6.0",
  "description": "Deep research infrastructure for comprehensive analysis",
  "author": "Nick Seal",
  "license": "MIT",
  "homepage": "https://github.com/blisspixel/deepr",
  "requires": {
    "python": ">=3.9",
    "bins": ["python3"],
    "env": ["OPENAI_API_KEY"]
  },
  "mcp": {
    "config": ".mcp.json"
  }
}
```

**Benefit:** Standard format enables plugin marketplaces, automated installation, dependency management.

---

### Gap 4: Meta-Skill for Expert Creation

**Research Insight (Section 2.2.3):**
> "The Meta-Plugin uses the user's description to generate the plugin.json, .mcp.json, and SKILL.md files required to instantiate that agent."

**Current State:** Experts created manually via CLI
**Opportunity:** Add skill for programmatic expert creation

**Proposed Skill: `expert-builder`**
```yaml
---
name: expert-builder
description: |
  Use when user wants to create a new domain expert from documents.
  Automates: document ingestion, knowledge synthesis, belief formation.
allowed-tools:
  - deepr_create_expert
  - deepr_ingest_documents
  - deepr_synthesize_knowledge
---

# Expert Builder Protocol

## When to Use
- User has domain documents they want to create an expert from
- User describes a role (e.g., "Investment Banking Analyst")

## Workflow
1. Clarify the expert's domain and scope
2. Identify source documents (files, URLs, knowledge bases)
3. Estimate cost for ingestion and synthesis
4. Create expert with initial knowledge
5. Verify with test queries
6. Suggest gap-filling research
```

**Benefit:** Enables recursive self-improvement - agent can create specialized sub-agents.

---

### Gap 5: Expanded Prompt Templates

**Research Insight (Section 3.3.3):**
> "Prompts encapsulate a specific way of using the tools. It is a 'stored procedure' for the interaction layer."

**Current State:** 3 prompts (deep_research_task, expert_consultation, comparative_analysis)
**Opportunity:** Add domain-specific prompt templates

**Proposed Additional Prompts:**

| Prompt | Use Case |
|--------|----------|
| `incident_report` | Structured post-mortem with root cause analysis |
| `decision_matrix` | Multi-criteria decision support with weighted scoring |
| `literature_review` | Academic-style synthesis with citation management |
| `competitive_analysis` | Market positioning with SWOT framework |
| `technical_deep_dive` | Architecture analysis with trade-off documentation |
| `gap_analysis` | Identify knowledge gaps and suggest research priorities |

**Implementation:**
```python
@mcp.prompt("incident-report")
def incident_report_prompt(incident_id: str, service: str) -> str:
    return f"""
    Analyze incident {incident_id} affecting {service}.

    Structure your response as:
    1. Timeline: What happened and when
    2. Impact: Users/systems affected
    3. Root Cause: Technical and process factors
    4. Resolution: Actions taken
    5. Prevention: Recommended changes

    Use deepr_research if you need to investigate external factors.
    Use deepr_query_expert if domain expertise is available.
    """
```

---

### Gap 6: Resource Templates with Dynamic URIs

**Research Insight (Section 3.3.2):**
> "Servers can define templates (e.g., `file:///{path}`) to expose dynamic classes of data."

**Current State:** Fixed resource URIs
**Opportunity:** Add parameterized resource templates

**Proposed Templates:**
```python
# Current: Fixed URIs
"deepr://experts/{id}/beliefs"

# Proposed: Parameterized templates
@mcp.resource_template("deepr://experts/{expert_id}/beliefs/{topic}")
def get_expert_beliefs_on_topic(expert_id: str, topic: str) -> str:
    """Get expert beliefs filtered by topic."""
    expert = load_expert(expert_id)
    return expert.filter_beliefs(topic=topic)

@mcp.resource_template("deepr://reports/{report_id}/section/{section_name}")
def get_report_section(report_id: str, section_name: str) -> str:
    """Get specific section of a report."""
    report = load_report(report_id)
    return report.get_section(section_name)
```

**Benefit:** Fine-grained access to large resources without loading entire documents.

---

### Gap 7: Governance Skills (Best Practice Enforcement)

**Research Insight (Section 5.3):**
> "Codify Best Practices: Translate your team's 'Contributing Guidelines' into SKILL.md files."

**Current State:** Cost controls exist but no research quality governance
**Opportunity:** Add skills that enforce research standards

**Proposed Skill: `research-governance`**
```yaml
---
name: research-governance
description: |
  Enforces research quality standards. Automatically triggered when:
  - Research results are returned
  - Expert answers are generated
  - Reports are synthesized
allowed-tools:
  - deepr_check_citations
  - deepr_verify_sources
  - deepr_flag_uncertainty
---

# Research Governance Protocol

## Quality Gates
1. **Citation Verification**: All claims must have inline citations
2. **Source Diversity**: Minimum 3 independent sources
3. **Recency Check**: Flag data older than configured threshold
4. **Uncertainty Flagging**: Confidence scores on all assertions

## When Sources Are Weak
- Flag with: "[LOW CONFIDENCE: Single source]"
- Suggest: "Would you like me to research this further?"
```

---

## Implementation Roadmap

### Phase 1: Foundation (Low Effort, High Value)

1. **Add `allowed-tools` to SKILL.md frontmatter** - Server-side enforcement
2. **Create `commands/` directory** - Start with 4 core commands
3. **Add 3 new prompt templates** - incident_report, decision_matrix, gap_analysis

**Estimated Effort:** 1-2 days
**Risk:** Low

### Phase 2: Structure (Medium Effort)

4. **Add `.claude-plugin/plugin.json` manifest** - Standard format
5. **Add resource templates** - Parameterized URIs
6. **Document Phase-based setup** - User onboarding guide

**Estimated Effort:** 2-3 days
**Risk:** Low

### Phase 3: Intelligence (Higher Effort)

7. **Create expert-builder skill** - Programmatic expert creation
8. **Add research-governance skill** - Quality enforcement
9. **Implement meta-skill workflow** - Recursive improvement

**Estimated Effort:** 3-5 days
**Risk:** Medium

---

## Key Architectural Principles from Research

1. **Separation of Concerns**
   - Commands (imperative) vs Skills (declarative)
   - Tools (execution) vs Resources (data) vs Prompts (templates)

2. **Progressive Disclosure**
   - Level 1: Metadata index (frontmatter only)
   - Level 2: Skill body (loaded when relevant)
   - Level 3: References (loaded on demand)

3. **Security Through Scoping**
   - `allowed-tools` restricts skill capabilities
   - Sandbox isolation for heavy processing
   - Path validation prevents traversal attacks

4. **Recursive Self-Improvement**
   - Meta-plugins that create other plugins
   - Gap analysis workflows for tool generation
   - Agent-driven capability expansion

---

## Success Metrics

| Metric | Current | Target |
|--------|---------|--------|
| Context reduction | 85% | 90% |
| Prompt templates | 3 | 9 |
| Command coverage | 0 | 10+ |
| Security scoping | None | All skills |
| Resource templates | Fixed | Parameterized |

---

## References

- [Anthropic Knowledge Work Plugins](https://github.com/anthropics/knowledge-work-plugins)
- [Model Context Protocol Specification](https://modelcontextprotocol.io/specification)
- [MCP Patterns Reference](references/mcp_patterns.md)
- [Deepr MCP Server Architecture](../mcp/README.md)
