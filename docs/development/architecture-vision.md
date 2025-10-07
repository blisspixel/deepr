# Deepr Architecture Vision: Research-as-a-Service

## The Real Problem We're Solving

**Organizations need to execute research tasks at scale, programmatically, from multiple applications.**

### Current State
- Individual AI apps make their own Deep Research API calls
- No centralized management or queue
- No visibility into what research is running
- No cost tracking across the organization
- Can't enforce rate limits or priorities
- Results scattered across different systems

### Deepr's Solution
**A centralized research orchestration platform that acts as infrastructure**

Think of it like:
- **Kubernetes** for container orchestration
- **RabbitMQ/Kafka** for message queues
- **Jenkins** for CI/CD
- But for **AI research tasks**

---

## Architecture: Two Deployment Models

### Model 1: Enterprise Azure Deployment (Multi-Tenant SaaS)

```
┌─────────────────────────────────────────────────────────┐
│                    API Gateway Layer                     │
│            (Azure Front Door + API Management)           │
└─────────────────┬───────────────────────────────────────┘
                  │
    ┌─────────────┼─────────────┐
    │             │             │
    ▼             ▼             ▼
┌─────────┐  ┌─────────┐  ┌─────────┐
│  App A  │  │  App B  │  │  App C  │
│         │  │         │  │         │
│ POST    │  │ POST    │  │ POST    │
│/research│  │/research│  │/research│
└─────────┘  └─────────┘  └─────────┘
                  │
                  ▼
┌──────────────────────────────────────────────────────────┐
│              Deepr REST API Layer                         │
│        (Azure App Service - Auto-scaling)                 │
│                                                           │
│  - Authentication (Azure AD / API Keys)                   │
│  - Request validation                                     │
│  - Tenant isolation                                       │
│  - Rate limiting                                          │
│  - Cost tracking                                          │
└──────────────────┬────────────────────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────────────────┐
│           Azure Service Bus (Premium)                     │
│                                                           │
│  Queue Structure:                                         │
│  ├─ research-requests-high-priority                       │
│  ├─ research-requests-normal                              │
│  └─ research-requests-low-priority                        │
│                                                           │
│  Features:                                                │
│  - Duplicate detection                                    │
│  - Dead letter queue                                      │
│  - Message sessions (for ordering)                        │
│  - Auto-scaling triggers                                  │
└──────────────────┬────────────────────────────────────────┘
                   │
      ┌────────────┼────────────┐
      │            │            │
      ▼            ▼            ▼
┌──────────┐ ┌──────────┐ ┌──────────┐
│ Worker 1 │ │ Worker 2 │ │ Worker N │
│          │ │          │ │          │
│ (Container│ (Container│ (Container│
│   Apps)  │   Apps)  │   Apps)  │
└─────┬────┘ └─────┬────┘ └─────┬────┘
      │            │            │
      └────────────┼────────────┘
                   │
      ┌────────────┼────────────────────┐
      │            │                    │
      ▼            ▼                    ▼
┌──────────┐ ┌──────────┐ ┌─────────────────┐
│  Azure   │ │  Cosmos  │ │  Azure Blob     │
│  OpenAI  │ │    DB    │ │   Storage       │
│          │ │          │ │                 │
│ Research │ │ Job State│ │ Report Storage  │
│   API    │ │ Tracking │ │  + Versioning   │
└──────────┘ └──────────┘ └─────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────────────────┐
│              Monitoring & Analytics                       │
│                                                           │
│  - Application Insights (telemetry)                       │
│  - Azure Monitor (alerts)                                 │
│  - Power BI Dashboard (cost/usage)                        │
└──────────────────────────────────────────────────────────┘
```

### Model 2: Local Development (Single-User)

```
┌──────────────────────────────────────────┐
│         Web UI (localhost:5000)          │
│                                          │
│  - Submit research                       │
│  - View queue                            │
│  - Monitor progress                      │
│  - Download reports                      │
└────────────────┬─────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────┐
│     Local Queue Manager (SQLite)         │
│                                          │
│  Table: research_queue                   │
│  - id, priority, status, created_at      │
│  - prompt, model, options                │
│  - result_path, error                    │
│                                          │
│  Watched Directories:                    │
│  - queue/inbox/*.txt (auto-import)       │
└────────────────┬─────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────┐
│      Background Worker Process           │
│      (asyncio event loop)                │
│                                          │
│  - Polls queue every 5 seconds           │
│  - Processes jobs one-at-a-time          │
│  - Updates status in SQLite              │
└────────────────┬─────────────────────────┘
                 │
      ┌──────────┼──────────┐
      │          │          │
      ▼          ▼          ▼
┌─────────┐ ┌─────────┐ ┌──────────┐
│ OpenAI  │ │ Local   │ │ JSONL    │
│   or    │ │ Storage │ │ Job Log  │
│  Azure  │ │(reports)│ │          │
└─────────┘ └─────────┘ └──────────┘
```

---

## Queue System Design

### Enterprise Queue Schema (Cosmos DB)

```json
{
  "id": "req_abc123",
  "partition_key": "tenant_company_xyz",
  "type": "research_request",
  "status": "queued",
  "priority": 5,
  "submitted_at": "2025-01-15T10:00:00Z",
  "submitted_by": "app_sales_intelligence",
  "tenant_id": "tenant_company_xyz",
  "workspace_id": "workspace_sales",

  "request": {
    "prompt": "Analyze competitor X's pricing strategy",
    "model": "o3-deep-research",
    "documents": [],
    "enable_web_search": true,
    "cost_limit": 5.00
  },

  "execution": {
    "worker_id": null,
    "started_at": null,
    "completed_at": null,
    "provider_job_id": null,
    "attempts": 0,
    "last_error": null
  },

  "results": {
    "report_urls": {},
    "cost": null,
    "token_usage": null
  },

  "metadata": {
    "tags": ["sales", "competitor-analysis"],
    "callback_url": "https://app.company.com/webhook",
    "ttl": 604800
  }
}
```

### Local Queue Schema (SQLite)

```sql
CREATE TABLE research_queue (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL,  -- queued, processing, completed, failed
    priority INTEGER DEFAULT 5,
    submitted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    started_at DATETIME,
    completed_at DATETIME,

    prompt TEXT NOT NULL,
    model TEXT DEFAULT 'o3-deep-research',
    documents TEXT,  -- JSON array
    options TEXT,    -- JSON object

    provider_job_id TEXT,
    worker_id TEXT,
    attempts INTEGER DEFAULT 0,
    last_error TEXT,

    report_path TEXT,
    cost REAL,
    tokens_used INTEGER
);

CREATE INDEX idx_status_priority ON research_queue(status, priority DESC);
CREATE INDEX idx_submitted_at ON research_queue(submitted_at);
```

---

## REST API Design (Enterprise)

### Authentication
```http
POST /api/v1/research
Authorization: Bearer <token>
X-Tenant-ID: company_xyz
X-Workspace-ID: workspace_sales
```

### Endpoints

#### 1. Submit Research Request
```http
POST /api/v1/research
Content-Type: application/json

{
  "prompt": "Analyze competitor pricing strategies",
  "model": "o3-deep-research",
  "priority": 5,
  "options": {
    "enable_web_search": true,
    "enable_code_interpreter": false,
    "cost_limit": 10.0
  },
  "documents": [
    {"url": "https://storage/doc1.pdf"}
  ],
  "metadata": {
    "tags": ["sales", "pricing"],
    "callback_url": "https://app.com/webhook"
  }
}

Response 202 Accepted:
{
  "request_id": "req_abc123",
  "status": "queued",
  "position": 3,
  "estimated_wait": "5m",
  "status_url": "/api/v1/research/req_abc123"
}
```

#### 2. Check Status
```http
GET /api/v1/research/{request_id}

Response 200 OK:
{
  "request_id": "req_abc123",
  "status": "processing",
  "progress": 45,
  "started_at": "2025-01-15T10:05:00Z",
  "estimated_completion": "2025-01-15T10:15:00Z"
}
```

#### 3. List Queue
```http
GET /api/v1/research?status=queued&limit=10

Response 200 OK:
{
  "total": 47,
  "items": [
    {
      "request_id": "req_abc123",
      "status": "queued",
      "priority": 5,
      "submitted_at": "2025-01-15T10:00:00Z"
    }
  ]
}
```

#### 4. Get Results
```http
GET /api/v1/research/{request_id}/results

Response 200 OK:
{
  "request_id": "req_abc123",
  "status": "completed",
  "results": {
    "formats": {
      "markdown": "https://storage/report.md",
      "docx": "https://storage/report.docx",
      "json": "https://storage/report.json"
    },
    "preview": "First 500 chars...",
    "cost": 2.45,
    "tokens_used": 15000
  }
}
```

#### 5. Cancel Request
```http
DELETE /api/v1/research/{request_id}

Response 200 OK:
{
  "request_id": "req_abc123",
  "status": "cancelled"
}
```

#### 6. Bulk Submit
```http
POST /api/v1/research/bulk
Content-Type: application/json

{
  "requests": [
    {"prompt": "Research topic 1", ...},
    {"prompt": "Research topic 2", ...}
  ]
}

Response 202 Accepted:
{
  "batch_id": "batch_xyz",
  "request_ids": ["req_1", "req_2"],
  "status_url": "/api/v1/batches/batch_xyz"
}
```

---

## Worker Architecture

### Enterprise Worker (Container App)

```python
# deepr/workers/azure_worker.py

import asyncio
from azure.servicebus.aio import ServiceBusClient
from deepr.core import ResearchOrchestrator

class AzureResearchWorker:
    def __init__(self, service_bus_conn_str, queue_name):
        self.sb_client = ServiceBusClient.from_connection_string(service_bus_conn_str)
        self.queue_name = queue_name
        self.orchestrator = None  # Initialize with provider/storage

    async def run(self):
        async with self.sb_client:
            receiver = self.sb_client.get_queue_receiver(self.queue_name)

            async with receiver:
                while True:
                    messages = await receiver.receive_messages(max_message_count=1, max_wait_time=5)

                    for message in messages:
                        try:
                            await self.process_message(message)
                            await receiver.complete_message(message)
                        except Exception as e:
                            # Dead letter queue
                            await receiver.dead_letter_message(message, reason=str(e))

    async def process_message(self, message):
        request_data = message.body

        # Update status in Cosmos DB
        await self.update_status(request_data['id'], 'processing')

        # Execute research
        job_id = await self.orchestrator.submit_research(
            prompt=request_data['prompt'],
            model=request_data['model']
        )

        # Poll for completion
        # Save results
        # Update Cosmos DB
        # Send webhook callback
```

### Local Worker (Background Process)

```python
# deepr/workers/local_worker.py

import asyncio
import sqlite3
from deepr.core import ResearchOrchestrator

class LocalResearchWorker:
    def __init__(self, db_path, orchestrator):
        self.db_path = db_path
        self.orchestrator = orchestrator

    async def run(self):
        while True:
            # Get next job from queue
            job = self.get_next_job()

            if job:
                await self.process_job(job)
            else:
                await asyncio.sleep(5)

    def get_next_job(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, prompt, model, documents, options
            FROM research_queue
            WHERE status = 'queued'
            ORDER BY priority DESC, submitted_at ASC
            LIMIT 1
        """)

        return cursor.fetchone()

    async def process_job(self, job):
        job_id, prompt, model, documents, options = job

        # Update status
        self.update_status(job_id, 'processing')

        try:
            # Execute research
            result_id = await self.orchestrator.submit_research(prompt, model)

            # Wait for completion (with polling)
            # ...

            # Save results
            self.update_status(job_id, 'completed', result_path='/path/to/report')

        except Exception as e:
            self.update_status(job_id, 'failed', error=str(e))
```

---

## Why This Matters

### For Enterprises
1. **Centralized Management** - All research in one place
2. **Cost Control** - Track spending across the organization
3. **Rate Limiting** - Prevent API quota exhaustion
4. **Priority Queuing** - Critical tasks first
5. **Multi-Tenancy** - Isolate teams/departments
6. **Audit Trail** - Who requested what, when, and why
7. **Integration** - Any app can use it via REST API

### For Developers
1. **Simple Integration** - POST request, get result
2. **No API Key Management** - Deepr handles it
3. **Reliable Execution** - Retries, error handling
4. **Webhook Callbacks** - Async notification
5. **Batch Processing** - Submit 100 tasks at once

### Example Use Cases

**Sales Intelligence App:**
```python
response = requests.post('https://deepr.company.com/api/v1/research', json={
    'prompt': f'Analyze {competitor} pricing strategy',
    'metadata': {'callback_url': 'https://sales-app/webhook'}
})
request_id = response.json()['request_id']
# Continue working, webhook will notify when done
```

**Content Marketing Tool:**
```python
# Generate 20 research briefs
prompts = generate_content_ideas()  # AI-generated list

requests.post('https://deepr.company.com/api/v1/research/bulk', json={
    'requests': [{'prompt': p} for p in prompts]
})
# All 20 get queued and processed
```

**Compliance Monitoring:**
```python
# Daily cron job
response = requests.post('https://deepr.company.com/api/v1/research', json={
    'prompt': 'Summarize new FDA regulations from the past 24 hours',
    'priority': 10,  # High priority
    'metadata': {'tags': ['compliance', 'daily']}
})
```

---

## Next Steps to Build This

1. **Queue System Implementation** (Week 1)
   - SQLite queue for local
   - Azure Service Bus integration for cloud
   - Worker process architecture

2. **REST API Layer** (Week 2)
   - FastAPI or Flask
   - Authentication (API keys + Azure AD)
   - Request validation and rate limiting

3. **Web UI** (Week 2)
   - Queue management dashboard
   - Real-time status updates (WebSockets)
   - Cost tracking and analytics

4. **Multi-Tenancy** (Week 3)
   - Tenant isolation in Cosmos DB
   - Workspace concept
   - Access control

5. **Testing** (Ongoing)
   - Integration tests with real providers
   - Load testing
   - Chaos engineering for workers

This is the real vision - **infrastructure for research at scale**.
