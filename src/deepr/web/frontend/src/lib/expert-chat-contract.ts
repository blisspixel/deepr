import type { ChatMode } from '../types'

export interface BrowserExpertChatRequestPayload {
  message: string
  backend: 'api'
  chat_mode: ChatMode
  budget: number
  allow_metered_api: true
  confirm_metered_cost: true
}

export function clampBrowserExpertChatBudgetInput(currentInput: string, maxBudget: number): string {
  if (!Number.isFinite(maxBudget) || maxBudget <= 0) return currentInput
  const currentBudget = Number(currentInput)
  if (!currentInput.trim() || !Number.isFinite(currentBudget) || currentBudget <= 0 || currentBudget > maxBudget) {
    return maxBudget.toFixed(2)
  }
  return currentInput
}

export function browserExpertChatFailureMessage({
  error,
  retryable,
  partialContent = '',
}: {
  error: string
  retryable: boolean
  partialContent?: string
}): string {
  const guidance = retryable
    ? 'Review and re-confirm the metered session ceiling, then use Retry.'
    : 'This request cannot be retried from the current message.'
  return [partialContent.trim(), `Chat failed: ${error}`, guidance].filter(Boolean).join('\n\n')
}

type BrowserExpertChatRequestResult =
  | { ok: true; request: BrowserExpertChatRequestPayload }
  | { ok: false; error: string }

export function prepareBrowserExpertChatRequest({
  message,
  chatMode,
  budgetInput,
  maxBudget,
  meteredConfirmed,
}: {
  message: string
  chatMode: ChatMode
  budgetInput: string
  maxBudget: number
  meteredConfirmed: boolean
}): BrowserExpertChatRequestResult {
  if (!Number.isFinite(maxBudget) || maxBudget <= 0) {
    return {
      ok: false,
      error: 'Chat budget controls are unavailable. Retry after the cost limits load.',
    }
  }
  if (!meteredConfirmed) {
    return { ok: false, error: 'Confirm metered API chat before sending a message.' }
  }

  const budget = Number(budgetInput)
  if (!Number.isFinite(budget) || budget <= 0 || budget > maxBudget) {
    return {
      ok: false,
      error: `Chat budget must be greater than $0 and no more than $${maxBudget.toFixed(2)}.`,
    }
  }

  return {
    ok: true,
    request: {
      message: message.trim(),
      backend: 'api',
      chat_mode: chatMode,
      budget,
      allow_metered_api: true,
      confirm_metered_cost: true,
    },
  }
}
