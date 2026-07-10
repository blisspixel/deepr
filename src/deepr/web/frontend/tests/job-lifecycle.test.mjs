import assert from 'node:assert/strict'
import test from 'node:test'

import {
  CANCELLATION_RETRY_MESSAGE,
  isTerminalJobStatus,
} from '../src/lib/job-lifecycle.ts'

test('recognizes every current terminal job status', () => {
  for (const status of ['completed', 'failed', 'cancelled']) {
    assert.equal(isTerminalJobStatus(status), true)
  }
  for (const status of ['queued', 'processing', undefined]) {
    assert.equal(isTerminalJobStatus(status), false)
  }
})

test('uses a truthful retryable cancellation failure message', () => {
  assert.match(CANCELLATION_RETRY_MESSAGE, /not confirmed/)
  assert.match(CANCELLATION_RETRY_MESSAGE, /still be running/)
  assert.match(CANCELLATION_RETRY_MESSAGE, /retry/)
})
