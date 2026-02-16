import { useEffect, useRef, useState } from 'react'
import { CHAT_COMMANDS } from '@/lib/constants'
import { cn } from '@/lib/utils'

interface SlashCommandMenuProps {
  inputValue: string
  visible: boolean
  onSelect: (command: string) => void
  onClose: () => void
}

export function SlashCommandMenu({ inputValue, visible, onSelect, onClose }: SlashCommandMenuProps) {
  const [selectedIndex, setSelectedIndex] = useState(0)
  const listRef = useRef<HTMLDivElement>(null)

  // Filter commands by prefix
  const prefix = inputValue.slice(1).toLowerCase()
  const filtered = CHAT_COMMANDS.filter(
    (cmd) =>
      cmd.name.startsWith(prefix) ||
      cmd.aliases.some((a) => a.startsWith(prefix))
  )

  // Group by category
  const grouped = filtered.reduce<Record<string, typeof filtered>>((acc, cmd) => {
    ;(acc[cmd.category] ??= []).push(cmd)
    return acc
  }, {})

  // Flatten for index navigation
  const flatList = filtered

  useEffect(() => {
    setSelectedIndex(0)
  }, [inputValue])

  useEffect(() => {
    if (!visible) return

    const handler = (e: KeyboardEvent) => {
      if (e.key === 'ArrowDown') {
        e.preventDefault()
        setSelectedIndex((i) => Math.min(i + 1, flatList.length - 1))
      } else if (e.key === 'ArrowUp') {
        e.preventDefault()
        setSelectedIndex((i) => Math.max(i - 1, 0))
      } else if (e.key === 'Enter' && flatList.length > 0) {
        e.preventDefault()
        e.stopImmediatePropagation()
        const cmd = flatList[selectedIndex]
        onSelect(`/${cmd.name}${cmd.args ? ' ' : ''}`)
      } else if (e.key === 'Escape') {
        e.preventDefault()
        onClose()
      }
    }

    window.addEventListener('keydown', handler, true)
    return () => window.removeEventListener('keydown', handler, true)
  }, [visible, selectedIndex, flatList, onSelect, onClose])

  if (!visible || flatList.length === 0) return null

  let flatIdx = 0

  return (
    <div
      ref={listRef}
      className="absolute bottom-full left-0 mb-1 w-72 max-h-64 overflow-auto rounded-lg border bg-popover shadow-lg z-50"
    >
      {Object.entries(grouped).map(([category, cmds]) => (
        <div key={category}>
          <div className="px-3 py-1.5 text-[10px] font-semibold text-muted-foreground uppercase tracking-wider bg-muted/50">
            {category}
          </div>
          {cmds.map((cmd) => {
            const idx = flatIdx++
            return (
              <button
                key={cmd.name}
                className={cn(
                  'flex items-center gap-2 w-full px-3 py-1.5 text-left text-sm transition-colors',
                  idx === selectedIndex ? 'bg-accent text-accent-foreground' : 'hover:bg-muted/50'
                )}
                onClick={() => onSelect(`/${cmd.name}${cmd.args ? ' ' : ''}`)}
                onMouseEnter={() => setSelectedIndex(idx)}
              >
                <span className="font-mono text-xs text-primary">/{cmd.name}</span>
                {cmd.args && <span className="text-[10px] text-muted-foreground">{cmd.args}</span>}
                <span className="ml-auto text-[10px] text-muted-foreground truncate max-w-[120px]">
                  {cmd.description}
                </span>
              </button>
            )
          })}
        </div>
      ))}
    </div>
  )
}
