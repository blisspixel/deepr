import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

import {
  ApiRequestError,
  DASHBOARD_TOKEN_KEY,
  classifyDashboardAccessError,
  clearDashboardToken,
  clearLegacyDashboardToken,
  createAuthAttemptGuard,
  dashboardShellCanMount,
  extractDashboardBearerToken,
  loadDashboardToken,
  shouldHandleAuthFailure,
  storeDashboardToken,
} from '../src/lib/dashboard-auth.ts'

class MemoryStorage {
  constructor(entries = {}) {
    this.entries = new Map(Object.entries(entries))
  }

  getItem(key) {
    return this.entries.get(key) ?? null
  }

  setItem(key, value) {
    this.entries.set(key, String(value))
  }

  removeItem(key) {
    this.entries.delete(key)
  }
}

class ThrowingStorage {
  getItem() {
    throw new Error('storage unavailable')
  }

  setItem() {
    throw new Error('storage unavailable')
  }

  removeItem() {
    throw new Error('storage unavailable')
  }
}

class WriteDeniedStorage extends MemoryStorage {
  setItem() {
    throw new Error('write denied')
  }

  removeItem() {
    throw new Error('write denied')
  }
}

test('dashboard credentials are normalized in session-scoped storage', () => {
  const storage = new MemoryStorage()

  storeDashboardToken('  session-secret  ', storage)

  assert.equal(storage.getItem(DASHBOARD_TOKEN_KEY), 'session-secret')
  assert.equal(loadDashboardToken(storage), 'session-secret')

  clearDashboardToken(storage)
  assert.equal(loadDashboardToken(storage), '')
})

test('blank dashboard credentials are never retained', () => {
  const storage = new MemoryStorage({ [DASHBOARD_TOKEN_KEY]: 'old-secret' })

  storeDashboardToken('   ', storage)

  assert.equal(storage.getItem(DASHBOARD_TOKEN_KEY), null)
})

test('legacy persistent dashboard credentials are removed without migration', () => {
  const storage = new MemoryStorage({ api_token: 'persistent-secret' })

  clearLegacyDashboardToken(storage)

  assert.equal(storage.getItem('api_token'), null)
  assert.equal(storage.getItem(DASHBOARD_TOKEN_KEY), null)
})

test('dashboard credentials retain a tab-local memory fallback when storage is unavailable', () => {
  const storage = new ThrowingStorage()

  assert.doesNotThrow(() => storeDashboardToken('memory-secret', storage))
  assert.equal(loadDashboardToken(storage), 'memory-secret')
  assert.doesNotThrow(() => clearLegacyDashboardToken(storage))

  clearDashboardToken(storage)
  assert.equal(loadDashboardToken(storage), '')
})

test('readable storage cannot erase the memory fallback after a denied write', () => {
  const storage = new WriteDeniedStorage()

  storeDashboardToken('memory-secret', storage)

  assert.equal(loadDashboardToken(storage), 'memory-secret')

  clearDashboardToken(storage)
  assert.equal(loadDashboardToken(storage), '')
})

test('auth attempt guard rejects stale async completions', () => {
  const guard = createAuthAttemptGuard()
  const first = guard.begin()
  const second = guard.begin()

  assert.equal(guard.isCurrent(first), false)
  assert.equal(guard.isCurrent(second), true)

  guard.invalidate()
  assert.equal(guard.isCurrent(second), false)
})

test('auth failures apply only to the credential and state that produced them', () => {
  assert.equal(shouldHandleAuthFailure('old-token', 'new-token', true), false)
  assert.equal(shouldHandleAuthFailure('', '', false), false)
  assert.equal(shouldHandleAuthFailure('', '', true), true)
  assert.equal(shouldHandleAuthFailure('current-token', 'current-token', true), true)
})

test('auth failure correlation extracts only the bearer credential that was presented', () => {
  assert.equal(extractDashboardBearerToken({ get: () => 'Bearer current-token' }), 'current-token')
  assert.equal(extractDashboardBearerToken({ Authorization: 'Bearer property-token' }), 'property-token')
  assert.equal(extractDashboardBearerToken({ authorization: 'Bearer lower-token' }), 'lower-token')
  assert.equal(extractDashboardBearerToken({ Authorization: 'Basic credentials' }), '')
  assert.equal(extractDashboardBearerToken({ get: () => { throw new Error('unreadable') } }), '')
})

test('application content cannot mount until access is authenticated', () => {
  for (const state of ['checking', 'auth_required', 'auth_not_configured', 'server_unavailable', 'unexpected']) {
    assert.equal(dashboardShellCanMount(state), false)
  }
  assert.equal(dashboardShellCanMount('authenticated'), true)
})

test('dashboard access failures retain bounded machine-readable classification', () => {
  assert.equal(
    classifyDashboardAccessError(new ApiRequestError('Unauthorized', { status: 401, hasResponse: true })),
    'auth_required',
  )
  assert.equal(
    classifyDashboardAccessError(new ApiRequestError('Not configured', {
      status: 503,
      errorCode: 'AUTH_NOT_CONFIGURED',
      hasResponse: true,
    })),
    'auth_not_configured',
  )
  assert.equal(
    classifyDashboardAccessError(new ApiRequestError('No response from server')),
    'server_unavailable',
  )
  assert.equal(
    classifyDashboardAccessError(new ApiRequestError('Internal error', { status: 500, hasResponse: true })),
    'unexpected',
  )
  assert.equal(classifyDashboardAccessError(new Error('unknown')), 'unexpected')
})

test('application shell and both transports share the authenticated session contract', async () => {
  const [appSource, clientSource, websocketSource, gateSource, sessionSource] = await Promise.all([
    readFile(new URL('../src/App.tsx', import.meta.url), 'utf8'),
    readFile(new URL('../src/api/client.ts', import.meta.url), 'utf8'),
    readFile(new URL('../src/api/websocket.ts', import.meta.url), 'utf8'),
    readFile(new URL('../src/components/auth/dashboard-auth-gate.tsx', import.meta.url), 'utf8'),
    readFile(new URL('../src/lib/dashboard-auth.ts', import.meta.url), 'utf8'),
  ])

  assert.match(appSource, /<DashboardAuthGate>[\s\S]*<AppShell \/>[\s\S]*<\/DashboardAuthGate>/)
  assert.match(clientSource, /loadDashboardToken\(\)/)
  assert.match(clientSource, /new CustomEvent(?:<[^>]+>)?\(\s*DASHBOARD_AUTH_REQUIRED_EVENT/)
  assert.match(clientSource, /extractDashboardBearerToken\(error\.config\?\.headers\)/)
  assert.match(websocketSource, /loadDashboardToken\(\)/)
  assert.doesNotMatch(clientSource, /localStorage/)
  assert.doesNotMatch(websocketSource, /localStorage/)
  assert.match(sessionSource, /window\.sessionStorage/)
  assert.match(sessionSource, /AUTH_NOT_CONFIGURED/)
  assert.match(gateSource, /Enter the value configured in DEEPR_API_KEY/)
  assert.match(gateSource, /apiClient\.get\('\/cost\/limits'/)
  assert.doesNotMatch(gateSource, /apiClient\.get\('\/jobs\/stats'/)
  assert.match(gateSource, /errorHeadingRef\.current\?\.focus\(\)/)
  assert.match(gateSource, /verifyCurrentSession\(tokenInput\)/)
  assert.match(gateSource, /aria-describedby=/)
  assert.match(gateSource, /aria-invalid=/)
})
