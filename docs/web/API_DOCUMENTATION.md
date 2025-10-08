# Deepr API Documentation

**Base URL:** `http://localhost:5000/api/v1`

**Version:** 2.0.0

## Authentication

Currently no authentication required for local deployment. Future versions will support API keys for cloud deployments.

---

## Jobs API

### Submit Research Job

```http
POST /api/v1/jobs
Content-Type: application/json

{
  "prompt": "Research quantum computing impact on cryptography",
  "model": "o4-mini-deep-research",
  "priority": 1,
  "enable_web_search": true,
  "file_ids": [],
  "config": {}
}
```

**Response (201):**
```json
{
  "job": {
    "id": "f6e2e738",
    "prompt": "Research quantum computing...",
    "model": "o4-mini-deep-research",
    "status": "pending",
    "priority": 1,
    "estimated_cost": 2.50,
    "created_at": "2025-10-08T12:00:00Z"
  },
  "estimated_cost": {
    "expected_cost": 2.50,
    "min_cost": 1.50,
    "max_cost": 4.00
  }
}
```

**Error (429):**
```json
{
  "error": "Daily budget exceeded",
  "estimated_cost": {...}
}
```

### List Jobs

```http
GET /api/v1/jobs?status=pending&limit=50&offset=0
```

**Query Parameters:**
- `status` (optional): Filter by status (pending, in_progress, completed, failed)
- `limit` (optional): Max results (default: 50, max: 100)
- `offset` (optional): Pagination offset (default: 0)

**Response (200):**
```json
{
  "jobs": [
    {
      "id": "f6e2e738",
      "prompt": "...",
      "status": "completed",
      "created_at": "2025-10-08T12:00:00Z"
    }
  ],
  "total": 42,
  "limit": 50,
  "offset": 0
}
```

### Get Job Details

```http
GET /api/v1/jobs/{job_id}
```

**Response (200):**
```json
{
  "job": {
    "id": "f6e2e738",
    "prompt": "Research quantum computing...",
    "model": "o4-mini-deep-research",
    "status": "completed",
    "priority": 1,
    "estimated_cost": 2.50,
    "actual_cost": 2.35,
    "created_at": "2025-10-08T12:00:00Z",
    "updated_at": "2025-10-08T12:05:23Z"
  }
}
```

### Cancel Job

```http
POST /api/v1/jobs/{job_id}/cancel
```

**Response (200):**
```json
{
  "message": "Job cancelled successfully"
}
```

### Delete Job

```http
DELETE /api/v1/jobs/{job_id}
```

**Response (204):** No content

### Batch Submit

```http
POST /api/v1/jobs/batch
Content-Type: application/json

{
  "jobs": [
    {
      "prompt": "Research topic 1",
      "model": "o4-mini-deep-research"
    },
    {
      "prompt": "Research topic 2",
      "model": "o3-deep-research"
    }
  ]
}
```

**Response (201):**
```json
{
  "created": [...],
  "errors": [...],
  "total": 2,
  "successful": 2,
  "failed": 0
}
```

---

## Results API

### List Results

```http
GET /api/v1/results?search=quantum&limit=50
```

**Query Parameters:**
- `search` (optional): Full-text search query
- `tags` (optional): Filter by tags (comma-separated)
- `limit` (optional): Max results (default: 50, max: 100)
- `offset` (optional): Pagination offset
- `sort` (optional): Sort field (date, cost, name)
- `order` (optional): Sort order (asc, desc)

**Response (200):**
```json
{
  "results": [
    {
      "job_id": "f6e2e738",
      "title": "Quantum Computing Impact on Cryptography",
      "created_at": "2025-10-08T12:00:00Z",
      "cost": 2.35,
      "tags": ["quantum", "cryptography"]
    }
  ],
  "total": 15,
  "limit": 50,
  "offset": 0
}
```

### Get Result

```http
GET /api/v1/results/{job_id}
```

**Response (200):**
```json
{
  "result": {
    "job_id": "f6e2e738",
    "title": "...",
    "content": "# Research Report\n\n...",
    "citations": [...],
    "metadata": {...},
    "created_at": "2025-10-08T12:00:00Z",
    "cost": 2.35
  }
}
```

### Download Result

```http
GET /api/v1/results/{job_id}/download/{format}
```

**Formats:** `md`, `docx`, `txt`, `json`, `pdf`

**Response (200):** File download with appropriate Content-Type

### Search Results

```http
GET /api/v1/results/search?q=quantum&limit=20
```

**Response (200):**
```json
{
  "query": "quantum",
  "results": [...],
  "total": 5
}
```

### Add Tags

```http
POST /api/v1/results/{job_id}/tags
Content-Type: application/json

{
  "tags": ["quantum", "cryptography", "research"]
}
```

**Response (200):**
```json
{
  "message": "Tags added successfully",
  "tags": ["quantum", "cryptography", "research"]
}
```

### Remove Tag

```http
DELETE /api/v1/results/{job_id}/tags/{tag}
```

**Response (200):**
```json
{
  "message": "Tag removed successfully"
}
```

---

## Cost Analytics API

### Get Summary

```http
GET /api/v1/cost/summary
```

**Response (200):**
```json
{
  "summary": {
    "daily": 45.50,
    "daily_limit": 100.00,
    "monthly": 320.75,
    "monthly_limit": 1000.00
  }
}
```

### Get Trends

```http
GET /api/v1/cost/trends?days=30
```

**Response (200):**
```json
{
  "trends": {
    "daily": [
      {"date": "2025-10-01", "cost": 5.25, "jobs": 3},
      {"date": "2025-10-02", "cost": 8.50, "jobs": 5}
    ],
    "cumulative": 320.75
  },
  "days": 30
}
```

### Get Breakdown

```http
GET /api/v1/cost/breakdown?by=model&days=30
```

**Response (200):**
```json
{
  "breakdown": {
    "dimension": "model",
    "items": [
      {"name": "o4-mini-deep-research", "cost": 150.25, "count": 45},
      {"name": "o3-deep-research", "cost": 170.50, "count": 12}
    ]
  },
  "days": 30
}
```

### Estimate Cost

```http
POST /api/v1/cost/estimate
Content-Type: application/json

{
  "prompt": "Research quantum computing",
  "model": "o4-mini-deep-research",
  "enable_web_search": true
}
```

**Response (200):**
```json
{
  "estimate": {
    "expected_cost": 2.50,
    "min_cost": 1.50,
    "max_cost": 4.00
  },
  "allowed": true,
  "reason": null
}
```

### Get Budget Limits

```http
GET /api/v1/cost/limits
```

**Response (200):**
```json
{
  "limits": {
    "per_job": 10.00,
    "daily": 100.00,
    "monthly": 1000.00
  }
}
```

### Update Budget Limits

```http
PATCH /api/v1/cost/limits
Content-Type: application/json

{
  "per_job": 15.00,
  "daily": 150.00,
  "monthly": 1500.00
}
```

**Response (200):**
```json
{
  "message": "Limits updated successfully",
  "limits": {
    "per_job": 15.00,
    "daily": 150.00,
    "monthly": 1500.00
  }
}
```

---

## Configuration API

### Get Configuration

```http
GET /api/v1/config
```

**Response (200):**
```json
{
  "config": {
    "provider": "openai",
    "default_model": "o4-mini-deep-research",
    "enable_web_search": true,
    "storage": "local",
    "queue": "local",
    "has_api_key": true
  }
}
```

### Update Configuration

```http
PATCH /api/v1/config
Content-Type: application/json

{
  "provider": "azure",
  "api_key": "...",
  "default_model": "o3-deep-research"
}
```

**Response (200):**
```json
{
  "message": "Configuration updated successfully"
}
```

### Test Connection

```http
POST /api/v1/config/test
Content-Type: application/json

{
  "provider": "openai",
  "api_key": "sk-..."
}
```

**Response (200):**
```json
{
  "status": "success",
  "message": "Connection successful",
  "provider": "openai"
}
```

### Get System Status

```http
GET /api/v1/config/status
```

**Response (200):**
```json
{
  "status": {
    "healthy": true,
    "version": "2.0.0",
    "provider": "openai",
    "queue": {
      "type": "local",
      "stats": {
        "pending": 5,
        "in_progress": 2,
        "completed": 42,
        "failed": 1
      }
    },
    "spending": {
      "daily": 45.50,
      "monthly": 320.75
    }
  }
}
```

---

## WebSocket Events

**Connection URL:** `ws://localhost:5000`

### Client → Server Events

#### Subscribe to Jobs

```javascript
socket.emit('subscribe_jobs', {
  scope: 'all'  // or 'job' with job_id
});
```

#### Unsubscribe from Jobs

```javascript
socket.emit('unsubscribe_jobs', {
  scope: 'all'
});
```

### Server → Client Events

#### Connected

```javascript
socket.on('connected', (data) => {
  console.log(data.message);
});
```

#### Job Created

```javascript
socket.on('job_created', (job) => {
  console.log('New job:', job);
});
```

#### Job Updated

```javascript
socket.on('job_updated', (job) => {
  console.log('Job updated:', job);
});
```

#### Job Completed

```javascript
socket.on('job_completed', (job) => {
  console.log('Job completed:', job);
});
```

#### Job Failed

```javascript
socket.on('job_failed', (data) => {
  console.log('Job failed:', data.job, data.error);
});
```

#### Cost Warning

```javascript
socket.on('cost_warning', (warning) => {
  console.warn('Cost warning:', warning);
});
```

#### Cost Exceeded

```javascript
socket.on('cost_exceeded', (exceeded) => {
  console.error('Cost exceeded:', exceeded);
});
```

---

## Error Responses

All errors follow this format:

```json
{
  "error": "Error type",
  "message": "Detailed error message"
}
```

**Common Status Codes:**
- `200` - Success
- `201` - Created
- `204` - No Content
- `400` - Bad Request
- `404` - Not Found
- `429` - Rate Limit Exceeded (Budget)
- `500` - Internal Server Error

---

## Running the API

### Development

```bash
# Start API server
python run_api.py

# Start worker (in separate terminal)
python run_worker.py
```

### Production (Docker)

```bash
docker-compose up
```

---

## Rate Limiting

Budget limits are enforced:
- Per-job limit
- Daily limit
- Monthly limit

When exceeded, API returns `429 Too Many Requests`.

---

## CORS

CORS is enabled for all origins in development. Configure `CORS_ORIGINS` env var for production.

---

## Health Check

```http
GET /health
```

**Response (200):**
```json
{
  "status": "healthy",
  "version": "2.0.0"
}
```
