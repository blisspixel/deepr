# /check command

Inspect an accepted research job without creating new provider work.

```text
deepr_check_status(job_id="<returned job id>")
```

Prefer the exact status resource URI returned by `deepr_research` when the host
supports subscriptions. Otherwise poll with a bounded cadence. Retrieve a
completed report with `deepr_get_result` and request cancellation with
`deepr_cancel_job`.

Do not infer completion phases, source counts, or remaining cost that the
provider did not report. A missing local cache entry can mean the job belongs to
another process; return `JOB_NOT_FOUND` honestly.

Cancellation is a request, not proof of zero spend. Preserve the reservation
and final accounting state until provider cancellation and settlement are
known.
