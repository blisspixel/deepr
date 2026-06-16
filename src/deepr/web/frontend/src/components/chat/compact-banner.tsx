import { X } from 'lucide-react'
import { Button } from '@/components/ui/button'

interface CompactBannerProps {
  messageCount: number
  onCompact: () => void
  onDismiss: () => void
}

export function CompactBanner({ messageCount, onCompact, onDismiss }: CompactBannerProps) {
  return (
    <div className="flex items-center gap-3 px-4 py-2 bg-yellow-500/10 border border-yellow-500/20 rounded-lg text-sm">
      <span className="text-yellow-600 dark:text-yellow-500 text-xs flex-1">
        Context is getting large ({messageCount} messages). Compact to free space?
      </span>
      <Button size="sm" variant="outline" className="h-6 text-xs" onClick={onCompact}>
        Compact
      </Button>
      <button onClick={onDismiss} className="text-muted-foreground hover:text-foreground" aria-label="Dismiss">
        <X className="w-3.5 h-3.5" />
      </button>
    </div>
  )
}
