import { Link, useLocation } from 'react-router-dom'
import {
  LayoutDashboard,
  Search,
  FileText,
  Users,
  DollarSign,
  Settings,
  HelpCircle,
  PanelLeftClose,
  PanelLeftOpen,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useUIStore } from '@/stores/ui-store'
import { useNotificationStore } from '@/stores/notification-store'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'

interface NavItem {
  path: string
  label: string
  icon: LucideIcon
  badge?: number
}

const mainNavItems: NavItem[] = [
  { path: '/', label: 'Overview', icon: LayoutDashboard },
  { path: '/research', label: 'Research', icon: Search },
  { path: '/results', label: 'Results', icon: FileText },
  { path: '/experts', label: 'Experts', icon: Users },
  { path: '/costs', label: 'Costs', icon: DollarSign },
]

const bottomNavItems: NavItem[] = [
  { path: '/settings', label: 'Settings', icon: Settings },
]

function NavLink({
  item,
  isActive,
  collapsed,
}: {
  item: NavItem
  isActive: boolean
  collapsed: boolean
}) {
  const Icon = item.icon

  const linkContent = (
    <Link
      to={item.path}
      className={cn(
        'flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors',
        'hover:bg-sidebar-accent hover:text-sidebar-accent-foreground',
        isActive
          ? 'bg-sidebar-accent text-sidebar-accent-foreground'
          : 'text-sidebar-foreground/70',
        collapsed && 'justify-center px-2'
      )}
    >
      <Icon className="h-4 w-4 shrink-0" />
      {!collapsed && (
        <>
          <span className="flex-1">{item.label}</span>
          {item.badge !== undefined && item.badge > 0 && (
            <Badge variant="destructive" className="h-5 min-w-5 px-1.5 text-[10px]">
              {item.badge}
            </Badge>
          )}
        </>
      )}
      {collapsed && item.badge !== undefined && item.badge > 0 && (
        <span className="absolute right-1 top-1 h-2 w-2 rounded-full bg-destructive" />
      )}
    </Link>
  )

  if (collapsed) {
    return (
      <Tooltip delayDuration={0}>
        <TooltipTrigger asChild>
          <div className="relative">{linkContent}</div>
        </TooltipTrigger>
        <TooltipContent side="right" className="flex items-center gap-2">
          {item.label}
          {item.badge !== undefined && item.badge > 0 && (
            <Badge variant="destructive" className="h-5 min-w-5 px-1.5 text-[10px]">
              {item.badge}
            </Badge>
          )}
        </TooltipContent>
      </Tooltip>
    )
  }

  return linkContent
}

export default function Sidebar() {
  const location = useLocation()
  const { sidebarCollapsed, toggleSidebar } = useUIStore()
  const { failedJobCount } = useNotificationStore()

  // Attach badge counts to nav items
  const mainItems = mainNavItems.map((item) => {
    if (item.path === '/results' && failedJobCount > 0) {
      return { ...item, badge: failedJobCount }
    }
    return item
  })

  const isActivePath = (path: string) => {
    if (path === '/') return location.pathname === '/'
    return location.pathname.startsWith(path)
  }

  return (
    <TooltipProvider>
      <aside
        className={cn(
          'flex h-full flex-col border-r bg-sidebar-background transition-all duration-200',
          sidebarCollapsed ? 'w-14' : 'w-56'
        )}
      >
        {/* Logo */}
        <div
          className={cn(
            'flex h-14 items-center border-b px-3',
            sidebarCollapsed ? 'justify-center' : 'gap-2'
          )}
        >
          <Link
            to="/"
            className="flex items-center gap-2 text-sidebar-foreground"
          >
            <div className="flex h-7 w-7 items-center justify-center rounded-md bg-primary text-primary-foreground text-xs font-bold">
              D
            </div>
            {!sidebarCollapsed && (
              <span className="text-lg font-semibold tracking-tight">
                Deepr
              </span>
            )}
          </Link>
        </div>

        {/* Main navigation */}
        <nav className="flex-1 space-y-1 p-2">
          {mainItems.map((item) => (
            <NavLink
              key={item.path}
              item={item}
              isActive={isActivePath(item.path)}
              collapsed={sidebarCollapsed}
            />
          ))}
        </nav>

        {/* Bottom section */}
        <div className="p-2">
          <Separator className="mb-2" />
          {bottomNavItems.map((item) => (
            <NavLink
              key={item.path}
              item={item}
              isActive={isActivePath(item.path)}
              collapsed={sidebarCollapsed}
            />
          ))}

          {/* Help link */}
          {sidebarCollapsed ? (
            <Tooltip delayDuration={0}>
              <TooltipTrigger asChild>
                <a
                  href="https://docs.deepr.dev"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center justify-center rounded-md px-2 py-2 text-sm font-medium text-sidebar-foreground/70 transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
                >
                  <HelpCircle className="h-4 w-4 shrink-0" />
                </a>
              </TooltipTrigger>
              <TooltipContent side="right">Help</TooltipContent>
            </Tooltip>
          ) : (
            <a
              href="https://docs.deepr.dev"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium text-sidebar-foreground/70 transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
            >
              <HelpCircle className="h-4 w-4 shrink-0" />
              <span className="flex-1">Help</span>
            </a>
          )}

          {/* Collapse toggle */}
          <Separator className="my-2" />
          {sidebarCollapsed ? (
            <Tooltip delayDuration={0}>
              <TooltipTrigger asChild>
                <button
                  onClick={toggleSidebar}
                  className="flex w-full items-center justify-center rounded-md px-2 py-2 text-sm font-medium text-sidebar-foreground/70 transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
                >
                  <PanelLeftOpen className="h-4 w-4" />
                </button>
              </TooltipTrigger>
              <TooltipContent side="right">Expand sidebar</TooltipContent>
            </Tooltip>
          ) : (
            <button
              onClick={toggleSidebar}
              className="flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm font-medium text-sidebar-foreground/70 transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
            >
              <PanelLeftClose className="h-4 w-4 shrink-0" />
              <span>Collapse</span>
            </button>
          )}
        </div>
      </aside>
    </TooltipProvider>
  )
}
