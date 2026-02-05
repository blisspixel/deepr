import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  LayoutDashboard,
  Search,
  FileText,
  Users,
  DollarSign,
  Settings,
  Plus,
  Sun,
  Moon,
  Monitor,
} from 'lucide-react'
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from '@/components/ui/command'
import { useUIStore } from '@/stores/ui-store'

export default function CommandMenu() {
  const [open, setOpen] = useState(false)
  const navigate = useNavigate()
  const { theme, cycleTheme } = useUIStore()

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        setOpen((prev) => !prev)
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [])

  const runCommand = (callback: () => void) => {
    setOpen(false)
    callback()
  }

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
    <CommandDialog open={open} onOpenChange={setOpen}>
      <CommandInput placeholder="Type a command or search..." />
      <CommandList>
        <CommandEmpty>No results found.</CommandEmpty>

        <CommandGroup heading="Navigation">
          <CommandItem onSelect={() => runCommand(() => navigate('/'))}>
            <LayoutDashboard className="mr-2 h-4 w-4" />
            <span>Overview</span>
          </CommandItem>
          <CommandItem onSelect={() => runCommand(() => navigate('/research'))}>
            <Search className="mr-2 h-4 w-4" />
            <span>Research</span>
          </CommandItem>
          <CommandItem onSelect={() => runCommand(() => navigate('/results'))}>
            <FileText className="mr-2 h-4 w-4" />
            <span>Results</span>
          </CommandItem>
          <CommandItem onSelect={() => runCommand(() => navigate('/experts'))}>
            <Users className="mr-2 h-4 w-4" />
            <span>Experts</span>
          </CommandItem>
          <CommandItem onSelect={() => runCommand(() => navigate('/costs'))}>
            <DollarSign className="mr-2 h-4 w-4" />
            <span>Costs</span>
          </CommandItem>
          <CommandItem onSelect={() => runCommand(() => navigate('/settings'))}>
            <Settings className="mr-2 h-4 w-4" />
            <span>Settings</span>
          </CommandItem>
        </CommandGroup>

        <CommandSeparator />

        <CommandGroup heading="Actions">
          <CommandItem
            onSelect={() => runCommand(() => navigate('/research'))}
          >
            <Plus className="mr-2 h-4 w-4" />
            <span>New Research</span>
          </CommandItem>
          <CommandItem
            onSelect={() => runCommand(() => navigate('/costs'))}
          >
            <DollarSign className="mr-2 h-4 w-4" />
            <span>Check Costs</span>
          </CommandItem>
          <CommandItem onSelect={() => runCommand(cycleTheme)}>
            {themeIcon()}
            <span className="ml-2">
              Toggle Theme (current: {theme})
            </span>
          </CommandItem>
        </CommandGroup>

        <CommandSeparator />

        <CommandGroup heading="Recent">
          <CommandItem onSelect={() => runCommand(() => navigate('/results'))}>
            <FileText className="mr-2 h-4 w-4" />
            <span>Recent Results</span>
          </CommandItem>
          <CommandItem onSelect={() => runCommand(() => navigate('/'))}>
            <LayoutDashboard className="mr-2 h-4 w-4" />
            <span>Dashboard</span>
          </CommandItem>
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  )
}
