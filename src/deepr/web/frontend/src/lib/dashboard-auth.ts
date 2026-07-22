export const DASHBOARD_TOKEN_KEY = 'deepr.dashboard_token'
export const DASHBOARD_AUTH_REQUIRED_EVENT = 'deepr:dashboard-auth-required'

const LEGACY_TOKEN_KEY = 'api_token'
let memoryToken = ''
let memoryTokenIsAuthoritative = false

export interface StorageLike {
  getItem(key: string): string | null
  setItem(key: string, value: string): void
  removeItem(key: string): void
}

export interface ApiRequestErrorOptions {
  status?: number | null
  errorCode?: string | null
  hasResponse?: boolean
}

export interface AuthAttemptGuard {
  begin(): number
  invalidate(): void
  isCurrent(attempt: number): boolean
}

export interface DashboardAuthRequiredDetail {
  token: string
}

export type DashboardAccessError =
  | 'auth_required'
  | 'auth_not_configured'
  | 'server_unavailable'
  | 'unexpected'

export type DashboardAccessState = 'checking' | 'authenticated' | DashboardAccessError

export class ApiRequestError extends Error {
  readonly status: number | null
  readonly errorCode: string | null
  readonly hasResponse: boolean

  constructor(message: string, options: ApiRequestErrorOptions = {}) {
    super(message)
    this.name = 'ApiRequestError'
    this.status = options.status ?? null
    this.errorCode = options.errorCode ?? null
    this.hasResponse = options.hasResponse ?? false
  }
}

function browserSessionStorage(): StorageLike | null {
  try {
    return window.sessionStorage
  } catch {
    return null
  }
}

function browserLocalStorage(): StorageLike | null {
  try {
    return window.localStorage
  } catch {
    return null
  }
}

export function loadDashboardToken(storage?: StorageLike | null): string {
  const target = storage === undefined ? browserSessionStorage() : storage
  if (!target || memoryTokenIsAuthoritative) return memoryToken
  try {
    memoryToken = target.getItem(DASHBOARD_TOKEN_KEY)?.trim() ?? ''
  } catch {
    memoryTokenIsAuthoritative = true
  }
  return memoryToken
}

export function storeDashboardToken(token: string, storage?: StorageLike | null): void {
  const normalized = token.trim()
  memoryToken = normalized
  const target = storage === undefined ? browserSessionStorage() : storage
  if (!target) {
    memoryTokenIsAuthoritative = true
    return
  }
  try {
    if (normalized) {
      target.setItem(DASHBOARD_TOKEN_KEY, normalized)
    } else {
      target.removeItem(DASHBOARD_TOKEN_KEY)
    }
    memoryTokenIsAuthoritative = false
  } catch {
    memoryTokenIsAuthoritative = true
  }
}

export function clearDashboardToken(storage?: StorageLike | null): void {
  memoryToken = ''
  const target = storage === undefined ? browserSessionStorage() : storage
  if (!target) {
    memoryTokenIsAuthoritative = true
    return
  }
  try {
    target.removeItem(DASHBOARD_TOKEN_KEY)
    memoryTokenIsAuthoritative = false
  } catch {
    memoryTokenIsAuthoritative = true
  }
}

export function clearLegacyDashboardToken(storage?: StorageLike | null): void {
  const target = storage === undefined ? browserLocalStorage() : storage
  try {
    target?.removeItem(LEGACY_TOKEN_KEY)
  } catch {
    // Inaccessible persistent storage cannot supply a legacy credential.
  }
}

export function classifyDashboardAccessError(error: unknown): DashboardAccessError {
  if (!(error instanceof ApiRequestError)) return 'unexpected'
  if (error.status === 401) return 'auth_required'
  if (error.errorCode === 'AUTH_NOT_CONFIGURED') return 'auth_not_configured'
  if (!error.hasResponse) return 'server_unavailable'
  return 'unexpected'
}

export function createAuthAttemptGuard(): AuthAttemptGuard {
  let current = 0
  return {
    begin() {
      current += 1
      return current
    },
    invalidate() {
      current += 1
    },
    isCurrent(attempt: number) {
      return attempt === current
    },
  }
}

export function shouldHandleAuthFailure(
  presentedToken: string,
  currentToken: string,
  accessEstablished: boolean,
): boolean {
  if (presentedToken !== currentToken) return false
  return Boolean(presentedToken) || accessEstablished
}

export function extractDashboardBearerToken(headers: unknown): string {
  if (!headers || typeof headers !== 'object') return ''

  const values = headers as {
    get?: (name: string) => unknown
    Authorization?: unknown
    authorization?: unknown
  }
  let authorization: unknown
  try {
    authorization = values.get?.('Authorization')
      ?? values.Authorization
      ?? values.authorization
  } catch {
    return ''
  }
  if (typeof authorization !== 'string' || !authorization.startsWith('Bearer ')) return ''
  return authorization.slice('Bearer '.length)
}

export function dashboardShellCanMount(state: DashboardAccessState): boolean {
  return state === 'authenticated'
}
