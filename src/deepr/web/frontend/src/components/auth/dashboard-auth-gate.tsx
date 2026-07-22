import { useCallback, useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react'
import { KeyRound, Loader2, ServerOff, ShieldCheck, TriangleAlert } from 'lucide-react'
import { apiClient } from '@/api/client'
import {
  DASHBOARD_AUTH_REQUIRED_EVENT,
  classifyDashboardAccessError,
  clearDashboardToken,
  clearLegacyDashboardToken,
  createAuthAttemptGuard,
  dashboardShellCanMount,
  loadDashboardToken,
  shouldHandleAuthFailure,
  storeDashboardToken,
  type DashboardAccessError,
  type DashboardAccessState,
  type DashboardAuthRequiredDetail,
} from '@/lib/dashboard-auth'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

interface DashboardAuthGateProps {
  children: ReactNode
}

async function checkDashboardAccess(token: string): Promise<'authenticated' | DashboardAccessError> {
  try {
    await apiClient.get('/cost/limits', {
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    })
    return 'authenticated'
  } catch (error) {
    return classifyDashboardAccessError(error)
  }
}

export default function DashboardAuthGate({ children }: DashboardAuthGateProps) {
  const [accessState, setAccessStateValue] = useState<DashboardAccessState>('checking')
  const [tokenInput, setTokenInput] = useState('')
  const [feedback, setFeedback] = useState('')
  const [tokenInvalid, setTokenInvalid] = useState(false)
  const accessStateRef = useRef<DashboardAccessState>('checking')
  const attemptGuardRef = useRef(createAuthAttemptGuard())
  const errorHeadingRef = useRef<HTMLHeadingElement>(null)

  const setAccessState = useCallback((state: DashboardAccessState) => {
    accessStateRef.current = state
    setAccessStateValue(state)
  }, [])

  const applyAccessResult = useCallback((result: 'authenticated' | DashboardAccessError, token: string) => {
    if (result === 'authenticated') {
      if (token) storeDashboardToken(token)
      setFeedback('')
      setTokenInvalid(false)
      setTokenInput('')
      setAccessState('authenticated')
      return
    }

    if (result === 'auth_required') {
      clearDashboardToken()
      setTokenInvalid(Boolean(token))
      setFeedback(token ? 'Token rejected. Check the DEEPR_API_KEY value and try again.' : '')
    } else {
      setTokenInvalid(false)
      setFeedback('')
    }
    setAccessState(result)
  }, [setAccessState])

  const verifyCurrentSession = useCallback(async (candidateToken = '') => {
    const attempt = attemptGuardRef.current.begin()
    setAccessState('checking')
    setFeedback('')
    const token = candidateToken.trim() || loadDashboardToken()
    const result = await checkDashboardAccess(token)
    if (attemptGuardRef.current.isCurrent(attempt)) applyAccessResult(result, token)
  }, [applyAccessResult, setAccessState])

  useEffect(() => {
    const attemptGuard = attemptGuardRef.current
    clearLegacyDashboardToken()
    void verifyCurrentSession()
    return () => attemptGuard.invalidate()
  }, [verifyCurrentSession])

  useEffect(() => {
    const requireAuthentication = (event: Event) => {
      const presentedToken = (event as CustomEvent<DashboardAuthRequiredDetail>).detail?.token ?? ''
      const currentToken = loadDashboardToken()
      if (!shouldHandleAuthFailure(
        presentedToken,
        currentToken,
        accessStateRef.current === 'authenticated',
      )) return

      attemptGuardRef.current.invalidate()
      clearDashboardToken()
      setTokenInvalid(Boolean(presentedToken))
      setFeedback(presentedToken
        ? 'Dashboard token was rejected. Enter the current server token.'
        : 'The server now requires a dashboard token.')
      setAccessState('auth_required')
    }
    window.addEventListener(DASHBOARD_AUTH_REQUIRED_EVENT, requireAuthentication)
    return () => window.removeEventListener(DASHBOARD_AUTH_REQUIRED_EVENT, requireAuthentication)
  }, [setAccessState])

  useEffect(() => {
    if (!['checking', 'authenticated', 'auth_required'].includes(accessState)) {
      errorHeadingRef.current?.focus()
    }
  }, [accessState])

  const submitToken = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const token = tokenInput.trim()
    if (!token) {
      setFeedback('Enter the dashboard token before continuing.')
      setTokenInvalid(true)
      return
    }

    const attempt = attemptGuardRef.current.begin()
    setAccessState('checking')
    const result = await checkDashboardAccess(token)
    if (!attemptGuardRef.current.isCurrent(attempt)) return
    applyAccessResult(result, token)
  }

  if (dashboardShellCanMount(accessState)) return children

  if (accessState === 'checking') {
    return (
      <main className="flex min-h-dvh items-center justify-center bg-background p-6" aria-busy="true">
        <div role="status" className="flex items-center gap-3 text-sm text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" />
          Checking dashboard access
        </div>
      </main>
    )
  }

  if (accessState === 'auth_required') {
    return (
      <main className="flex min-h-dvh items-center justify-center bg-background p-6">
        <section className="w-full max-w-md rounded-xl border bg-card p-6 shadow-sm" aria-labelledby="dashboard-auth-title">
          <div className="mb-5 flex h-11 w-11 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <ShieldCheck className="h-5 w-5" aria-hidden="true" />
          </div>
          <h1 id="dashboard-auth-title" className="text-xl font-semibold text-foreground">Unlock dashboard</h1>
          <p id="dashboard-token-help" className="mt-2 text-sm text-muted-foreground">
            Enter the value configured in DEEPR_API_KEY. It is kept only for this browser tab and is sent to this Deepr server.
          </p>
          <form className="mt-6 space-y-4" onSubmit={submitToken}>
            <div className="space-y-2">
              <label htmlFor="dashboard-token" className="text-sm font-medium text-foreground">Dashboard token</label>
              <div className="relative">
                <KeyRound className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
                <Input
                  id="dashboard-token"
                  type="password"
                  value={tokenInput}
                  onChange={(event) => {
                    setTokenInput(event.target.value)
                    setTokenInvalid(false)
                    setFeedback('')
                  }}
                  className="pl-9"
                  aria-describedby={feedback
                    ? 'dashboard-token-help dashboard-token-feedback'
                    : 'dashboard-token-help'}
                  aria-invalid={tokenInvalid}
                  autoComplete="off"
                  autoFocus
                  spellCheck={false}
                />
              </div>
            </div>
            {feedback && (
              <p id="dashboard-token-feedback" role="alert" className="text-sm text-destructive">
                {feedback}
              </p>
            )}
            <Button type="submit" className="w-full">Continue</Button>
          </form>
          <p className="mt-4 text-xs text-muted-foreground">
            For intentional tokenless local access, restart with --allow-unauthenticated-loopback.
          </p>
        </section>
      </main>
    )
  }

  const notConfigured = accessState === 'auth_not_configured'
  const unavailable = accessState === 'server_unavailable'
  const Icon = unavailable ? ServerOff : TriangleAlert
  const title = notConfigured
    ? 'Dashboard authentication is not configured'
    : unavailable
      ? 'Dashboard server unavailable'
      : 'Dashboard access check failed'
  const description = notConfigured
    ? 'Restart Deepr with DEEPR_API_KEY, or explicitly allow tokenless loopback access. The application shell remains locked.'
    : unavailable
      ? 'Start or restart deepr web, then retry. No response was received from the local server.'
      : 'The server returned an unexpected response. Inspect the local server log, then retry.'

  return (
    <main className="flex min-h-dvh items-center justify-center bg-background p-6">
      <section
        role="alert"
        aria-live="assertive"
        className="w-full max-w-md rounded-xl border bg-card p-6 shadow-sm"
        aria-labelledby="dashboard-access-title"
      >
        <div className="mb-5 flex h-11 w-11 items-center justify-center rounded-lg bg-destructive/10 text-destructive">
          <Icon className="h-5 w-5" aria-hidden="true" />
        </div>
        <h1
          ref={errorHeadingRef}
          id="dashboard-access-title"
          tabIndex={-1}
          className="text-xl font-semibold text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          {title}
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">{description}</p>
        <Button type="button" variant="outline" className="mt-6" onClick={() => void verifyCurrentSession(tokenInput)}>
          Retry access check
        </Button>
      </section>
    </main>
  )
}
