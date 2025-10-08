import { Outlet, Link, useLocation } from 'react-router-dom'
import { useEffect } from 'react'
import { wsClient } from '@/api/websocket'

export default function Layout() {
  const location = useLocation()

  useEffect(() => {
    wsClient.connect()
    return () => {
      wsClient.disconnect()
    }
  }, [])

  const navItems = [
    { path: '/', label: 'Dashboard' },
    { path: '/submit', label: 'Submit' },
    { path: '/jobs', label: 'Queue' },
    { path: '/results', label: 'Results' },
    { path: '/cost', label: 'Analytics' },
  ]

  return (
    <div className="min-h-screen" style={{ backgroundColor: 'var(--color-bg)' }}>
      {/* Header - ChatGPT style */}
      <header className="border-b" style={{ borderColor: 'var(--color-border)' }}>
        <div className="max-w-5xl mx-auto px-4">
          <div className="flex justify-between items-center h-14">
            <Link to="/" className="flex items-center">
              <div className="text-lg font-medium" style={{ color: 'var(--color-text-primary)' }}>
                Deepr
              </div>
            </Link>

            <nav className="hidden md:flex items-center gap-1">
              {navItems.map((item) => {
                const isActive = location.pathname === item.path
                return (
                  <Link
                    key={item.path}
                    to={item.path}
                    className="px-3 py-1.5 rounded-lg text-sm transition-all"
                    style={{
                      color: isActive ? 'var(--color-text-primary)' : 'var(--color-text-secondary)',
                      backgroundColor: isActive ? 'var(--color-surface)' : 'transparent',
                    }}
                    onMouseEnter={(e) => {
                      if (!isActive) {
                        e.currentTarget.style.backgroundColor = 'var(--color-surface)'
                      }
                    }}
                    onMouseLeave={(e) => {
                      if (!isActive) {
                        e.currentTarget.style.backgroundColor = 'transparent'
                      }
                    }}
                  >
                    {item.label}
                  </Link>
                )
              })}
            </nav>

            <div className="text-xs px-2 py-1" style={{ color: 'var(--color-text-secondary)', fontSize: '11px' }}>
              Local
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-4xl mx-auto px-4 py-6">
        <Outlet />
      </main>
    </div>
  )
}
