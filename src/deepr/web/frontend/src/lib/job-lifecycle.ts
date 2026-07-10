const TERMINAL_JOB_STATUSES = new Set(['completed', 'failed', 'cancelled'])

export const CANCELLATION_RETRY_MESSAGE =
  'Cancellation was not confirmed. The job may still be running. Check provider connectivity and retry.'

export function isTerminalJobStatus(status: string | undefined): boolean {
  return status !== undefined && TERMINAL_JOB_STATUSES.has(status)
}
