import assert from 'node:assert/strict'
import test from 'node:test'

import {
  browserExpertChatFailureMessage,
  clampBrowserExpertChatBudgetInput,
  prepareBrowserExpertChatRequest,
} from '../src/lib/expert-chat-contract.ts'

const base = {
  message: 'What changed?',
  chatMode: 'research',
  budgetInput: '0.50',
  maxBudget: 2,
  meteredConfirmed: true,
}

test('builds an explicit API-only metered chat request', () => {
  const result = prepareBrowserExpertChatRequest(base)

  assert.equal(result.ok, true)
  assert.deepEqual(result.request, {
    message: 'What changed?',
    backend: 'api',
    chat_mode: 'research',
    budget: 0.5,
    allow_metered_api: true,
    confirm_metered_cost: true,
  })
})

test('fails closed until metered cost is acknowledged', () => {
  const result = prepareBrowserExpertChatRequest({ ...base, meteredConfirmed: false })

  assert.deepEqual(result, {
    ok: false,
    error: 'Confirm metered API chat before sending a message.',
  })
})

test('rejects zero, nonnumeric, and over-limit session budgets', () => {
  assert.equal(prepareBrowserExpertChatRequest({ ...base, budgetInput: '0' }).ok, false)
  assert.equal(prepareBrowserExpertChatRequest({ ...base, budgetInput: 'not-a-number' }).ok, false)
  assert.deepEqual(
    prepareBrowserExpertChatRequest({ ...base, budgetInput: '2.01' }),
    { ok: false, error: 'Chat budget must be greater than $0 and no more than $2.00.' },
  )
})

test('fails closed when the server budget ceiling is unavailable', () => {
  const result = prepareBrowserExpertChatRequest({ ...base, maxBudget: 0 })

  assert.deepEqual(result, {
    ok: false,
    error: 'Chat budget controls are unavailable. Retry after the cost limits load.',
  })
})

test('initializes and clamps the displayed ceiling to the loaded server maximum', () => {
  assert.equal(clampBrowserExpertChatBudgetInput('', 0.2), '0.20')
  assert.equal(clampBrowserExpertChatBudgetInput('0.50', 0.2), '0.20')
  assert.equal(clampBrowserExpertChatBudgetInput('0.10', 0.2), '0.10')
  assert.equal(clampBrowserExpertChatBudgetInput('', 0), '')
})

test('terminal chat failures retain partial output and explicit retry acknowledgement', () => {
  assert.equal(
    browserExpertChatFailureMessage({
      error: 'Expert chat failed. Start a new session and retry.',
      retryable: true,
      partialContent: 'Partial answer',
    }),
    [
      'Partial answer',
      'Chat failed: Expert chat failed. Start a new session and retry.',
      'Review and re-confirm the metered session ceiling, then use Retry.',
    ].join('\n\n'),
  )
})
