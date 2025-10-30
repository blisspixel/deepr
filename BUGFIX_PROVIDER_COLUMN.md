# Bug Fix: Missing Provider Column in SQLite Queue

**Date:** October 30, 2025
**Severity:** High - Jobs were getting stuck and status checks failing
**Status:** Fixed

## Problem

The SQLite queue database was missing the `provider` column, causing a critical provider mismatch bug:

1. Jobs were created with `provider` field (e.g., `provider="gemini"`)
2. The `provider` field was NOT saved to the database (missing column in schema)
3. When jobs were loaded back from DB, they defaulted to `provider="openai"`
4. Status checks used the wrong provider API:
   - Gemini jobs with `provider_job_id="gemini-xxx"` were queried against OpenAI API
   - This caused errors: `Invalid 'response_id': 'gemini-8625d2d395ee4b91'. Expected an ID that begins with 'resp'.`

### Impact

- 6 jobs stuck in "processing" state indefinitely
- Status checks failing with provider API errors
- No way to retrieve completed results from correct provider
- Users unable to get job results even after completion

## Root Cause

**File:** `deepr/queue/local_queue.py`

### Issue 1: Missing database column
The `CREATE TABLE` statement (line 32-64) did not include the `provider` column, even though the `ResearchJob` dataclass has this field.

### Issue 2: Field not serialized
The `_job_to_dict()` method (line 89-118) did not include `job.provider` in the dictionary.

### Issue 3: Field not deserialized
The `_dict_to_job()` method (line 120-149) did not read `provider` from the row, causing it to default to "openai".

### Issue 4: Wrong provider used for status checks
**File:** `deepr/cli/commands/jobs.py`

The status check (line 64) and result retrieval (line 179) used `config.get("provider", "openai")` instead of `job.provider`, always checking OpenAI even for Gemini/Grok jobs.

## Solution

### 1. Add provider column to database schema
Added `provider TEXT DEFAULT 'openai'` to the table schema.

### 2. Add migration for existing databases
Added migration code to detect and add the provider column if missing:
```python
try:
    cursor.execute("SELECT provider FROM research_queue LIMIT 1")
except sqlite3.OperationalError:
    cursor.execute("ALTER TABLE research_queue ADD COLUMN provider TEXT DEFAULT 'openai'")
```

### 3. Include provider in serialization
Added `"provider": job.provider` to `_job_to_dict()`.

### 4. Include provider in deserialization
Added `provider=row.get("provider", "openai")` to `_dict_to_job()`.

### 5. Use job's provider for API calls
Updated status and result retrieval commands to use `job.provider` with correct API keys:
```python
provider_name = job.provider if hasattr(job, 'provider') and job.provider else config.get("provider", "openai")

# Get provider-specific API key
if provider_name == "gemini":
    api_key = config.get("gemini_api_key")
elif provider_name == "grok":
    api_key = config.get("xai_api_key")
elif provider_name == "azure":
    api_key = config.get("azure_api_key")
else:  # openai
    api_key = config.get("api_key")
```

### 6. Fixed existing corrupted jobs
Wrote migration script to detect provider from `provider_job_id` pattern and update 6 corrupted jobs.

## Files Modified

1. `deepr/queue/local_queue.py`
   - Added `provider` column to schema (line 36)
   - Added migration for existing databases (lines 78-84)
   - Added `provider` to `_job_to_dict()` (line 95)
   - Added `provider` to `_dict_to_job()` (line 126)

2. `deepr/cli/commands/jobs.py`
   - Updated status check to use `job.provider` (lines 65-78)
   - Updated result retrieval to use `job.provider` (lines 180-195)

## Testing

- All 10 queue unit tests passed
- Migration successfully added provider column to existing database
- Fixed 6 stuck jobs by detecting provider from job ID pattern
- Status check now works correctly for OpenAI jobs (verified with research-6cb)

## Prevention

Going forward:
- All new jobs will properly save and retrieve provider information
- Status checks will query the correct provider API
- Jobs won't get stuck due to provider mismatches

## Backwards Compatibility

- Migration is automatic and backwards compatible
- Existing tables get the provider column added on first queue initialization
- Old jobs default to "openai" provider (safe default)
- Provider can be inferred from `provider_job_id` pattern if needed
