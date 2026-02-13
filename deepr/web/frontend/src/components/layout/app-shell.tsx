import { Suspense, useEffect } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import { Loader2, Menu, Search, Sun, Moon, Monitor } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useUIStore } from '@/stores/ui-store'
import { wsClient } from '@/api/websocket'
import { useJobWebSocket } from '@/hooks/use-websocket'
import Sidebar from '@/components/layout/sidebar'
import StatusBar from '@/components/layout/status-bar'
import CommandMenu from '@/components/layout/command-menu'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetTitle } from '@/components/ui/sheet'

export default function AppShell() {
  const { theme, cycleTheme, mobileMenuOpen, setMobileMenuOpen } = useUIStore()
  const location = useLocation()

  // Connect WebSocket on mount, disconnect on unmount
  useEffect(() => {
    wsClient.connect()
    return () => wsClient.disconnect()
  }, [])

  // Invalidate React Query caches on WebSocket events
  useJobWebSocket()

  // Close mobile menu on route change
  useEffect(() => {
    setMobileMenuOpen(false)
  }, [location.pathname, setMobileMenuOpen])

  const themeIcon = () => {
    switch (theme) {
      case 'light':
        return <Sun className="h-4 w-4" />
      case 'dark':
        return <Moon className="h-4 w-4" />
      default:
        return <Monitor className="h-4 w-4" />
    }
  }

  return (
    <div className="flex h-dvh overflow-hidden bg-background">
      {/* Skip to content link */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-[100] focus:px-4 focus:py-2 focus:bg-primary focus:text-primary-foreground focus:rounded-lg focus:text-sm focus:font-medium focus:outline-none focus:ring-2 focus:ring-ring"
      >
        Skip to content
      </a>

      {/* Command palette (rendered in a portal) */}
      <CommandMenu />

      {/* Desktop sidebar */}
      <div className="hidden md:block">
        <Sidebar />
      </div>

      {/* Mobile sidebar sheet */}
      <Sheet open={mobileMenuOpen} onOpenChange={setMobileMenuOpen}>
        <SheetContent side="left" className="w-64 p-0">
          <SheetTitle className="sr-only">Navigation</SheetTitle>
          <Sidebar mobile />
        </SheetContent>
      </Sheet>

      {/* Main area */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Top bar */}
        <header
          aria-label="Top bar"
          className={cn(
            'flex h-14 items-center justify-between border-b px-4 md:px-6',
            'glass'
          )}
        >
          {/* Mobile hamburger */}
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setMobileMenuOpen(true)}
            aria-label="Open navigation menu"
            className="md:hidden h-9 w-9 mr-2"
          >
            <Menu className="h-5 w-5" />
          </Button>

          {/* Search trigger */}
          <button
            onClick={() => {
              document.dispatchEvent(
                new KeyboardEvent('keydown', {
                  key: 'k',
                  ctrlKey: true,
                  metaKey: true,
                  bubbles: true,
                })
              )
            }}
            aria-label="Open command palette"
            className={cn(
              'flex items-center gap-2 rounded-md border bg-muted/40 px-3 py-1.5 text-sm text-muted-foreground transition-colors',
              'hover:bg-muted hover:text-foreground',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
              'flex-1 md:flex-none md:w-72'
            )}
          >
            <Search className="h-4 w-4" />
            <span className="flex-1 text-left">Search or command...</span>
            <kbd className="pointer-events-none hidden select-none items-center gap-1 rounded border bg-muted px-1.5 font-mono text-[10px] font-medium text-muted-foreground sm:flex" aria-hidden="true">
              <span className="text-xs">Ctrl</span>K
            </kbd>
          </button>

          {/* Right side actions */}
          <div className="flex items-center gap-2 ml-2">
            <Button
              variant="ghost"
              size="icon"
              onClick={cycleTheme}
              title={`Theme: ${theme}`}
              aria-label={`Current theme: ${theme}. Click to cycle.`}
              className="h-9 w-9"
            >
              {themeIcon()}
            </Button>
          </div>
        </header>

        {/* Main content */}
        <main id="main-content" className="flex-1 overflow-auto">
          <Suspense fallback={
            <div className="flex items-center justify-center h-[60vh]">
              <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
            </div>
          }>
            <Outlet />
          </Suspense>
        </main>

        {/* Status bar */}
        <StatusBar />
      </div>
    </div>
  )
}
