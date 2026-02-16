import { useCallback } from 'react'
import { Copy, Pencil, RotateCcw } from 'lucide-react'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'

interface MessageActionsProps {
  content: string
  role: 'user' | 'assistant'
  index: number
  onRetry?: (index: number) => void
  onEdit?: (index: number, content: string) => void
  className?: string
}

export function MessageActions({ content, role, index, onRetry, onEdit, className }: MessageActionsProps) {
  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(content)
    toast.success('Copied to clipboard')
  }, [content])

  return (
    <div className={cn(
      'flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity',
      className,
    )}>
      <button
        onClick={handleCopy}
        className="p-1 rounded hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
        aria-label="Copy message"
      >
        <Copy className="w-3 h-3" />
      </button>
      {role === 'assistant' && onRetry && (
        <button
          onClick={() => onRetry(index)}
          className="p-1 rounded hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
          aria-label="Retry response"
        >
          <RotateCcw className="w-3 h-3" />
        </button>
      )}
      {role === 'user' && onEdit && (
        <button
          onClick={() => onEdit(index, content)}
          className="p-1 rounded hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
          aria-label="Edit message"
        >
          <Pencil className="w-3 h-3" />
        </button>
      )}
    </div>
  )
}
