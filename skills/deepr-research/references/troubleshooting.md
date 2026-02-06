# Troubleshooting Reference

This document covers common issues, error scenarios, and solutions when using Deepr.

## Contents

- [API Key Issues](#api-key-issues)
- [Job Failures](#job-failures)
- [Budget and Cost Issues](#budget-and-cost-issues)
- [Expert System Issues](#expert-system-issues)
- [Network and Connectivity](#network-and-connectivity)
- [Database and Storage](#database-and-storage)
- [MCP Server Issues](#mcp-server-issues)
- [Common Error Codes](#common-error-codes)
- [Getting Help](#getting-help)

## API Key Issues

### Missing API Key

Symptom: `API key not configured for provider: [PROVIDER]`

Solution:
```bash
# Set via environment variable
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
export GOOGLE_API_KEY="..."
export XAI_API_KEY="..."

# Or configure via CLI
deepr config set openai_api_key "sk-..."
deepr config set anthropic_api_key "sk-ant-..."
```

### Invalid API Key

Symptom: `Authentication failed` or `Invalid API key`

Causes:
- Key has been revoked or expired
- Key copied incorrectly (missing characters)
- Key from wrong environment (test vs production)

Solution:
1. Verify key in provider dashboard
2. Regenerate if necessary
3. Ensure no leading/trailing whitespace

### Rate Limiting

Symptom: `Rate limit exceeded` or `429 Too Many Requests`

Solutions:
- Wait and retry (automatic backoff built-in)
- Reduce concurrent research jobs
- Upgrade API tier with provider
- Switch to alternative provider temporarily

## Job Failures

### Job Stuck in "Running" State

Symptom: Job shows running but no progress for extended period

Diagnostic:
```bash
deepr status [JOB_ID] --verbose
```

Causes:
- Provider API timeout
- Network connectivity issues
- Large research scope causing extended processing

Solutions:
1. Check provider status page
2. Cancel and retry with smaller scope
3. Use `--timeout` flag to set explicit limits

### Job Failed with No Output

Symptom: Job completes but results are empty or minimal

Causes:
- Query too vague for meaningful research
- Provider returned empty response
- Budget exhausted mid-research

Solutions:
1. Refine query with more specific focus
2. Check remaining budget
3. Review job logs for provider errors

### Partial Results

Symptom: Research completed but missing expected sections

Causes:
- Budget limit reached during execution
- Provider rate limiting mid-job
- Scope too broad for allocated resources

Solutions:
1. Increase budget allocation
2. Break into smaller focused queries
3. Use follow-up research for missing areas

## Budget and Cost Issues

### Budget Exceeded Error

Symptom: `Budget limit exceeded. Estimated: $X, Limit: $Y`

This is expected behavior - Deepr prevents overspending.

Solutions:
- Increase budget: `deepr run --budget 10.00 "query"`
- Use cheaper model: `deepr run --model grok-4-fast "query"`
- Reduce scope of research

### Unexpected High Costs

Symptom: Research cost more than expected

Causes:
- Deep research mode selected for simple query
- Multiple follow-up queries accumulated
- Agentic mode ran extended iterations

Prevention:
1. Always check cost estimate before confirming
2. Use `--dry-run` to preview costs
3. Set explicit budget limits
4. Monitor session costs with `deepr cost session`

### Cost Tracking Discrepancy

Symptom: Reported costs don't match provider billing

Note: Deepr estimates are approximations based on token counts.

Factors affecting accuracy:
- Provider pricing changes
- Cached responses (may be cheaper)
- Retry attempts on failures

## Expert System Issues

### Expert Not Found

Symptom: `Expert not found: [NAME]`

Solutions:
```bash
# List available experts
deepr expert list

# Search by topic
deepr expert search "machine learning"
```

### Expert Knowledge Outdated

Symptom: Expert provides information that seems stale

Solutions:
1. Check expert's last training date
2. Run new research to update knowledge
3. Use agentic mode to fill knowledge gaps

### Expert Confidence Low

Symptom: Expert responses include many caveats or low confidence

This indicates knowledge gaps in the expert's domain.

Solutions:
1. Run targeted research on gap areas
2. Query with more specific questions
3. Use `deepr expert gaps [NAME]` to identify weak areas

## Network and Connectivity

### Connection Timeout

Symptom: `Connection timed out` or `Network unreachable`

Solutions:
1. Check internet connectivity
2. Verify firewall allows HTTPS outbound
3. Check if provider is experiencing outage
4. Try alternative provider

### SSL Certificate Errors

Symptom: `SSL certificate verification failed`

Causes:
- Corporate proxy intercepting traffic
- Outdated CA certificates
- Clock skew on system

Solutions:
1. Update system CA certificates
2. Configure proxy settings if applicable
3. Verify system clock is accurate

### Proxy Configuration

For corporate environments:
```bash
export HTTP_PROXY="http://proxy.company.com:8080"
export HTTPS_PROXY="http://proxy.company.com:8080"
export NO_PROXY="localhost,127.0.0.1"
```

## Database and Storage

### Database Locked

Symptom: `Database is locked` or `SQLite busy`

Causes:
- Multiple Deepr processes accessing same database
- Previous process crashed without cleanup

Solutions:
1. Ensure only one Deepr instance running
2. Wait a few seconds and retry
3. If persistent: `deepr db repair`

### Storage Full

Symptom: `No space left on device` or write failures

Solutions:
1. Clean old research results: `deepr cleanup --older-than 30d`
2. Archive completed campaigns
3. Increase storage allocation

### Corrupted Data

Symptom: Unexpected errors reading saved data

Solutions:
```bash
# Verify database integrity
deepr db check

# Repair if issues found
deepr db repair

# Export and reimport if severe
deepr export --all backup.json
deepr db reset
deepr import backup.json
```

## MCP Server Issues

### Server Not Starting

Symptom: MCP server fails to initialize

Diagnostic:
```bash
deepr mcp start --verbose
```

Common causes:
- Port already in use
- Missing dependencies
- Configuration errors

### Tool Discovery Failing

Symptom: `deepr_tool_search` returns no results

Solutions:
1. Verify tool registry is initialized
2. Check search query is not empty
3. Rebuild registry: `deepr mcp rebuild-registry`

### Subscription Not Receiving Updates

Symptom: Subscribed to resource but no notifications

Causes:
- Subscription expired
- Job completed before subscription
- Network issues with event delivery

Solutions:
1. Resubscribe to resource
2. Poll status as fallback
3. Check server logs for emission errors

## Common Error Codes

| Code | Meaning | Action |
|------|---------|--------|
| E001 | API key missing | Configure provider API key |
| E002 | Authentication failed | Verify API key is valid |
| E003 | Rate limited | Wait and retry |
| E004 | Budget exceeded | Increase budget or reduce scope |
| E005 | Job timeout | Retry with smaller scope |
| E006 | Provider unavailable | Try alternative provider |
| E007 | Invalid query | Refine research query |
| E008 | Expert not found | Check expert name spelling |
| E009 | Database error | Run db repair |
| E010 | Network error | Check connectivity |

## Getting Help

### Diagnostic Information

When reporting issues, include:
```bash
# Version info
deepr --version

# Configuration (sanitized)
deepr config show --safe

# Recent logs
deepr logs --tail 50
```

### Log Locations

- Main log: `~/.deepr/logs/deepr.log`
- Research logs: `~/.deepr/logs/research/`
- MCP server logs: `~/.deepr/logs/mcp.log`

### Debug Mode

For detailed troubleshooting:
```bash
deepr --debug run "query"
```

This enables verbose logging of:
- API requests and responses
- Token counting
- Cost calculations
- Job state transitions
