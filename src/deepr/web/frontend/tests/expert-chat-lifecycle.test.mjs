import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const profileSource = readFileSync(new URL('../src/pages/expert-profile.tsx', import.meta.url), 'utf8')
const websocketSource = readFileSync(new URL('../src/api/websocket.ts', import.meta.url), 'utf8')

test('long-running browser chat has no artificial one-minute timeout', () => {
  assert.doesNotMatch(profileSource, /streamTimeoutRef/)
  assert.doesNotMatch(profileSource, /60_000/)
  assert.doesNotMatch(profileSource, /Chat stream timeout/)
})

test('stop remains pending until the server acknowledges cancellation', () => {
  assert.match(profileSource, /const \[isStopping, setIsStopping\] = useState\(false\)/)
  assert.match(profileSource, /wsClient\.onChatCancelled/)
  assert.match(profileSource, /setIsStopping\(true\)/)
  assert.match(profileSource, /stopped before completion/)
  assert.match(websocketSource, /this\.socket\.on\('chat_cancelled', callback\)/)
  assert.match(websocketSource, /this\.socket\.emit\('chat_stop', \{\}\)[\s\S]*return true/)
})

test('terminal failures remain visible and require renewed metered acknowledgement', () => {
  assert.match(profileSource, /error_code === 'chat_turn_failed'/)
  assert.match(profileSource, /browserExpertChatFailureMessage/)
  assert.match(profileSource, /role: 'assistant',[\s\S]*error: true/)
  assert.match(profileSource, /setMeteredChatConfirmed\(false\)/)
  assert.match(profileSource, /setSessionId\(null\)/)
})
