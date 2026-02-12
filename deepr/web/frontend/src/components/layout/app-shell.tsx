import { useEffect } from 'react'
import { Outlet } from 'react-router-dom'
import { Search, Sun, Moon, Monitor } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useUIStore } from '@/stores/ui-store'
import { wsClient } from '@/api/websocket'
import { useJobWebSocket } from '@/hooks/use-websocket'
import Sidebar from '@/components/layout/sidebar'
import StatusBar from '@/components/layout/status-bar'
import CommandMenu from '@/components/layout/command-menu'
import { Button } from '@/components/ui/button'

export default function AppShell() {
  const { theme, cycleTheme } = useUIStore()

  // Connect WebSocket on mount, disconnect on unmount
  useEffect(() => {
    wsClient.connect()
    return () => wsClient.disconnect()
  }, [])

  // Invalidate React Query caches on WebSocket events
  useJobWebSocket()

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
    <div className="flex h-screen overflow-hidden bg-background">
      {/* Command palette (rendered in a portal) */}
      <CommandMenu />

      {/* Sidebar */}
      <Sidebar />

      {/* Main area */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Top bar */}
        <header
          className={cn(
            'flex h-14 items-center justify-between border-b px-6',
            'glass'
          )}
        >
          {/* Search trigger */}
          <button
            onClick={() => {
              // Dispatch keyboard event to trigger command menu
              document.dispatchEvent(
                new KeyboardEvent('keydown', {
                  key: 'k',
                  ctrlKey: true,
                  metaKey: true,
                  bubbles: true,
                })
              )
            }}
            className={cn(
              'flex items-center gap-2 rounded-md border bg-muted/40 px-3 py-1.5 text-sm text-muted-foreground transition-colors',
              'hover:bg-muted hover:text-foreground',
              'w-72'
            )}
          >
            <Search className="h-4 w-4" />
            <span className="flex-1 text-left">Search or command...</span>
            <kbd className="pointer-events-none hidden select-none items-center gap-1 rounded border bg-muted px-1.5 font-mono text-[10px] font-medium text-muted-foreground sm:flex">
              <span className="text-xs">Ctrl</span>K
            </kbd>
          </button>

          {/* Right side actions */}
          <div className="flex items-center gap-2">
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
        <main className="flex-1 overflow-auto">
          <Outlet />
        </main>

        {/* Status bar */}
        <StatusBar />
      </div>
    </div>
  )
}
