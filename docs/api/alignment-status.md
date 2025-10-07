# OpenAI Deep Research API - Alignment Status

This document tracks Deepr's alignment with the official OpenAI Deep Research API features and capabilities.

Reference: [docs/api/openai-deep-research-full.txt](openai-deep-research-full.txt)

## Current Implementation Status

### Core Features

| Feature | Status | Notes |
|---------|--------|-------|
| o3-deep-research model | Supported | Model mapping in place |
| o4-mini-deep-research model | Supported | Default model for cost savings |
| Responses API integration | Partial | Basic structure exists, needs completion |
| Background mode | Not Implemented | Critical for production use |
| Webhooks | Partial | v1.x has ngrok support, needs v2 integration |

### Tools and Data Sources

| Tool | Status | Notes |
|------|--------|-------|
| web_search_preview | Supported | Via tool configuration |
| file_search with vector stores | Not Implemented | Requires vector store integration |
| code_interpreter | Supported | Via tool configuration |
| MCP (Model Context Protocol) | Not Implemented | Required for internal data access |
| Connectors (Dropbox, Gmail) | Not Implemented | Third-party integrations |

### Prompting Features

| Feature | Status | Notes |
|---------|--------|-------|
| Clarification questions | Partial | v1.x has basic support |
| Prompt rewriting/enrichment | Partial | v1.x uses GPT-4 for refinement |
| System instructions | Supported | Via configuration |
| Multi-step clarification flow | Not Implemented | Needs structured workflow |

### Output Structure

| Feature | Status | Notes |
|---------|--------|-------|
| Inline citations | Not Implemented | Critical for credibility |
| Annotations with URL metadata | Not Implemented | Required by API spec |
| Web search call tracking | Not Implemented | Useful for debugging |
| Code interpreter call tracking | Not Implemented | Transparency feature |
| MCP tool call tracking | Not Implemented | N/A until MCP implemented |
| Reasoning summaries | Not Implemented | Optional transparency |

### Output Formats

| Format | Status | Notes |
|--------|--------|-------|
| JSON | Supported | Basic implementation |
| Markdown | Supported | Primary format |
| Plain text | Supported | Simple export |
| DOCX | Supported | Professional output |
| PDF | Not Implemented | Planned for v2.1 |

### Best Practices Compliance

| Practice | Status | Notes |
|----------|--------|-------|
| Background mode for long tasks | Not Implemented | High priority |
| Webhook notifications | Partial | Needs v2 integration |
| Higher timeout settings | Supported | Configurable |
| max_tool_calls parameter | Not Implemented | Cost control mechanism |
| Detailed system instructions | Supported | Via config |

### Safety and Security

| Feature | Status | Notes |
|---------|--------|-------|
| Prompt injection awareness | Not Implemented | Documentation only |
| MCP server trust validation | Not Implemented | N/A until MCP |
| Tool call logging | Partial | Basic logging exists |
| Staged workflow (public then private) | Not Implemented | Security best practice |
| Link screening | Not Implemented | Security feature |
| Data exfiltration monitoring | Not Implemented | Advanced security |

---

## Critical Gaps

### High Priority (Blocking Production Use)

1. **Background Mode**
   - Status: Not Implemented
   - Impact: Deep research takes 10+ minutes, synchronous calls timeout
   - Required: Full async execution with job tracking
   - API: `client.responses.create(background=True, ...)`

2. **Inline Citations and Annotations**
   - Status: Not Implemented
   - Impact: Results lack credibility and traceability
   - Required: Parse and preserve annotation metadata
   - API: Access via `response.output[-1].content[0].annotations`

3. **Webhook Integration**
   - Status: Partial (v1.x only)
   - Impact: Cannot reliably receive completion notifications
   - Required: Webhook URL registration and callback handling
   - API: Configure webhook in OpenAI dashboard

4. **MCP Server Support**
   - Status: Not Implemented
   - Impact: Cannot access private/internal data
   - Required: MCP search/fetch interface implementation
   - API: `{"type": "mcp", "server_url": "...", "require_approval": "never"}`

### Medium Priority (Feature Completeness)

5. **Vector Store / File Search**
   - Status: Not Implemented
   - Impact: Cannot search over uploaded documents
   - Required: Vector store management and file search tool
   - API: `{"type": "file_search", "vector_store_ids": [...]}`

6. **Clarification Workflow**
   - Status: Partial
   - Impact: Suboptimal prompts lead to poor results
   - Required: Structured clarification + prompt rewriting
   - API: Multi-turn conversation with gpt-4.1 before research

7. **Tool Call Transparency**
   - Status: Not Implemented
   - Impact: Users cannot see what searches were performed
   - Required: Parse and display intermediate steps
   - API: Iterate `response.output` for web_search_call items

8. **Cost Control**
   - Status: Partial (estimation only)
   - Impact: Cannot limit actual tool calls
   - Required: max_tool_calls parameter support
   - API: `client.responses.create(max_tool_calls=50, ...)`

### Low Priority (Nice to Have)

9. **Reasoning Summaries**
   - Status: Not Implemented
   - Impact: Limited insight into research process
   - API: `reasoning={"summary": "auto"}` or `"detailed"`

10. **Code Interpreter Tracking**
    - Status: Not Implemented
    - Impact: Cannot see analysis/charts generated
    - API: Parse `code_interpreter_call` items

11. **Safety Monitoring**
    - Status: Not Implemented
    - Impact: No protection against prompt injection
    - Required: LLM-based monitor for suspicious tool calls

---

## Implementation Recommendations

### Phase 1: Core Functionality (v2.0)

```python
# Example: Background mode with webhook
response = client.responses.create(
    model="o3-deep-research-2025-06-26",
    input=[
        {"role": "developer", "content": [{"type": "input_text", "text": system_message}]},
        {"role": "user", "content": [{"type": "input_text", "text": user_query}]}
    ],
    background=True,  # ← CRITICAL
    reasoning={"summary": "auto"},
    tools=[
        {"type": "web_search_preview"},
        {"type": "code_interpreter", "container": {"type": "auto"}}
    ]
)

# Response contains job_id, poll for status or receive webhook
```

### Phase 2: Data Access (v2.1)

```python
# Example: MCP for internal documents
tools=[
    {"type": "web_search_preview"},
    {
        "type": "mcp",
        "server_label": "internal_docs",
        "server_url": "https://your-mcp-server.com/sse",
        "require_approval": "never"
    }
]
```

### Phase 3: Citations and Transparency (v2.1)

```python
# Example: Parse citations
annotations = response.output[-1].content[0].annotations
for citation in annotations:
    print(f"[{citation.start_index}:{citation.end_index}] {citation.title}")
    print(f"  URL: {citation.url}")
```

### Phase 4: Advanced Features (v2.2+)

- Vector store management
- Clarification agent pipeline
- Tool call monitoring
- Safety filters

---

## Alignment Score

**Current:** 45% aligned with OpenAI Deep Research API specification

**Breakdown:**
- Core API calls: 60%
- Tools support: 40%
- Output handling: 30%
- Best practices: 35%
- Safety features: 10%

**Target v2.0:** 75% aligned
**Target v2.1:** 90% aligned
**Target v2.2:** 95% aligned

---

## References

- [OpenAI Deep Research API Documentation](openai-deep-research-full.txt)
- [OpenAI Cookbook - Deep Research](https://cookbook.openai.com/examples/deep_research)
- [Model Context Protocol Guide](https://platform.openai.com/docs/guides/mcp)

---

**Last Updated:** 2025-10-07
