manager.py — Job Management CLI for Deepr
manager.py is a companion utility to deepr.py, designed to provide operational visibility and control over research jobs submitted to OpenAI's asynchronous /v1/responses endpoint. It enables developers to inspect, manage, and troubleshoot long-running or background tasks created by deepr.

This tool is suitable for use in both interactive and scripted environments and integrates directly with the shared job_log.jsonl used by deepr.py.

Responsibilities
Parse and display job metadata from the job log

Refresh job statuses via OpenAI's API

Display compact summaries or detailed metadata

Cancel submitted or in-progress jobs

Download and persist job outputs

Automatically prune old jobs from the log

Prerequisites
Python 3.8 or later

OpenAI Python SDK (openai)

Additional dependencies: colorama, python-dotenv

Install dependencies:

bash
Copy
Edit
pip install -r requirements.txt
Environment configuration (.env file):

ini
Copy
Edit
OPENAI_API_KEY=sk-...
Command Line Usage
Interactive Mode
Launch the TUI menu:

bash
Copy
Edit
python manager.py --interactive
CLI Options
bash
Copy
Edit
# List most recent completed jobs
python manager.py --list

# List all jobs (active and completed)
python manager.py --list --all

# View detailed metadata for a specific job
python manager.py --details <response_id>

# Download output from a completed job
python manager.py --download <response_id>

# Cancel an in-progress job
python manager.py --cancel <response_id>

# Cancel all active jobs
python manager.py --cancel-all

# Clear the log file entirely
python manager.py --clear
Log File Format
All jobs are stored in job_log.jsonl, a newline-delimited JSON file. Each entry includes metadata such as:

json
Copy
Edit
{
  "response_id": "resp_abc123",
  "status": "completed",
  "timestamp": "2025-07-04T13:45:00Z",
  "prompt": "Summarize recent AI advancements...",
  "model": "gpt-4o",
  "temperature": 0.7,
  "usage": {
    "total_tokens": 1450
  }
}
Entries are automatically updated or pruned based on status and timestamp.

Features
Job Summaries

Displays a list of recent or active jobs, sorted by creation time

Includes status, job ID, human-readable timestamps, and prompt excerpts

Detailed Inspection

Provides full metadata for any job, including model used, token usage, and full prompt

Report Download

Downloads response content from completed jobs

Saves output to reports/report_<job_id>.txt

Also previews the first portion of the output in the terminal

Job Cancellation

Allows cancellation of active jobs using the OpenAI API

Marks jobs as cancelled in the local log

Automatic Cleanup

Removes completed jobs older than 7 days at startup

Keeps the job log file manageable without manual intervention

Developer Notes
manager.py is stateless between runs and operates directly on the log file

Invalid or malformed log entries are skipped, not crashed

list_jobs() returns structured summaries and handles sorting internally

File locking is not implemented; concurrent access is not supported

Interactive and CLI modes use the same underlying functions

Suggested Enhancements
Add CSV export functionality for reporting or audit

Support filtering by date, model, or keywords

Implement tag-based grouping or metadata extensions

Build web dashboard integration or notebook view

Introduce file locking or multi-user coordination

Related Files
deepr.py — job creation and polling logic

job_log.jsonl — append-only log of all jobs

reports/ — downloaded completions and responses

