# Webhook Strategy for Deepr

## The Ngrok Problem

**Current approach (v1.x):** Uses ngrok to tunnel localhost for webhook callbacks.

**Why this is odd:**
1. **Extra dependency** - Requires ngrok installed and running
2. **Complex setup** - Process management, URL retrieval, tunnel monitoring
3. **Unreliable** - Tunnels can drop, URLs change on restart
4. **Security concern** - Exposes local dev environment to internet
5. **Not local-first** - Defeats our local deployment philosophy

## Better Approaches

### Option 1: Polling (Recommended for Local Deployment)

**How it works:**
- Worker polls the provider API for job status
- Check every 30-60 seconds
- Update local queue when status changes
- No webhooks, no tunnels, no exposed ports

**Advantages:**
- Simple, reliable, no external dependencies
- Works everywhere (local, container, cloud)
- No security exposure
- Provider-agnostic (all support polling)

**Disadvantages:**
- Slight delay in status updates (30-60s)
- More API calls (but providers expect this)

**Implementation:**
```python
# deepr/worker/poller.py
async def poll_active_jobs():
    while True:
        jobs = await queue.get_in_progress_jobs()

        for job in jobs:
            status = await provider.get_status(job.id)

            if status.completed:
                result = await provider.get_result(job.id)
                await storage.save_result(job.id, result)
                await queue.mark_completed(job.id)

            elif status.failed:
                await queue.mark_failed(job.id, status.error)

        await asyncio.sleep(30)  # Poll every 30 seconds
```

### Option 2: WebSocket Events (For Web Deployment)

**How it works:**
- Frontend connects to backend via WebSocket
- Worker updates queue, emits events
- Frontend receives real-time updates
- No provider webhooks needed

**Advantages:**
- Real-time UI updates
- No polling overhead in browser
- Works behind NAT/firewall
- Clean separation of concerns

**Implementation:**
```python
# When job status changes
socketio.emit('job.updated', {
    'job_id': job.id,
    'status': job.status,
    'progress': job.progress
})
```

### Option 3: Webhooks (For Cloud Deployment Only)

**When to use:**
- Running on cloud infrastructure with public IP
- Need immediate notifications
- Can configure stable webhook URLs

**How it works:**
- Register webhook URL with provider
- Provider POSTs to your endpoint when job completes
- Update queue and emit to frontend

**Advantages:**
- Immediate notifications (no polling)
- Efficient (no wasted API calls)

**Disadvantages:**
- Requires public endpoint
- Doesn't work for local deployment
- Adds complexity

## Recommended Architecture

### For Local Workstation (Primary)
```
┌─────────────┐
│   Worker    │
│             │
│  ┌───────┐  │     ┌──────────────┐
│  │Poller │──┼────→│  Provider    │
│  └───────┘  │     │  API         │
│      ↓      │     └──────────────┘
│  ┌───────┐  │
│  │ Queue │  │
│  └───────┘  │
└─────────────┘
```

**Flow:**
1. Worker polls provider every 30s
2. Updates local queue
3. CLI/Web checks queue for status

### For Web Deployment (Containerized)
```
┌─────────────┐     WebSocket     ┌─────────────┐
│   Browser   │←─────────────────→│   Backend   │
└─────────────┘                   │             │
                                  │  ┌───────┐  │
                                  │  │Worker │  │
                                  │  └───┬───┘  │
                                  │      ↓      │
                                  │  ┌───────┐  │
                                  │  │Queue  │  │
                                  │  └───────┘  │
                                  └─────────────┘
```

**Flow:**
1. Frontend connects via WebSocket
2. Worker polls provider
3. Updates queue, emits events
4. Frontend gets real-time updates

### For Cloud Deployment (Optional, Low Priority)
```
┌──────────────┐                  ┌─────────────┐
│   Provider   │                  │   Backend   │
│      API     │                  │             │
└──────┬───────┘                  │  ┌───────┐  │
       │                          │  │Webhook│  │
       │  POST /webhook           │  │Handler│  │
       └─────────────────────────→│  └───────┘  │
                                  │      ↓      │
                                  │  ┌───────┐  │
                                  │  │Queue  │  │
                                  │  └───────┘  │
                                  └─────────────┘
```

**Flow:**
1. Provider POSTs to webhook
2. Handler updates queue
3. Emits WebSocket events
4. Frontend updates immediately

## Implementation Plan

### Phase 1: Polling (Now)
- [x] Remove ngrok dependency
- [ ] Implement polling worker
- [ ] Test with local deployment
- [ ] Validate reliability

### Phase 2: WebSocket (Web UI)
- [ ] Add Socket.IO to API
- [ ] Emit events on status changes
- [ ] Frontend real-time updates
- [ ] Test with multiple clients

### Phase 3: Webhooks (Cloud, Optional)
- [ ] Implement webhook handler
- [ ] Register with provider
- [ ] Fallback to polling if webhook fails
- [ ] Test with cloud deployment

## Migration from v1.x

**Remove:**
- `deepr/webhooks/tunnel.py` (ngrok)
- Ngrok from requirements.txt
- Ngrok setup instructions

**Add:**
- `deepr/worker/poller.py` (polling implementation)
- WebSocket events in API
- Documentation for local-first approach

## Configuration

```python
# .env
DEEPR_POLL_INTERVAL=30  # Seconds between polls
DEEPR_USE_WEBHOOKS=false  # Only enable for cloud
DEEPR_WEBHOOK_URL=  # Only needed if USE_WEBHOOKS=true
```

## Bottom Line

**For local deployment:** Use polling. Simple, reliable, no dependencies.

**For web deployment:** Use WebSocket + polling. Real-time UI, works everywhere.

**For cloud deployment:** Add webhooks if needed. But polling still works fine.

**Ngrok is not needed and adds unnecessary complexity.**

---

**Action Items:**
1. Remove ngrok dependency
2. Implement polling worker
3. Document polling approach
4. Test local deployment
5. Add WebSocket events for web UI
