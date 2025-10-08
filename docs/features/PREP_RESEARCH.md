# Prep Research Feature

## Overview

**Prep Research** is Deepr's intelligent research planning system that uses GPT-5 models to decompose high-level scenarios into multiple targeted research tasks. Instead of manually creating individual research jobs, users describe a scenario and let GPT-5 plan a comprehensive, multi-angle research strategy.

## Key Concept

**One Scenario → Multiple Research Tasks**

Example:
```
User Input: "Meeting with Company X about implementing Topic Y tomorrow"

GPT-5 Plans:
1. Company X background and recent developments
2. Industry trends for Topic Y adoption
3. Technical specifications and implementation approaches
4. Competitor landscape analysis
5. Real-world use cases and ROI data
```

All tasks are executed in parallel using o3 or o4-mini deep research models, then linked together by a `batch_id` for easy tracking.

## Architecture

### Planning Phase (GPT-5)
- **Model:** GPT-5, GPT-5-mini, or GPT-5-nano (NO OLD MODELS)
- **Purpose:** Fast, intelligent decomposition of scenarios
- **Output:** 1-10 specific research prompts with titles
- **Cost:** ~$0.01-0.05 per plan

### Execution Phase (Deep Research)
- **Model:** o4-mini-deep-research or o3-deep-research
- **Purpose:** Comprehensive research with web search
- **Output:** Detailed research reports for each task
- **Cost:** $0.10-0.30 per task

## API Endpoints

### POST /api/v1/planner/plan

Plan research strategy using GPT-5.

**Request:**
```json
{
  "scenario": "Meeting with Company X about Topic Y tomorrow",
  "max_tasks": 5,
  "context": "Optional additional context",
  "planner_model": "gpt-5-mini",
  "research_model": "o4-mini-deep-research",
  "enable_web_search": true
}
```

**Response:**
```json
{
  "plan": [
    {
      "title": "Company Background Research",
      "prompt": "Research Company X's recent developments, key products, market position...",
      "estimated_cost": 0.15
    },
    {
      "title": "Industry Context and Trends",
      "prompt": "Research industry trends relevant to Topic Y...",
      "estimated_cost": 0.12
    }
  ],
  "total_estimated_cost": 0.75,
  "planner_model": "gpt-5-mini",
  "research_model": "o4-mini-deep-research"
}
```

### POST /api/v1/planner/execute

Execute a research plan by creating batch jobs.

**Request:**
```json
{
  "scenario": "Meeting with Company X about Topic Y",
  "tasks": [
    {"title": "Company Background", "prompt": "Research..."},
    {"title": "Industry Trends", "prompt": "Research..."}
  ],
  "model": "o4-mini-deep-research",
  "priority": 3,
  "enable_web_search": true
}
```

**Response:**
```json
{
  "batch_id": "batch-a1b2c3d4",
  "scenario": "Meeting with Company X about Topic Y",
  "jobs": [
    {
      "id": "job-uuid-1",
      "title": "Company Background",
      "status": "pending",
      "estimated_cost": 0.15
    }
  ],
  "total_jobs": 2,
  "total_estimated_cost": 0.27
}
```

### GET /api/v1/planner/batch/{batch_id}

Get status of all jobs in a batch.

**Response:**
```json
{
  "batch_id": "batch-a1b2c3d4",
  "scenario": "Meeting with Company X",
  "jobs": [
    {
      "id": "job-uuid-1",
      "title": "Company Background",
      "status": "completed",
      "actual_cost": 0.14
    }
  ],
  "summary": {
    "total": 2,
    "pending": 0,
    "in_progress": 0,
    "completed": 2,
    "failed": 0,
    "total_cost": 0.26
  }
}
```

## Web Interface

### Prep Research Page (`/prep`)

**Step 1: Describe Scenario**
- Large textarea for scenario description
- Optional context field
- Configuration options:
  - Max tasks (1-10)
  - Planner model (GPT-5 family)
  - Research model (o3/o4-mini)
  - Enable web search toggle

**Step 2: Review & Select Tasks**
- Generated tasks displayed as cards
- Each card shows:
  - Title
  - Full prompt
  - Estimated cost
  - Checkbox to select/deselect
- Select all/deselect all button
- Total cost calculation updates live

**Step 3: Execute**
- Choose priority level
- Click "Start Research"
- Redirects to Batch Status page

### Batch Status Page (`/batch/:batchId`)

Real-time tracking of batch progress:
- Summary cards (Total, Completed, In Progress, Pending, Failed)
- Progress bar with percentage
- List of all tasks with:
  - Title and prompt
  - Status badge
  - Cost (estimated/actual)
  - View Result button (when completed)
- Polls every 5 seconds for updates
- Link to view all results when complete

## Backend Implementation

### ResearchPlanner Service

Location: `deepr/services/research_planner.py`

```python
class ResearchPlanner:
    """Uses GPT-5 models to plan multi-angle research strategies."""

    def __init__(self, model: str = "gpt-5-mini"):
        # Validates model is GPT-5 family ONLY
        valid_models = ["gpt-5", "gpt-5-mini", "gpt-5-nano", "gpt-5-chat"]
        if model not in valid_models:
            raise ValueError("NO OLD MODELS ALLOWED")

    def plan_research(
        self,
        scenario: str,
        max_tasks: int = 5,
        context: Optional[str] = None
    ) -> List[Dict[str, str]]:
        """
        Decompose scenario into research tasks.

        Returns:
            List of {title, prompt} dictionaries
        """
```

**Key Features:**
- Strict validation: Only GPT-5 models allowed
- Fallback plan if API call fails
- JSON parsing with markdown code block handling
- Title/prompt length capping for safety

### Planner API Routes

Location: `deepr/api/routes/planner.py`

Three endpoints:
1. `/plan` - Generate research plan
2. `/execute` - Create batch jobs
3. `/batch/<id>` - Get batch status

**Batch Tracking:**
- Jobs are tagged with `batch_id` in metadata
- Scenario stored in metadata for display
- Task titles stored for easy reference

## User Workflows

### Basic Workflow
1. Navigate to `/prep`
2. Enter scenario: "Preparing for investor pitch about AI product"
3. Click "Generate Research Plan"
4. GPT-5-mini analyzes and creates 5 tasks:
   - Market size and growth trends
   - Competitive analysis
   - Customer pain points and use cases
   - Technology differentiation
   - Financial projections and benchmarks
5. Review tasks, deselect any unwanted
6. Click "Start Research (5 tasks)"
7. Redirected to `/batch/batch-xyz123`
8. Watch real-time progress as tasks complete
9. Click "View Result" on completed tasks
10. Review all research in Results Library

### Advanced Workflow
1. Use additional context field for constraints:
   - "Focus on enterprise B2B market"
   - "Technical audience, deep dive on architecture"
   - "Limited to 3 tasks, budget conscious"
2. Choose GPT-5 (not mini) for more thorough planning
3. Select o3 (not o4-mini) for highest quality research
4. Set priority to High for faster execution

## Configuration

### Environment Variables

```bash
# Required for GPT-5 planner
OPENAI_API_KEY=sk-...

# Or for Azure
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com
```

### Model Selection Guide

**Planner Models (GPT-5):**
- **gpt-5-nano**: Fastest, lowest cost, good for simple scenarios
- **gpt-5-mini**: Recommended default, great balance
- **gpt-5**: Most thorough, best for complex multi-domain scenarios

**Research Models (Deep Research):**
- **o4-mini-deep-research**: Faster, cheaper, 90% of use cases
- **o3-deep-research**: More thorough, longer outputs, complex topics

## Cost Optimization

### Typical Costs

**Planning Phase:**
- GPT-5-nano: $0.005-0.01 per plan
- GPT-5-mini: $0.01-0.03 per plan
- GPT-5: $0.03-0.05 per plan

**Execution Phase:**
- o4-mini per task: $0.08-0.15
- o3 per task: $0.15-0.30

**Example Batch:**
```
Scenario: "Preparing for vendor demo tomorrow"
Planning: $0.02 (gpt-5-mini)
5 tasks × $0.10 (o4-mini): $0.50
Total: $0.52
```

### Budget Tips

1. **Use gpt-5-mini for planning** - Best ROI
2. **Start with fewer tasks** - 3-5 is often sufficient
3. **Use o4-mini for research** - Unless you need maximum depth
4. **Review before executing** - Deselect unnecessary tasks
5. **Set monthly limits** - Configure in Settings

## Error Handling

### Fallback Planning

If GPT-5 API call fails, the planner generates a fallback plan with generic but useful research angles:
1. Background and Overview Research
2. Industry Context and Trends
3. Technical Deep Dive
4. Competitive Landscape
5. Use Cases and Applications

### Validation

- Scenario required (non-empty)
- Max tasks clamped to 1-10
- Only GPT-5 models accepted
- Task titles capped at 100 chars
- Task prompts capped at 1000 chars

### Cost Guardrails

- Budget check before execution
- Cost estimation for each task
- Total cost displayed before starting
- Daily/monthly limit enforcement

## Integration with Existing Features

### Jobs Queue
- Batch jobs appear in queue like normal jobs
- Filter by status to see batch progress
- Bulk cancel supported

### Results Library
- Batch jobs stored as individual results
- Searchable by scenario or task title
- All results tagged with batch_id (in future: batch view)

### Cost Analytics
- Batch costs rolled up in daily/monthly totals
- Cost breakdown by model includes planner + research
- Batch tracking in analytics dashboard (future)

## Future Enhancements

### Phase 2
- [ ] Batch results aggregation view
- [ ] "Re-plan" button to refine with feedback
- [ ] Template scenarios (e.g., "Investor Pitch", "Technical Review")
- [ ] Save/load scenario configurations

### Phase 3
- [ ] Multi-turn planning (refine based on initial results)
- [ ] Dependency-aware task ordering
- [ ] Automatic synthesis report combining all batch results
- [ ] Batch comparison and diff views

## Technical Notes

### Why GPT-5 for Planning?

1. **Fast:** Planning takes 2-5 seconds, not 30-60 seconds
2. **Steerable:** Excellent instruction following for structured output
3. **Cost-effective:** $0.01-0.03 vs $0.50+ for reasoning models
4. **Latest:** Access to newest capabilities and knowledge

### Why NOT Use GPT-4o?

**NO OLD MODELS.** GPT-5 family represents a significant leap in:
- Task decomposition quality
- JSON adherence
- Context understanding
- Multi-angle analysis

Old models (gpt-4o, gpt-4-turbo, etc.) are explicitly rejected.

### WebSocket Integration

Future: Real-time batch progress updates via WebSocket
- Subscribe to `batch:{batch_id}` room
- Receive `task_completed` events
- Live progress bar updates

### Batch ID Format

Format: `batch-{12 hex chars}`
Example: `batch-a1b2c3d4e5f6`

Stored in job metadata:
```python
job.metadata = {
    "batch_id": "batch-a1b2c3d4",
    "batch_scenario": "Meeting with Company X",
    "task_title": "Company Background Research"
}
```

## Example Scenarios

### Scenario 1: Investor Pitch
```
Scenario: "Preparing investor pitch for AI-powered CRM product"
Context: "Series A round, targeting enterprise B2B"

Generated Tasks:
1. Market size and TAM analysis for AI CRM
2. Competitive landscape and differentiation
3. Customer acquisition strategy and unit economics
4. Technology moat and IP positioning
5. Team background and domain expertise research
```

### Scenario 2: Technical Implementation
```
Scenario: "Implementing Kubernetes for microservices migration"
Context: "Legacy monolith, team has limited k8s experience"

Generated Tasks:
1. Kubernetes architecture best practices for migration
2. Service mesh options comparison (Istio, Linkerd, etc.)
3. CI/CD pipeline integration with k8s
4. Observability and monitoring setup
5. Security considerations and RBAC patterns
```

### Scenario 3: Competitive Analysis
```
Scenario: "Understanding competitor X's new product launch"

Generated Tasks:
1. Product features and technical specifications
2. Pricing strategy and market positioning
3. Customer reception and review analysis
4. Technology stack and architecture insights
5. Go-to-market strategy and distribution channels
```

## Support & Troubleshooting

### Common Issues

**Issue:** "Invalid planner model"
- **Solution:** Only use GPT-5 models (gpt-5, gpt-5-mini, gpt-5-nano)

**Issue:** Plan generation fails
- **Solution:** Check API keys, Azure endpoint configuration
- **Fallback:** System generates generic fallback plan automatically

**Issue:** Batch not found
- **Solution:** Batch ID must be exact match, check URL

**Issue:** High costs
- **Solution:** Use gpt-5-mini + o4-mini, reduce max_tasks

### Best Practices

1. **Start specific:** More specific scenarios = better tasks
2. **Use context:** Additional context helps GPT-5 understand constraints
3. **Review plans:** Always review before executing
4. **Track batches:** Bookmark batch URL for later reference
5. **Tag results:** Use Results Library search to find batch results

## Conclusion

Prep Research transforms research automation from **one-at-a-time manual job submission** to **intelligent multi-angle strategy planning**. By leveraging GPT-5's planning capabilities and o3/o4-mini's deep research execution, users can prepare comprehensively for meetings, pitches, technical reviews, and strategic decisions with minimal effort.

**Knowledge is Power. Automate It.**
